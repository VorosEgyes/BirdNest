#ifndef GH_OTA_H
#define GH_OTA_H

#include <Arduino.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>

// ============================================================
// GitHub-based OTA module for BirdNest
// Ported from RaisedGarden. Logic is identical; only NVS
// namespace and User-Agent differ.
// ============================================================

// NVS namespace for all GitHub OTA keys (max 15 chars)
#define GH_OTA_NVS_NAMESPACE "birdnest_gh"

// NVS key names (max 15 chars each)
#define GH_OTA_KEY_AUTO        "otaAuto"
#define GH_OTA_KEY_CHANNEL     "otaChannel"
#define GH_OTA_KEY_TOKEN       "otaToken"
#define GH_OTA_KEY_LAST_CHK    "otaLastChk"
#define GH_OTA_KEY_WIFI_FAIL   "otaWifiFail"
#define GH_OTA_KEY_CHK_FAIL    "otaChkFail"
#define GH_OTA_KEY_BACKOFF     "otaBackoff"
#define GH_OTA_KEY_TARGET      "otaTarget"
#define GH_OTA_KEY_WIFI_OK     "otaWifiOk"
#define GH_OTA_KEY_LAST_REASON "otaLastReason"

// ============================================================
// Enums and Structs
// ============================================================

enum class GhOtaCheck {
    NoUpdate,
    UpdateAvailable,
    Skipped,
    Error
};

struct GhOtaTarget {
    String version;
    String channel;
    String binAssetUrl;
    String sha256;
    float  minBatteryV;
    bool   isPrivateRepo;
};

// ============================================================
// Public API
// ============================================================

// Must be called once during setup() after WiFi connects.
// Idempotent; safe to call multiple times (lazy init guard).
void ghOtaInit();

// Check for a newer release on GitHub.
// manualOverride=true: bypass daily interval and backoff gates.
GhOtaCheck ghOtaCheckForUpdate(GhOtaTarget& out, bool manualOverride = false);

// Download, verify and flash a previously fetched target.
// manualOverride=true: bypass WiFi stability gate.
bool ghOtaInstall(const GhOtaTarget& target, bool manualOverride = false);

// Short HTTPS health probe to api.github.com/rate_limit.
bool ghOtaHealthProbe();

// Post-boot rollback confirmation. Call once if image state is PENDING_VERIFY.
void ghOtaConfirmHealthIfPending();

// JSON status string for /otastatus and MQTT telemetry.
String ghOtaStatusJson();

// Retrieve pending install target from NVS (set after check, cleared after install).
bool ghOtaGetPendingTarget(GhOtaTarget& out);
String ghOtaGetPendingReason();

// Runtime settings (NVS-persisted, changeable via Telegram commands).
bool   ghOtaSetAutoEnabled(bool enabled);
bool   ghOtaIsAutoEnabled();
bool   ghOtaSetChannel(const String& channel);
String ghOtaGetChannel();
bool   ghOtaSetToken(const String& token);
bool   ghOtaClearToken(bool* droppedPendingPrivateTarget = nullptr);
bool   ghOtaHasToken();

#endif // GH_OTA_H
