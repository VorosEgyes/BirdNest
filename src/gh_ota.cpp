#include "gh_ota.h"

#include "battery.h"
#include "config.h"
#include "mqtt_client.h"
#include "telegram.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <esp_app_format.h>
#include <esp_err.h>
#include <esp_http_client.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>
#include <nvs.h>
#include <time.h>

static bool s_ghOtaInitialized = false;

static constexpr uint32_t GH_OTA_DAILY_CHECK_SEC         = 86400UL;
static constexpr float    GH_OTA_MIN_INSTALL_BATTERY_V   = 3.60f;
static constexpr uint8_t  GH_OTA_WIFI_STABLE_RESET_CYCLES = 2;

static constexpr const char* OTA_REASON_NO_UPDATE                         = "no_update";
static constexpr const char* OTA_REASON_UPDATE_FOUND                      = "update_found";
static constexpr const char* OTA_REASON_WIFI_DISCONNECTED                 = "wifi_disconnected";
static constexpr const char* OTA_REASON_WIFI_UNSTABLE                     = "wifi_unstable";
static constexpr const char* OTA_REASON_GITHUB_RELEASES_HTTP              = "github_releases_http";
static constexpr const char* OTA_REASON_GITHUB_RELEASES_PARSE             = "github_releases_parse";
static constexpr const char* OTA_REASON_MANIFEST_HTTP                     = "manifest_http";
static constexpr const char* OTA_REASON_MANIFEST_PARSE                    = "manifest_parse";
static constexpr const char* OTA_REASON_MANIFEST_MISSING_FIELDS           = "manifest_missing_fields";
static constexpr const char* OTA_REASON_BIN_ASSET_NOT_FOUND               = "bin_asset_not_found";
static constexpr const char* OTA_REASON_BATTERY_LOW                       = "battery_low";
static constexpr const char* OTA_REASON_TOKEN_MISSING_FOR_PRIVATE_TARGET  = "token_missing_for_private_target";
static constexpr const char* OTA_REASON_NO_UPDATE_PARTITION               = "no_update_partition";
static constexpr const char* OTA_REASON_MANIFEST_SHA256_INVALID           = "manifest_sha256_invalid";
static constexpr const char* OTA_REASON_INSTALL_START                     = "install_start";
static constexpr const char* OTA_REASON_OTA_BEGIN_FAILED                  = "ota_begin_failed";
static constexpr const char* OTA_REASON_DOWNLOAD_NETWORK_INTERRUPTED      = "download_network_interrupted";
static constexpr const char* OTA_REASON_FLASH_WRITE_FAILED                = "flash_write_failed";
static constexpr const char* OTA_REASON_SIZE_MISMATCH                     = "size_mismatch";
static constexpr const char* OTA_REASON_OTA_FINISH_FAILED                 = "ota_finish_failed";
static constexpr const char* OTA_REASON_SHA256_MISMATCH                   = "sha256_mismatch";
static constexpr const char* OTA_REASON_HEALTH_CONFIRMED                  = "health_confirmed";
static constexpr const char* OTA_REASON_HEALTH_CONFIRMED_DEGRADED         = "health_confirmed_degraded";
static constexpr const char* OTA_REASON_HEALTH_PROBE_FAILED               = "health_probe_failed";
static constexpr const char* GH_OTA_KEY_REBOOT_FLG                       = "otaRebootFlg";
static constexpr const char* GH_OTA_KEY_LAST_TGT                         = "otaLastTgt";

// Keep download buffer in static storage to avoid large stack usage.
static uint8_t s_otaDownloadBuf[4096];

// ============================================================
// SHA-256 helpers
// ============================================================

static String normalizeSha256Hex(const String& inputRaw) {
    String input = inputRaw;
    input.trim();
    input.toLowerCase();
    String out;
    out.reserve(64);
    for (size_t i = 0; i < input.length(); ++i) {
        const char c = input.charAt(i);
        if ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) out += c;
    }
    return out;
}

static int hexNibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
    if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
    return -1;
}

static bool parseSha256ToBytes(const String& shaHex, uint8_t out[32]) {
    const String n = normalizeSha256Hex(shaHex);
    if (n.length() != 64) return false;
    for (int i = 0; i < 32; ++i) {
        const int hi = hexNibble(n.charAt(i * 2));
        const int lo = hexNibble(n.charAt(i * 2 + 1));
        if (hi < 0 || lo < 0) return false;
        out[i] = static_cast<uint8_t>((hi << 4) | lo);
    }
    return true;
}

// ============================================================
// NVS helpers
// ============================================================

static String nvsReadString(const char* key, const String& fallback = "") {
    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READONLY, &handle) != ESP_OK) return fallback;
    size_t needed = 0;
    esp_err_t err = nvs_get_str(handle, key, nullptr, &needed);
    if (err != ESP_OK || needed == 0 || needed > 2048) { nvs_close(handle); return fallback; }
    char* buf = static_cast<char*>(malloc(needed));
    if (!buf) { nvs_close(handle); return fallback; }
    err = nvs_get_str(handle, key, buf, &needed);
    nvs_close(handle);
    if (err != ESP_OK) { free(buf); return fallback; }
    String out(buf);
    free(buf);
    return out;
}

static uint32_t nvsReadU32(const char* key, uint32_t fallback = 0) {
    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READONLY, &handle) != ESP_OK) return fallback;
    uint32_t v = fallback;
    nvs_get_u32(handle, key, &v);
    nvs_close(handle);
    return v;
}

static uint16_t nvsReadU16(const char* key, uint16_t fallback = 0) {
    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READONLY, &handle) != ESP_OK) return fallback;
    uint16_t v = fallback;
    nvs_get_u16(handle, key, &v);
    nvs_close(handle);
    return v;
}

static uint8_t nvsReadU8(const char* key, uint8_t fallback = 0) {
    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READONLY, &handle) != ESP_OK) return fallback;
    uint8_t v = fallback;
    nvs_get_u8(handle, key, &v);
    nvs_close(handle);
    return v;
}

