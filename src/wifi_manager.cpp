#include "wifi_manager.h"
#include "config.h"

#include <WiFi.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <Arduino.h>

// ============================================================
// Internal state – static, only visible in this translation unit
// ============================================================

static char s_botToken[BOT_TOKEN_LEN]  = {0};
static char s_chatId[CHAT_ID_LEN]      = {0};
static char s_debugChatId[CHAT_ID_LEN] = {0};

static bool s_shouldSave = false;

// ============================================================
// NVS (Preferences) helpers
// ============================================================

static void loadFromNVS() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/true);
    prefs.getString("botToken",    s_botToken,    sizeof(s_botToken));
    prefs.getString("chatId",      s_chatId,      sizeof(s_chatId));
    prefs.getString("debugChatId", s_debugChatId, sizeof(s_debugChatId));
    prefs.end();
}

static void saveToNVS() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.putString("botToken",    s_botToken);
    prefs.putString("chatId",      s_chatId);
    prefs.putString("debugChatId", s_debugChatId);
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

    WiFiManager wm;
    wm.setConfigPortalTimeout(CONFIG_PORTAL_TIMEOUT);
    wm.setSaveConfigCallback(onSaveConfig);

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

    bool connected = wm.autoConnect(AP_NAME, AP_PASSWORD);

    if (!connected) {
        return false;
    }

    // OTA is sensitive to modem sleep on ESP32-CAM. Keep the radio fully awake.
    WiFi.setSleep(false);

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
