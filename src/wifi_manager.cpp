#include "wifi_manager.h"
#include "config.h"

#include <WiFi.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <Arduino.h>
#include <ctype.h>

#ifndef WIFI_RESCUE_FAIL_COUNT
    #define WIFI_RESCUE_FAIL_COUNT 12
#endif
#ifndef WIFI_RESCUE_PORTAL_INTERVAL_FAILS
    #define WIFI_RESCUE_PORTAL_INTERVAL_FAILS 24
#endif
#ifndef WIFI_RESCUE_PORTAL_TIMEOUT
    #define WIFI_RESCUE_PORTAL_TIMEOUT 180
#endif

static constexpr uint16_t kWifiRescueFailCount = WIFI_RESCUE_FAIL_COUNT;
static constexpr uint16_t kWifiRescuePortalIntervalFails = WIFI_RESCUE_PORTAL_INTERVAL_FAILS;
static constexpr int kWifiRescuePortalTimeout = WIFI_RESCUE_PORTAL_TIMEOUT;

// ============================================================
// Internal state – static, only visible in this translation unit
// ============================================================

static char s_botToken[BOT_TOKEN_LEN]  = {0};
static char s_chatId[CHAT_ID_LEN]      = {0};
static char s_debugChatId[CHAT_ID_LEN] = {0};
static char s_deviceLabel[48]          = {0};
static char s_otaHostname[48]          = {0};
static char s_apName[48]               = {0};

static bool s_shouldSave = false;

static String makeDeviceSuffix() {
    const uint64_t chipId = ESP.getEfuseMac();
    const uint32_t shortId = static_cast<uint32_t>(chipId & 0xFFFFFFFFUL);
    char buf[9];
    snprintf(buf, sizeof(buf), "%08lx", static_cast<unsigned long>(shortId));
    return String(buf);
}

static String sanitizeHostname(const String& input) {
    String out;
    out.reserve(input.length());
    for (size_t i = 0; i < input.length(); ++i) {
        char c = static_cast<char>(tolower(static_cast<unsigned char>(input.charAt(i))));
        const bool alnum = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
        if (alnum || c == '-') {
            out += c;
        } else if (c == ' ' || c == '_' || c == '.') {
            out += '-';
        }
    }

    while (out.length() > 0 && out.charAt(0) == '-') out.remove(0, 1);
    while (out.length() > 0 && out.charAt(out.length() - 1) == '-') out.remove(out.length() - 1, 1);
    while (out.indexOf("--") >= 0) out.replace("--", "-");
    if (out.length() > 32) out.remove(32);
    return out;
}

static String sanitizeLabel(const String& input) {
    String out = input;
    out.trim();
    for (size_t i = 0; i < out.length(); ++i) {
        const char c = out.charAt(i);
        if (static_cast<unsigned char>(c) < 32 || static_cast<unsigned char>(c) == 127) {
            out.setCharAt(i, ' ');
        }
    }
    while (out.indexOf("  ") >= 0) out.replace("  ", " ");
    if (out.length() > 40) out.remove(40);
    return out;
}

static void refreshApNameFromLabel() {
    const String label = String(s_deviceLabel);
    String ap = sanitizeHostname(label);
    if (ap.isEmpty()) {
        ap = String("birdnest-") + makeDeviceSuffix();
    }
    ap += "-cfg";
    if (ap.length() > 31) ap.remove(31);
    strncpy(s_apName, ap.c_str(), sizeof(s_apName) - 1);
    s_apName[sizeof(s_apName) - 1] = '\0';
}

static uint16_t loadWiFiFailCount() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/true);
    uint16_t failCount = prefs.getUShort("wifiFail", 0);
    prefs.end();
    return failCount;
}

static void saveWiFiFailCount(uint16_t failCount) {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.putUShort("wifiFail", failCount);
    prefs.end();
}

static void recordWiFiConnectSuccess() {
    saveWiFiFailCount(0);
}