static bool nvsReadBool(const char* key, bool fallback = false) {
    return nvsReadU8(key, fallback ? 1 : 0) != 0;
}

static void nvsWriteString(const char* key, const String& value) {
    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) return;
    nvs_set_str(handle, key, value.c_str());
    nvs_commit(handle);
    nvs_close(handle);
}

static void nvsWriteU32(const char* key, uint32_t value) {
    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) return;
    nvs_set_u32(handle, key, value);
    nvs_commit(handle);
    nvs_close(handle);
}

static void nvsWriteU16(const char* key, uint16_t value) {
    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) return;
    nvs_set_u16(handle, key, value);
    nvs_commit(handle);
    nvs_close(handle);
}

static void nvsWriteU8(const char* key, uint8_t value) {
    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) return;
    nvs_set_u8(handle, key, value);
    nvs_commit(handle);
    nvs_close(handle);
}

static void nvsWriteBool(const char* key, bool value) {
    nvsWriteU8(key, value ? 1 : 0);
}

static void setLastOtaReason(const String& reason) {
    nvsWriteString(GH_OTA_KEY_LAST_REASON, reason);
}

static void mqttOtaEvent(const String& eventType,
                         const String& reason,
                         const String& targetVersion = "") {
    mqttPublishOtaEvent(eventType, reason, targetVersion, ghOtaGetChannel());
}

// ============================================================
// SemVer helpers
// ============================================================

struct ParsedSemVer {
    int major = 0, minor = 0, patch = 0;
    String prerelease;
    bool valid = false;
};

static ParsedSemVer parseSemVer(const String& versionIn) {
    ParsedSemVer out;
    String version = versionIn;
    version.trim();
    if (version.startsWith("v")) version = version.substring(1);
    int dash = version.indexOf('-');
    String core = (dash >= 0) ? version.substring(0, dash) : version;
    if (dash >= 0) out.prerelease = version.substring(dash + 1);
    int d1 = core.indexOf('.');
    int d2 = core.indexOf('.', d1 + 1);
    if (d1 <= 0 || d2 <= d1 + 1) return out;
    out.major = atoi(core.substring(0, d1).c_str());
    out.minor = atoi(core.substring(d1 + 1, d2).c_str());
    out.patch = atoi(core.substring(d2 + 1).c_str());
    out.valid = true;
    return out;
}

static int comparePrereleaseToken(const String& a, const String& b) {
    const bool aNum = a.length() > 0 && (a.toInt() != 0 || a == "0");
    const bool bNum = b.length() > 0 && (b.toInt() != 0 || b == "0");
    if (aNum && bNum) {
        const int ai = a.toInt(), bi = b.toInt();
        return (ai == bi) ? 0 : ((ai > bi) ? 1 : -1);
    }
    if (aNum && !bNum) return -1;
    if (!aNum && bNum) return 1;
    if (a == b) return 0;
    return (a > b) ? 1 : -1;
}

static int comparePrerelease(const String& a, const String& b) {
    if (a == b) return 0;
    if (a.isEmpty() && !b.isEmpty()) return 1;
    if (!a.isEmpty() && b.isEmpty()) return -1;
    int aStart = 0, bStart = 0;
    while (true) {
        int aDot = a.indexOf('.', aStart);
        int bDot = b.indexOf('.', bStart);
        String aTok = (aDot < 0) ? a.substring(aStart) : a.substring(aStart, aDot);
        String bTok = (bDot < 0) ? b.substring(bStart) : b.substring(bStart, bDot);
        int cmp = comparePrereleaseToken(aTok, bTok);
        if (cmp != 0) return cmp;
        if (aDot < 0 && bDot < 0) return 0;
        if (aDot < 0) return -1;
        if (bDot < 0) return 1;
        aStart = aDot + 1;
        bStart = bDot + 1;
    }
}

static int semVerCompare(const String& aVersion, const String& bVersion) {
    ParsedSemVer a = parseSemVer(aVersion);
    ParsedSemVer b = parseSemVer(bVersion);
    if (!a.valid && !b.valid) return 0;
    if (!a.valid) return -1;
    if (!b.valid) return 1;
    if (a.major != b.major) return (a.major > b.major) ? 1 : -1;
    if (a.minor != b.minor) return (a.minor > b.minor) ? 1 : -1;
    if (a.patch != b.patch) return (a.patch > b.patch) ? 1 : -1;
    return comparePrerelease(a.prerelease, b.prerelease);
}

// ============================================================
// Backoff helpers
// ============================================================

static uint32_t wifiBackoffSeconds(uint8_t wifiFailStreak) {
    if (wifiFailStreak <= 1) return 6UL * 3600UL;
    if (wifiFailStreak == 2) return 12UL * 3600UL;
    if (wifiFailStreak == 3) return 24UL * 3600UL;
    return 48UL * 3600UL;
}

// ============================================================
// HTTP helpers
// ============================================================

static bool ghHttpGet(const String& url, const String& token, bool octetAccept,
                      String& outBody, int& outCode) {
    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;
    if (!http.begin(client, url)) { outCode = -1; return false; }
    http.setTimeout(GH_OTA_HTTP_TIMEOUT_MS);
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    http.addHeader("User-Agent", "BirdNest-OTA");
    http.addHeader("X-GitHub-Api-Version", "2022-11-28");
    http.addHeader("Accept", octetAccept ? "application/octet-stream" : "application/vnd.github+json");
    if (!token.isEmpty()) http.addHeader("Authorization", "Bearer " + token);
    outCode = http.GET();
    if (outCode > 0) outBody = http.getString();
    http.end();
    return outCode == 200;
}

static bool ghFetchReleases(const String& token,
                            DynamicJsonDocument& outDoc,
                            bool& parseError,
                            int& httpCode) {
    parseError = false;
    httpCode = -1;
    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;
    const String url = String("https://") + OTA_GH_API_HOST + "/repos/" + OTA_GH_OWNER + "/" + OTA_GH_REPO + "/releases?per_page=10";
    if (!http.begin(client, url)) return false;
    http.setTimeout(GH_OTA_HTTP_TIMEOUT_MS);
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    http.addHeader("User-Agent", "BirdNest-OTA");
    http.addHeader("X-GitHub-Api-Version", "2022-11-28");
    http.addHeader("Accept", "application/vnd.github+json");
    if (!token.isEmpty()) http.addHeader("Authorization", "Bearer " + token);
    httpCode = http.GET();
    if (httpCode != 200) { http.end(); return false; }
    DeserializationError derr = deserializeJson(outDoc, http.getStream());
    http.end();
    if (derr != DeserializationError::Ok || !outDoc.is<JsonArray>()) { parseError = true; return false; }
    return true;
}

// ============================================================
// NVS target helpers
// ============================================================

static void savePendingTarget(const GhOtaTarget& target, const String& reason) {
    StaticJsonDocument<768> doc;
    doc["version"] = target.version;
    doc["channel"] = target.channel;
    doc["bin_asset_url"] = target.binAssetUrl;
    doc["sha256"] = target.sha256;
    doc["min_battery_v"] = target.minBatteryV;
    doc["is_private_repo"] = target.isPrivateRepo;
    if (!reason.isEmpty()) doc["pending_reason"] = reason;
    String raw;
    serializeJson(doc, raw);
    nvsWriteString(GH_OTA_KEY_TARGET, raw);
    if (!reason.isEmpty()) setLastOtaReason(reason);
}

static void clearPendingTarget() {
    nvsWriteString(GH_OTA_KEY_TARGET, "");
}

static void markWifiStabilityFailure(time_t nowEpoch) {
    uint16_t fail = nvsReadU16(GH_OTA_KEY_WIFI_FAIL, 0);
    if (fail < 0xFFFF) ++fail;
    nvsWriteU16(GH_OTA_KEY_WIFI_FAIL, fail);
    nvsWriteU8(GH_OTA_KEY_WIFI_OK, 0);
    if (nowEpoch > 100000) {
        nvsWriteU32(GH_OTA_KEY_BACKOFF,
                    static_cast<uint32_t>(nowEpoch) +
                    wifiBackoffSeconds(static_cast<uint8_t>(fail > 255 ? 255 : fail)) +
                    (esp_random() % 900));
    }
}

static void markWifiStabilitySuccess() {
    uint8_t stableCycles = nvsReadU8(GH_OTA_KEY_WIFI_OK, 0);
    if (stableCycles < GH_OTA_WIFI_STABLE_RESET_CYCLES) ++stableCycles;
    nvsWriteU8(GH_OTA_KEY_WIFI_OK, stableCycles);
    if (stableCycles >= GH_OTA_WIFI_STABLE_RESET_CYCLES) nvsWriteU16(GH_OTA_KEY_WIFI_FAIL, 0);
}

static void incrementCheckFailStreak() {
    uint16_t chkFail = nvsReadU16(GH_OTA_KEY_CHK_FAIL, 0);
    if (chkFail < 0xFFFF) ++chkFail;
    nvsWriteU16(GH_OTA_KEY_CHK_FAIL, chkFail);
}

static bool loadPendingTargetFromNvs(GhOtaTarget& out) {
    const String pending = nvsReadString(GH_OTA_KEY_TARGET, "");
    if (pending.isEmpty()) return false;
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, pending) != DeserializationError::Ok) return false;
    const String version = doc["version"] | "";
    const String binUrl  = doc["bin_asset_url"] | "";
    const String sha     = doc["sha256"] | "";
    if (version.isEmpty() || binUrl.isEmpty() || sha.isEmpty()) return false;
    out.version      = version;
    out.channel      = doc["channel"] | ghOtaGetChannel();
    out.binAssetUrl  = binUrl;
    out.sha256       = sha;
    out.minBatteryV  = doc["min_battery_v"] | 0.0f;
    out.isPrivateRepo = doc["is_private_repo"] | false;
    return true;
}

// ============================================================
// Public API implementation
// ============================================================