static uint16_t recordWiFiConnectFailure() {
    uint16_t failCount = loadWiFiFailCount();
    if (failCount < 65535) ++failCount;
    saveWiFiFailCount(failCount);
    return failCount;
}

static bool shouldOpenRescuePortal(bool missingTelegramFields, uint16_t failCount) {
    if (missingTelegramFields) return true;
    if (WIFI_ENABLE_CAPTIVE_PORTAL != 0) return true;
    if (failCount < kWifiRescueFailCount) return false;
    if (kWifiRescuePortalIntervalFails == 0) return true;

    return ((failCount - kWifiRescueFailCount) % kWifiRescuePortalIntervalFails) == 0;
}

static bool hasAllTelegramFields() {
    return s_botToken[0] != '\0' &&
           s_chatId[0] != '\0' &&
           s_debugChatId[0] != '\0';
}

// ============================================================
// NVS (Preferences) helpers
// ============================================================

static void loadFromNVS() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/true);
    prefs.getString("botToken",    s_botToken,    sizeof(s_botToken));
    prefs.getString("chatId",      s_chatId,      sizeof(s_chatId));
    prefs.getString("debugChatId", s_debugChatId, sizeof(s_debugChatId));
    prefs.getString("devLabel",    s_deviceLabel, sizeof(s_deviceLabel));
    prefs.getString("otaHost",     s_otaHostname, sizeof(s_otaHostname));
    prefs.end();

    if (s_deviceLabel[0] == '\0') {
        const String fallback = String("BirdNest-") + makeDeviceSuffix();
        strncpy(s_deviceLabel, fallback.c_str(), sizeof(s_deviceLabel) - 1);
        s_deviceLabel[sizeof(s_deviceLabel) - 1] = '\0';
    }

    if (s_otaHostname[0] == '\0') {
        String fallback = String("birdnest-") + makeDeviceSuffix();
        fallback = sanitizeHostname(fallback);
        strncpy(s_otaHostname, fallback.c_str(), sizeof(s_otaHostname) - 1);
        s_otaHostname[sizeof(s_otaHostname) - 1] = '\0';
    }

    refreshApNameFromLabel();
}

static void saveToNVS() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.putString("botToken",    s_botToken);
    prefs.putString("chatId",      s_chatId);
    prefs.putString("debugChatId", s_debugChatId);
    prefs.putString("devLabel",    s_deviceLabel);
    prefs.putString("otaHost",     s_otaHostname);
    prefs.end();
}

// ============================================================
// WiFiManager callback – called when portal saves settings
// ============================================================

static void onSaveConfig() {
    s_shouldSave = true;
}

// ============================================================
// Public API
// ============================================================