void ghOtaInit() {
    if (s_ghOtaInitialized) return;

    nvs_handle_t handle;
    if (nvs_open(GH_OTA_NVS_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) {
        telegramSendDebug("[OTA][ERR] gh_ota NVS open failed", 0);
        return;
    }

    // Write defaults for any missing keys
    if (nvsReadString(GH_OTA_KEY_CHANNEL).isEmpty()) nvs_set_str(handle, GH_OTA_KEY_CHANNEL, "stable");
    if (nvsReadString(GH_OTA_KEY_TOKEN, "__m__") == "__m__")        nvs_set_str(handle, GH_OTA_KEY_TOKEN, "");
    if (nvsReadString(GH_OTA_KEY_TARGET, "__m__") == "__m__")       nvs_set_str(handle, GH_OTA_KEY_TARGET, "");
    if (nvsReadString(GH_OTA_KEY_LAST_REASON, "__m__") == "__m__")  nvs_set_str(handle, GH_OTA_KEY_LAST_REASON, "");
    if (nvsReadString(GH_OTA_KEY_LAST_TGT, "__m__") == "__m__")     nvs_set_str(handle, GH_OTA_KEY_LAST_TGT, "");

    uint8_t tmpU8 = 0; uint16_t tmpU16 = 0; uint32_t tmpU32 = 0;
    if (nvs_get_u8(handle,  GH_OTA_KEY_AUTO,      &tmpU8)  != ESP_OK) nvs_set_u8(handle,  GH_OTA_KEY_AUTO,      0);
    if (nvs_get_u16(handle, GH_OTA_KEY_WIFI_FAIL,  &tmpU16) != ESP_OK) nvs_set_u16(handle, GH_OTA_KEY_WIFI_FAIL,  0);
    if (nvs_get_u16(handle, GH_OTA_KEY_CHK_FAIL,   &tmpU16) != ESP_OK) nvs_set_u16(handle, GH_OTA_KEY_CHK_FAIL,   0);
    if (nvs_get_u8(handle,  GH_OTA_KEY_WIFI_OK,   &tmpU8)  != ESP_OK) nvs_set_u8(handle,  GH_OTA_KEY_WIFI_OK,   0);
    if (nvs_get_u32(handle, GH_OTA_KEY_LAST_CHK,  &tmpU32) != ESP_OK) nvs_set_u32(handle, GH_OTA_KEY_LAST_CHK,  0);
    if (nvs_get_u32(handle, GH_OTA_KEY_BACKOFF,   &tmpU32) != ESP_OK) nvs_set_u32(handle, GH_OTA_KEY_BACKOFF,   0);
    if (nvs_get_u8(handle,  GH_OTA_KEY_REBOOT_FLG, &tmpU8)  != ESP_OK) nvs_set_u8(handle,  GH_OTA_KEY_REBOOT_FLG, 0);

    nvs_commit(handle);
    nvs_close(handle);
    s_ghOtaInitialized = true;

    if (nvsReadBool(GH_OTA_KEY_REBOOT_FLG, false)) {
        const String lastTarget = nvsReadString(GH_OTA_KEY_LAST_TGT, "unknown");
        nvsWriteBool(GH_OTA_KEY_REBOOT_FLG, false);
        telegramSendDebug(
            "[OTA][INFO] boot after GitHub OTA reboot: target=" + lastTarget +
            " current=" + String(FW_VERSION), 0);
    }
}

bool ghOtaHealthProbe() {
    if (!s_ghOtaInitialized) return false;
    if (WiFi.status() != WL_CONNECTED) return false;
    String body; int code = 0;
    const bool ok = ghHttpGet(String("https://") + OTA_GH_API_HOST + "/rate_limit", "", false, body, code);
    if (!ok) return false;
    StaticJsonDocument<512> doc;
    return deserializeJson(doc, body) == DeserializationError::Ok;
}

GhOtaCheck ghOtaCheckForUpdate(GhOtaTarget& out, bool manualOverride) {
    if (!s_ghOtaInitialized) {
        telegramSendDebug("[OTA][ERR] check failed: module not initialized", 0);
        return GhOtaCheck::Error;
    }

    const time_t now = time(nullptr);
    if (!manualOverride && now <= 100000) {
        telegramSendDebug("[OTA][WARN] check skipped: time not synced", 1);
        return GhOtaCheck::Skipped;
    }

    if (WiFi.status() != WL_CONNECTED) {
        markWifiStabilityFailure(now);
        mqttOtaEvent("ota_check_fail", OTA_REASON_WIFI_DISCONNECTED);
        return GhOtaCheck::Skipped;
    }

    if (!manualOverride) {
        if (WiFi.RSSI() < static_cast<int>(GH_OTA_WIFI_STABLE_RSSI_MIN) || !ghOtaHealthProbe()) {
            markWifiStabilityFailure(now);
            mqttOtaEvent("ota_check_fail", OTA_REASON_WIFI_UNSTABLE);
            return GhOtaCheck::Skipped;
        }
    }

    markWifiStabilitySuccess();

    if (!manualOverride && now > 100000) {
        const uint32_t backoffUntil = nvsReadU32(GH_OTA_KEY_BACKOFF, 0);
        const uint32_t lastCheck    = nvsReadU32(GH_OTA_KEY_LAST_CHK, 0);
        if (backoffUntil > static_cast<uint32_t>(now)) return GhOtaCheck::Skipped;
        if (lastCheck > 0 && (static_cast<uint32_t>(now) - lastCheck) < GH_OTA_DAILY_CHECK_SEC) return GhOtaCheck::Skipped;
    }

    mqttOtaEvent("ota_check_start", "github_release_query");

    const String token = nvsReadString(GH_OTA_KEY_TOKEN);
    DynamicJsonDocument releasesDoc(32768);
    bool releasesOk = false, releasesParseErr = false;
    int releasesCode = -1;
    for (uint8_t attempt = 0; attempt < GH_OTA_MAX_CHECK_ATTEMPTS; ++attempt) {
        releasesDoc.clear();
        releasesParseErr = false; releasesCode = -1;
        if (ghFetchReleases(token, releasesDoc, releasesParseErr, releasesCode)) { releasesOk = true; break; }
        if (attempt + 1 < GH_OTA_MAX_CHECK_ATTEMPTS) delay(GH_OTA_CHECK_RETRY_DELAY_MS);
    }

    if (!releasesOk) {
        incrementCheckFailStreak();
        String hint;
        if (releasesCode == 404)     hint = "repo not found/inaccessible";
        else if (releasesCode == 401) hint = "unauthorized (missing/invalid token)";
        else if (releasesCode == 403) hint = "forbidden/rate-limited";
        else if (releasesCode <= 0)   hint = "network/TLS/timeout";
        else if (releasesParseErr)    hint = "response parse error";
        else                          hint = "unexpected API response";
        telegramSendDebug(
            "[OTA][ERR] releases fetch failed: http=" + String(releasesCode) +
            " parse=" + String(releasesParseErr ? "yes" : "no") +
            " repo=" + String(OTA_GH_OWNER) + "/" + String(OTA_GH_REPO) +
            " hint=" + hint, 0);
        mqttOtaEvent("ota_check_fail", releasesParseErr ? OTA_REASON_GITHUB_RELEASES_PARSE : OTA_REASON_GITHUB_RELEASES_HTTP);
        return GhOtaCheck::Error;
    }

    const String channel = ghOtaGetChannel();
    const String localVersion = FW_VERSION;
    String bestVersion, bestManifestUrl, bestManifestBrowserUrl;
    bool bestPrivate = !token.isEmpty();

    for (JsonObject release : releasesDoc.as<JsonArray>()) {
        const bool prerelease = release["prerelease"] | false;
        if (channel == "stable" && prerelease) continue;
        String tag = release["tag_name"] | "";
        if (tag.isEmpty() || !tag.startsWith("v")) continue;
        String version = tag.substring(1);
        if (semVerCompare(version, localVersion) <= 0) continue;
        if (!bestVersion.isEmpty() && semVerCompare(version, bestVersion) <= 0) continue;
        JsonArray assets = release["assets"].as<JsonArray>();
        if (assets.isNull()) continue;
        String manifestApi, manifestBrowser;
        for (JsonObject asset : assets) {
            const String name = asset["name"] | "";
            if (name == "ota-manifest.json") {
                manifestApi = asset["url"] | "";
                manifestBrowser = asset["browser_download_url"] | "";
                break;
            }
        }
        if (manifestApi.isEmpty() && manifestBrowser.isEmpty()) continue;
        bestVersion = version;
        bestManifestUrl = manifestApi;
        bestManifestBrowserUrl = manifestBrowser;
    }

    if (bestVersion.isEmpty()) {
        if (now > 100000) nvsWriteU32(GH_OTA_KEY_LAST_CHK, static_cast<uint32_t>(now));
        nvsWriteU16(GH_OTA_KEY_CHK_FAIL, 0);
        mqttOtaEvent("ota_check_no_update", OTA_REASON_NO_UPDATE);
        return GhOtaCheck::NoUpdate;
    }

    // Fetch manifest
    String manifestBody; int manifestCode = 0;
    const String manifestUrl = (!token.isEmpty() && !bestManifestUrl.isEmpty()) ? bestManifestUrl : bestManifestBrowserUrl;
    const bool manifestOctet = !token.isEmpty() && !bestManifestUrl.isEmpty();
    bool manifestOk = false;
    for (uint8_t attempt = 0; attempt < GH_OTA_MAX_CHECK_ATTEMPTS; ++attempt) {
        manifestBody = ""; manifestCode = -1;
        if (ghHttpGet(manifestUrl, token, manifestOctet, manifestBody, manifestCode)) { manifestOk = true; break; }
        if (attempt + 1 < GH_OTA_MAX_CHECK_ATTEMPTS) delay(GH_OTA_CHECK_RETRY_DELAY_MS);
    }
    if (!manifestOk) {
        incrementCheckFailStreak();
        telegramSendDebug("[OTA][ERR] manifest fetch failed: http=" + String(manifestCode) + " url=" + manifestUrl, 0);
        mqttOtaEvent("ota_check_fail", OTA_REASON_MANIFEST_HTTP);
        return GhOtaCheck::Error;
    }

    StaticJsonDocument<2048> manifest;
    if (deserializeJson(manifest, manifestBody) != DeserializationError::Ok) {
        incrementCheckFailStreak();
        telegramSendDebug("[OTA][ERR] manifest parse failed: bytes=" + String(manifestBody.length()), 0);
        mqttOtaEvent("ota_check_fail", OTA_REASON_MANIFEST_PARSE);
        return GhOtaCheck::Error;
    }

    const String binAssetName = manifest["bin_asset_name"] | "";
    const String sha256       = manifest["sha256"] | "";
    const float  minBattery   = manifest["min_battery_v"] | 0.0f;
    if (binAssetName.isEmpty() || sha256.isEmpty()) {
        incrementCheckFailStreak();
        telegramSendDebug("[OTA][ERR] manifest missing fields", 0);
        mqttOtaEvent("ota_check_fail", OTA_REASON_MANIFEST_MISSING_FIELDS);
        return GhOtaCheck::Error;
    }

    // Resolve binary URL from releases list
    String binApiUrl, binBrowserUrl;
    for (JsonObject release : releasesDoc.as<JsonArray>()) {
        String tag = release["tag_name"] | "";
        if (tag != ("v" + bestVersion)) continue;
        JsonArray assets = release["assets"].as<JsonArray>();
        if (assets.isNull()) break;
        for (JsonObject asset : assets) {
            const String assetName = asset["name"] | "";
            if (assetName == binAssetName) {
                binApiUrl     = asset["url"] | "";
                binBrowserUrl = asset["browser_download_url"] | "";
                break;
            }
        }
        break;
    }

    const String binUrl = (!token.isEmpty() && !binApiUrl.isEmpty()) ? binApiUrl : binBrowserUrl;
    if (binUrl.isEmpty()) {
        incrementCheckFailStreak();
        telegramSendDebug("[OTA][ERR] binary asset not found: version=" + bestVersion + " asset=" + binAssetName, 0);
        mqttOtaEvent("ota_check_fail", OTA_REASON_BIN_ASSET_NOT_FOUND);
        return GhOtaCheck::Error;
    }

    out.version       = bestVersion;
    out.channel       = channel;
    out.binAssetUrl   = binUrl;
    out.sha256        = sha256;
    out.minBatteryV   = minBattery;
    out.isPrivateRepo = !token.isEmpty() && !binApiUrl.isEmpty() && bestPrivate;

    if (now > 100000) nvsWriteU32(GH_OTA_KEY_LAST_CHK, static_cast<uint32_t>(now));
    nvsWriteU16(GH_OTA_KEY_CHK_FAIL, 0);
    savePendingTarget(out, "");
    mqttOtaEvent("ota_update_available", OTA_REASON_UPDATE_FOUND, bestVersion);
    return GhOtaCheck::UpdateAvailable;
}

bool ghOtaInstall(const GhOtaTarget& target, bool manualOverride) {
    if (!s_ghOtaInitialized) return false;
    if (target.version.isEmpty() || target.binAssetUrl.isEmpty()) return false;

    telegramSendDebug("[OTA][DBG] install entry: target=" + target.version, 2);
    if (telegramIsMaintMode()) telegramSendDebug("[OTA][INFO] maintenance mode active: install allowed", 1);

    const float battery   = batteryReadVoltage();
    const float threshold = (target.minBatteryV > GH_OTA_MIN_INSTALL_BATTERY_V) ? target.minBatteryV : GH_OTA_MIN_INSTALL_BATTERY_V;
    if (battery > 0.0f && battery < threshold) {
        savePendingTarget(target, "battery_low");
        mqttOtaEvent("ota_install_blocked", OTA_REASON_BATTERY_LOW, target.version);
        telegramSendDebug("[OTA][WARN] install blocked: battery " + String(battery, 2) + "V below " + String(threshold, 2) + "V", 1);
        return false;
    }

    const wl_status_t wifiStatus = WiFi.status();
    const long rssi = WiFi.RSSI();
    if (!manualOverride) {
        const bool healthOk = ghOtaHealthProbe();
        if (wifiStatus != WL_CONNECTED || rssi < GH_OTA_WIFI_STABLE_RSSI_MIN || !healthOk) {
            savePendingTarget(target, "wifi_unstable");
            mqttOtaEvent("ota_install_blocked", OTA_REASON_WIFI_UNSTABLE, target.version);
            telegramSendDebug("[OTA][WARN] install blocked: WiFi unstable rssi=" + String(rssi) + " health=" + String(healthOk ? "ok" : "fail"), 1);
            return false;
        }
    } else {
        telegramSendDebug("[OTA][INFO] manual install: WiFi gate bypassed rssi=" + String(rssi), 1);
    }

    const String installToken = target.isPrivateRepo ? nvsReadString(GH_OTA_KEY_TOKEN, "") : "";
    if (target.isPrivateRepo && installToken.isEmpty()) {
        savePendingTarget(target, "token_missing_for_private_target");
        mqttOtaEvent("ota_install_blocked", OTA_REASON_TOKEN_MISSING_FOR_PRIVATE_TARGET, target.version);
        telegramSendDebug("[OTA][WARN] install blocked: private target requires token", 1);
        return false;
    }

    const esp_partition_t* updatePartition = esp_ota_get_next_update_partition(nullptr);
    if (updatePartition == nullptr) {
        savePendingTarget(target, "no_update_partition");
        mqttOtaEvent("ota_update_fail", OTA_REASON_NO_UPDATE_PARTITION, target.version);
        telegramSendDebug("[OTA][ERR] no OTA update partition available", 0);
        return false;
    }

    uint8_t expectedSha[32] = {0};
    if (!parseSha256ToBytes(target.sha256, expectedSha)) {
        savePendingTarget(target, "manifest_sha256_invalid");
        mqttOtaEvent("ota_update_fail", OTA_REASON_MANIFEST_SHA256_INVALID, target.version);
        telegramSendDebug("[OTA][ERR] invalid manifest sha256 format", 0);
        return false;
    }

    mqttOtaEvent("ota_update_start", OTA_REASON_INSTALL_START, target.version);
    telegramSendDebug("[OTA][INFO] starting GitHub OTA install: target=" + target.version, 1);

    WiFiClientSecure dlClient;
    dlClient.setInsecure();
    dlClient.setTimeout(20000);
    HTTPClient dlHttp;
    int httpStatus = -1, contentLength = -1;
    bool requestStarted = false;

    constexpr uint8_t kGetAttempts = 3;
    for (uint8_t attempt = 1; attempt <= kGetAttempts; ++attempt) {
        if (dlHttp.begin(dlClient, target.binAssetUrl)) {
            dlHttp.setTimeout(20000);
            dlHttp.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
            dlHttp.addHeader("User-Agent", "BirdNest-OTA");
            dlHttp.addHeader("X-GitHub-Api-Version", "2022-11-28");
            dlHttp.addHeader("Accept", "application/octet-stream");
            if (target.isPrivateRepo) dlHttp.addHeader("Authorization", "Bearer " + installToken);
            httpStatus = dlHttp.GET();
            if (httpStatus >= 200 && httpStatus < 300) {
                requestStarted = true;
                contentLength = dlHttp.getSize();
                break;
            }
            telegramSendDebug("[OTA][WARN] HTTP GET attempt " + String(attempt) + "/" + String(kGetAttempts) + " failed, code=" + String(httpStatus), 1);
            dlHttp.end();
        }
        if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();
        if (attempt < kGetAttempts) delay(700);
    }

    if (!requestStarted) {
        savePendingTarget(target, "ota_begin_failed");
        mqttOtaEvent("ota_update_fail", OTA_REASON_OTA_BEGIN_FAILED, target.version);
        telegramSendDebug("[OTA][ERR] OTA download open failed code=" + String(httpStatus), 0);
        dlHttp.end();
        return false;
    }

    esp_ota_handle_t otaHandle = 0;
    esp_err_t err = esp_ota_begin(updatePartition, OTA_SIZE_UNKNOWN, &otaHandle);
    if (err != ESP_OK) {
        dlHttp.end();
        savePendingTarget(target, "ota_begin_failed");
        mqttOtaEvent("ota_update_fail", OTA_REASON_OTA_BEGIN_FAILED, target.version);
        telegramSendDebug("[OTA][ERR] esp_ota_begin failed, err=" + String(static_cast<int>(err)), 0);
        return false;
    }

    auto abortInstall = [&](const String& pendingReason, const char* reasonCode, const String& logMsg) -> bool {
        esp_ota_abort(otaHandle);
        dlHttp.end();
        savePendingTarget(target, pendingReason);
        mqttOtaEvent("ota_update_fail", reasonCode, target.version);
        telegramSendDebug(logMsg, 0);
        return false;
    };

    mbedtls_sha256_context shaCtx;
    mbedtls_sha256_init(&shaCtx);
    if (mbedtls_sha256_starts_ret(&shaCtx, 0) != 0) {
        mbedtls_sha256_free(&shaCtx);
        return abortInstall("sha_ctx_init_failed", OTA_REASON_OTA_BEGIN_FAILED, "[OTA][ERR] sha256 init failed");
    }

    int64_t totalRead = 0;
    int lastProgress = -1;
    WiFiClient* dlStream = dlHttp.getStreamPtr();
    if (!dlStream) {
        mbedtls_sha256_free(&shaCtx);
        return abortInstall("download_stream_missing", OTA_REASON_DOWNLOAD_NETWORK_INTERRUPTED, "[OTA][ERR] download stream pointer is null");
    }

    const unsigned long streamStallTimeoutMs = 20000UL;
    unsigned long lastStreamReadMs = millis();

    while (true) {
        int available = dlStream->available();
        if (available <= 0) {
            if (contentLength >= 0 && totalRead >= contentLength) break;
            if (!dlHttp.connected()) break;
            if ((millis() - lastStreamReadMs) > streamStallTimeoutMs) {
                mbedtls_sha256_free(&shaCtx);
                const char* reason = (WiFi.status() == WL_CONNECTED) ? OTA_REASON_DOWNLOAD_NETWORK_INTERRUPTED : OTA_REASON_WIFI_DISCONNECTED;
                return abortInstall("download_network_interrupted", reason, "[OTA][ERR] download stream stalled");
            }
            delay(10); continue;
        }
        if (available > static_cast<int>(sizeof(s_otaDownloadBuf))) available = static_cast<int>(sizeof(s_otaDownloadBuf));
        const int bytesRead = dlStream->readBytes(reinterpret_cast<char*>(s_otaDownloadBuf), static_cast<size_t>(available));
        if (bytesRead <= 0) {
            if ((millis() - lastStreamReadMs) > streamStallTimeoutMs) {
                mbedtls_sha256_free(&shaCtx);
                const char* reason = (WiFi.status() == WL_CONNECTED) ? OTA_REASON_DOWNLOAD_NETWORK_INTERRUPTED : OTA_REASON_WIFI_DISCONNECTED;
                return abortInstall("download_network_interrupted", reason, "[OTA][ERR] download read timeout");
            }
            delay(5); continue;
        }
        lastStreamReadMs = millis();

        if (mbedtls_sha256_update_ret(&shaCtx, s_otaDownloadBuf, static_cast<size_t>(bytesRead)) != 0) {
            mbedtls_sha256_free(&shaCtx);
            return abortInstall("sha_update_failed", OTA_REASON_OTA_BEGIN_FAILED, "[OTA][ERR] sha256 update failed");
        }
        err = esp_ota_write(otaHandle, s_otaDownloadBuf, static_cast<size_t>(bytesRead));
        if (err != ESP_OK) {
            mbedtls_sha256_free(&shaCtx);
            return abortInstall("flash_write_failed", OTA_REASON_FLASH_WRITE_FAILED, "[OTA][ERR] esp_ota_write failed, err=" + String(static_cast<int>(err)));
        }
        totalRead += bytesRead;
        if (contentLength > 0) {
            const int progress = static_cast<int>((totalRead * 100) / contentLength);
            if (progress >= 0 && progress <= 100 && progress / 10 != lastProgress / 10) {
                lastProgress = progress;
                mqttOtaEvent("ota_update_progress", String(progress), target.version);
                telegramSendDebug("[OTA][DBG] install progress=" + String(progress) + "%", 2);
            }
        }
    }

    if (contentLength > 0 && totalRead != contentLength) {
        mbedtls_sha256_free(&shaCtx);
        return abortInstall("size_mismatch", OTA_REASON_SIZE_MISMATCH,
                            "[OTA][ERR] size mismatch: expected=" + String(contentLength) + " read=" + String(static_cast<long>(totalRead)));
    }

    uint8_t actualSha[32] = {0};
    if (mbedtls_sha256_finish_ret(&shaCtx, actualSha) != 0) {
        mbedtls_sha256_free(&shaCtx);
        return abortInstall("sha_finish_failed", OTA_REASON_OTA_FINISH_FAILED, "[OTA][ERR] sha256 finish failed");
    }
    mbedtls_sha256_free(&shaCtx);

    if (memcmp(actualSha, expectedSha, sizeof(actualSha)) != 0) {
        return abortInstall("sha256_mismatch", OTA_REASON_SHA256_MISMATCH, "[OTA][ERR] sha256 mismatch");
    }

    dlHttp.end();

    err = esp_ota_end(otaHandle);
    if (err != ESP_OK) {
        savePendingTarget(target, "ota_finish_failed");
        mqttOtaEvent("ota_update_fail", OTA_REASON_OTA_FINISH_FAILED, target.version);
        telegramSendDebug("[OTA][ERR] esp_ota_end failed, err=" + String(static_cast<int>(err)), 0);
        return false;
    }

    err = esp_ota_set_boot_partition(updatePartition);
    if (err != ESP_OK) {
        savePendingTarget(target, "ota_finish_failed");
        mqttOtaEvent("ota_update_fail", OTA_REASON_OTA_FINISH_FAILED, target.version);
        telegramSendDebug("[OTA][ERR] esp_ota_set_boot_partition failed, err=" + String(static_cast<int>(err)), 0);
        return false;
    }

    clearPendingTarget();
    setLastOtaReason("");
    nvsWriteString(GH_OTA_KEY_LAST_TGT, target.version);
    nvsWriteBool(GH_OTA_KEY_REBOOT_FLG, true);
    telegramSendDebug("[OTA][INFO] install finished, rebooting into " + target.version, 1);
    delay(200);
    ESP.restart();
    return true;
}

void ghOtaConfirmHealthIfPending() {
    const esp_partition_t* running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (esp_ota_get_state_partition(running, &state) != ESP_OK) return;
    if (state != ESP_OTA_IMG_PENDING_VERIFY) return;

    constexpr uint8_t  kAttempts = 3;
    constexpr uint32_t kDelayMs  = 2000;
    bool ok = false;
    for (uint8_t i = 0; i < kAttempts; ++i) {
        if (WiFi.status() == WL_CONNECTED && ghOtaHealthProbe()) { ok = true; break; }
        if (i + 1 < kAttempts) delay(kDelayMs);
    }

    const esp_err_t markErr = esp_ota_mark_app_valid_cancel_rollback();
    if (markErr == ESP_OK) {
        if (ok) {
            mqttOtaEvent("ota_update_ok", OTA_REASON_HEALTH_CONFIRMED, FW_VERSION);
            telegramSendDebug("[OTA][INFO] image confirmed healthy current=" + String(FW_VERSION), 1);
        } else {
            mqttOtaEvent("ota_update_ok", OTA_REASON_HEALTH_CONFIRMED_DEGRADED, FW_VERSION);
            mqttOtaEvent("ota_check_fail", OTA_REASON_HEALTH_PROBE_FAILED, FW_VERSION);
            telegramSendDebug("[OTA][WARN] health probe failed, rollback suppressed to preserve device", 0);
        }
        clearPendingTarget();
        return;
    }
    telegramSendDebug("[OTA][ALERT] failed to cancel rollback, err=" + String(static_cast<int>(markErr)), 0);
}

String ghOtaStatusJson() {
    StaticJsonDocument<768> doc;
    doc["current_version"]   = FW_VERSION;
    doc["channel"]           = ghOtaGetChannel();
    doc["auto"]              = ghOtaIsAutoEnabled();
    doc["last_check"]        = nvsReadU32(GH_OTA_KEY_LAST_CHK, 0);
    doc["wifi_fail_streak"]  = nvsReadU16(GH_OTA_KEY_WIFI_FAIL, 0);
    doc["check_fail_streak"] = nvsReadU16(GH_OTA_KEY_CHK_FAIL, 0);
    doc["backoff_until"]     = nvsReadU32(GH_OTA_KEY_BACKOFF, 0);
    const String lastReason  = nvsReadString(GH_OTA_KEY_LAST_REASON, "");
    doc["last_reason"]       = lastReason.isEmpty() ? nullptr : (const char*)lastReason.c_str();

    const String pending = nvsReadString(GH_OTA_KEY_TARGET, "");
    if (pending.isEmpty()) {
        doc["pending_target"] = nullptr;
        doc["pending_reason"] = lastReason.isEmpty() ? nullptr : (const char*)lastReason.c_str();
    } else {
        StaticJsonDocument<512> pendingDoc;
        if (deserializeJson(pendingDoc, pending) == DeserializationError::Ok) {
            const String pendingReason = pendingDoc["pending_reason"] | "";
            doc["pending_target"] = pendingDoc["version"] | nullptr;
            const String reason = !pendingReason.isEmpty() ? pendingReason : lastReason;
            doc["pending_reason"] = reason.isEmpty() ? nullptr : (const char*)reason.c_str();
        } else {
            doc["pending_target"] = "unknown";
            doc["pending_reason"] = "parse_error";
        }
    }

    String out;
    serializeJson(doc, out);
    return out;
}

bool ghOtaGetPendingTarget(GhOtaTarget& out) {
    if (!s_ghOtaInitialized) return false;
    return loadPendingTargetFromNvs(out);
}

String ghOtaGetPendingReason() {
    if (!s_ghOtaInitialized) return "";
    const String pending = nvsReadString(GH_OTA_KEY_TARGET, "");
    if (pending.isEmpty()) return nvsReadString(GH_OTA_KEY_LAST_REASON, "");
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, pending) != DeserializationError::Ok) return nvsReadString(GH_OTA_KEY_LAST_REASON, "");
    const String reason = doc["pending_reason"] | "";
    return !reason.isEmpty() ? reason : nvsReadString(GH_OTA_KEY_LAST_REASON, "");
}

bool ghOtaSetAutoEnabled(bool enabled) { nvsWriteBool(GH_OTA_KEY_AUTO, enabled); return true; }
bool ghOtaIsAutoEnabled()               { return nvsReadBool(GH_OTA_KEY_AUTO, false); }

bool ghOtaSetChannel(const String& channelRaw) {
    String channel = channelRaw; channel.trim(); channel.toLowerCase();
    if (channel != "stable" && channel != "beta") return false;
    nvsWriteString(GH_OTA_KEY_CHANNEL, channel);
    return true;
}

String ghOtaGetChannel() {
    String channel = nvsReadString(GH_OTA_KEY_CHANNEL, "stable");
    channel.toLowerCase();
    return (channel != "stable" && channel != "beta") ? "stable" : channel;
}

bool ghOtaSetToken(const String& tokenRaw) {
    String token = tokenRaw; token.trim();
    if (token.length() < 10 || token.length() > 200) return false;
    nvsWriteString(GH_OTA_KEY_TOKEN, token);
    return true;
}

bool ghOtaClearToken(bool* droppedPendingPrivateTarget) {
    if (droppedPendingPrivateTarget) *droppedPendingPrivateTarget = false;
    nvsWriteString(GH_OTA_KEY_TOKEN, "");
    const String pending = nvsReadString(GH_OTA_KEY_TARGET, "");
    if (pending.isEmpty()) return true;
    StaticJsonDocument<512> pendingDoc;
    if (deserializeJson(pendingDoc, pending) != DeserializationError::Ok) return true;
    const bool privateTarget = pendingDoc["is_private_repo"] | false;
    if (!privateTarget) return true;
    const String pendingVersion = pendingDoc["version"] | "";
    clearPendingTarget();
    if (droppedPendingPrivateTarget) *droppedPendingPrivateTarget = true;
    mqttOtaEvent("ota_install_blocked", OTA_REASON_TOKEN_MISSING_FOR_PRIVATE_TARGET, pendingVersion);
    return true;
}

bool ghOtaHasToken() { return !nvsReadString(GH_OTA_KEY_TOKEN, "").isEmpty(); }