bool wifiInit() {
    loadFromNVS();
    uint16_t failCount = loadWiFiFailCount();
    bool failureRecordedThisBoot = false;

    // Safety fallback: if Telegram IDs are missing, force portal mode so
    // credentials can be entered remotely without reflashing.
    bool missingTelegramFields = !hasAllTelegramFields();

    // Remote deployment mode: avoid long-lived captive portal sessions.
    if (WIFI_ENABLE_CAPTIVE_PORTAL == 0 && !missingTelegramFields) {
        WiFi.mode(WIFI_STA);
        WiFi.begin(); // Use credentials saved by WiFi stack

        unsigned long start = millis();
        const unsigned long timeoutMs = static_cast<unsigned long>(WIFI_FAIL_FAST_SEC) * 1000UL;
        while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeoutMs) {
            delay(100);
        }

        if (WiFi.status() != WL_CONNECTED) {
            failCount = recordWiFiConnectFailure();
            failureRecordedThisBoot = true;
            if (!shouldOpenRescuePortal(missingTelegramFields, failCount)) {
                return false;
            }

            Serial.println("[WIFI] repeated STA failures - opening rescue portal");
        } else {
            // OTA is sensitive to modem sleep on ESP32-CAM. Keep the radio fully awake.
            WiFi.setSleep(false);
            recordWiFiConnectSuccess();
            return true;
        }
    }

    WiFiManager wm;
    const int portalTimeout = shouldOpenRescuePortal(missingTelegramFields, failCount)
        ? kWifiRescuePortalTimeout
        : CONFIG_PORTAL_TIMEOUT;
    wm.setConfigPortalTimeout(portalTimeout);
    wm.setSaveConfigCallback(onSaveConfig);

    if (missingTelegramFields) {
        Serial.println("[WIFI] Telegram credentials missing - opening config portal");
    } else if (failCount >= kWifiRescueFailCount) {
        Serial.println("[WIFI] rescue portal window open after " + String(failCount) + " failed WiFi boots");
    }

    // Custom fields shown on the captive portal page
    WiFiManagerParameter paramToken(
        "botToken",    "Telegram Bot Token", s_botToken,    BOT_TOKEN_LEN - 1);
    WiFiManagerParameter paramChat(
        "chatId",      "Chat ID",            s_chatId,      CHAT_ID_LEN - 1);
    WiFiManagerParameter paramDebug(
        "debugChatId", "Debug Chat ID",      s_debugChatId, CHAT_ID_LEN - 1);

    wm.addParameter(&paramToken);
    wm.addParameter(&paramChat);
    wm.addParameter(&paramDebug);

    // If Telegram credentials are missing, force AP portal even when WiFi STA
    // credentials are valid. autoConnect() would otherwise skip the portal.
    bool connected = missingTelegramFields
        ? wm.startConfigPortal(s_apName, AP_PASSWORD)
        : wm.autoConnect(s_apName, AP_PASSWORD);

    if (!connected) {
        if (!failureRecordedThisBoot) {
            recordWiFiConnectFailure();
        }
        return false;
    }

    // OTA is sensitive to modem sleep on ESP32-CAM. Keep the radio fully awake.
    WiFi.setSleep(false);
    recordWiFiConnectSuccess();

    // If the portal saved new values, update buffers and persist to NVS
    if (s_shouldSave) {
        strncpy(s_botToken,    paramToken.getValue(), sizeof(s_botToken) - 1);
        strncpy(s_chatId,      paramChat.getValue(),  sizeof(s_chatId) - 1);
        strncpy(s_debugChatId, paramDebug.getValue(), sizeof(s_debugChatId) - 1);
        s_botToken[sizeof(s_botToken) - 1]       = '\0';
        s_chatId[sizeof(s_chatId) - 1]           = '\0';
        s_debugChatId[sizeof(s_debugChatId) - 1] = '\0';
        saveToNVS();
        s_shouldSave = false;
    }

    return true;
}

void wifiReset() {
    WiFiManager wm;
    wm.resetSettings();
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, false);
    prefs.clear();
    prefs.end();
    delay(500);
    ESP.restart();
}

const char* getBotToken()    { return s_botToken; }
const char* getChatId()      { return s_chatId; }
const char* getDebugChatId() { return s_debugChatId; }
const char* getDeviceLabel() { return s_deviceLabel; }
const char* getOtaHostname() { return s_otaHostname; }
const char* getApName()      { return s_apName; }

bool setDeviceLabel(const String& label) {
    const String normalized = sanitizeLabel(label);
    if (normalized.isEmpty()) return false;

    strncpy(s_deviceLabel, normalized.c_str(), sizeof(s_deviceLabel) - 1);
    s_deviceLabel[sizeof(s_deviceLabel) - 1] = '\0';
    refreshApNameFromLabel();
    saveToNVS();
    return true;
}

bool setOtaHostname(const String& hostname) {
    const String normalized = sanitizeHostname(hostname);
    if (normalized.isEmpty()) return false;

    strncpy(s_otaHostname, normalized.c_str(), sizeof(s_otaHostname) - 1);
    s_otaHostname[sizeof(s_otaHostname) - 1] = '\0';
    saveToNVS();
    return true;
}
