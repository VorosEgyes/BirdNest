#include "telegram.h"
#include "wifi_manager.h"
#include "config.h"
#include "temperature.h"
#include "battery.h"
#include "ota.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <UniversalTelegramBot.h>
#include <Arduino.h>
#include <Preferences.h>

// static objects, not pointers, token set at construct time.
static WiFiClientSecure s_client;
static String           s_token;
static UniversalTelegramBot* s_bot = nullptr;

static const unsigned long BOT_POLL_INTERVAL_MS  = 5000UL; // 5s – saves radio vs 1s polling

static unsigned long s_lastBotCheck  = 0;
static bool          s_maintMode     = false;
static uint32_t      s_sleepSec      = DEEP_SLEEP_SEC;
static uint8_t       s_debugVerbosity = 2; // 0=minimal, 1=normal, 2=verbose
static bool          s_camMirror     = true;
static bool          s_camFlip       = false;
static int32_t       s_lastMessageId = 0;  // Last processed Telegram update_id
static bool          s_lastMsgDirty  = false;
static unsigned long s_lastMsgPersistMs = 0;
typedef void (*PhotoCallback)(const char*);
static PhotoCallback s_photoCb       = nullptr;
static SleepCallback s_sleepCb       = nullptr;

static const uint16_t STARTUP_MSG_PROCESS_LIMIT = 20;
static const unsigned long STARTUP_MSG_TIME_LIMIT_MS = 10000UL;
static const unsigned long LAST_MSG_PERSIST_INTERVAL_MS = 30000UL;

static void persistLastMessageId(bool force = false) {
    if (!s_lastMsgDirty) return;

    unsigned long now = millis();
    if (!force && (now - s_lastMsgPersistMs) < LAST_MSG_PERSIST_INTERVAL_MS) {
        return;
    }

    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.putLong("lastMsgId", s_lastMessageId);
    prefs.end();

    s_lastMsgDirty = false;
    s_lastMsgPersistMs = now;
}

static void loadRuntimeConfig() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/true);
    s_sleepSec = prefs.getUInt("sleepSec", DEEP_SLEEP_SEC);
    s_maintMode = prefs.getBool("maintMode", false);
    s_debugVerbosity = prefs.getUChar("dbgVerb", 2);
    s_camMirror = prefs.getBool("camMirror", true);
    s_camFlip = prefs.getBool("camFlip", false);
    s_lastMessageId = prefs.getLong("lastMsgId", 0);
    if (s_debugVerbosity > 2) s_debugVerbosity = 2;
    prefs.end();
}

static void saveRuntimeConfig() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.putUInt("sleepSec", s_sleepSec);
    prefs.putBool("maintMode", s_maintMode);
    prefs.putUChar("dbgVerb", s_debugVerbosity);
    prefs.putBool("camMirror", s_camMirror);
    prefs.putBool("camFlip", s_camFlip);
    prefs.putLong("lastMsgId", s_lastMessageId);
    prefs.end();
    s_lastMsgDirty = false;
    s_lastMsgPersistMs = millis();
}

// ============================================================
// Chat ID helper
// ============================================================

static bool chatIdMatches(const String& incoming, const char* stored) {
    if (!stored || stored[0] == '\0') return false;
    String s = String(stored);
    s.trim();
    return incoming == s;
}

static String normalizeCommand(String text) {
    int atIdx = text.indexOf('@');
    if (atIdx > 0) text = text.substring(0, atIdx);
    text.trim();
    return text;
}

static bool parseBatteryCalibrationArgs(const String& text, float& realV1, float& measuredV1, float& realV2, float& measuredV2) {
    const int firstSpace = text.indexOf(' ');
    if (firstSpace < 0) return false;

    String args = text.substring(firstSpace + 1);
    args.trim();

    float parsed[4] = {0.0f, 0.0f, 0.0f, 0.0f};
    int count = 0;
    int start = 0;

    while (start < args.length() && count < 4) {
        while (start < args.length() && args.charAt(start) == ' ') ++start;
        if (start >= args.length()) break;

        int end = args.indexOf(' ', start);
        if (end < 0) end = args.length();

        String token = args.substring(start, end);
        token.trim();
        token.replace(',', '.');
        if (token.length() == 0) return false;

        parsed[count++] = token.toFloat();
        start = end + 1;
    }

    if (count != 4) return false;

    realV1 = parsed[0];
    measuredV1 = parsed[1];
    realV2 = parsed[2];
    measuredV2 = parsed[3];
    return true;
}

// ============================================================
// Command handler
// ============================================================

static void handleMessage(const telegramMessage& msg, bool allowResetConfig = true) {
    String text   = normalizeCommand(msg.text);
    String chatId = msg.chat_id;

    // Update the last processed message ID so we don't replay on restart
    if (msg.update_id > s_lastMessageId) {
        s_lastMessageId = msg.update_id;
        s_lastMsgDirty = true;
        persistLastMessageId(false);
    }

    bool fromMain  = chatIdMatches(chatId, getChatId());
    bool fromDebug = chatIdMatches(chatId, getDebugChatId());
    if (!fromMain && !fromDebug) return;

    if (text == "/start" || text == "/status") {
        float temp = tempRead();
        float battRaw = batteryReadRawVoltage();
        float battV = batteryReadVoltage();
        int battPct = batteryReadPercent();
        String tempStr = (temp > -100) ? String(temp, 1) + " °C" : "N/A";
        String battStr = String(battV, 2) + " V (" + String(battPct) + "%)";
        String calState = batteryIsCalibrationEnabled() ? "ON" : "OFF";
        telegramSend(chatId.c_str(),
            "BirdNest online\nIP: " + WiFi.localIP().toString() +
            "\nTemp: " + tempStr +
            "\nBattery: " + battStr +
            "\nBattery raw: " + String(battRaw, 2) + " V" +
            "\nBattery calibration: " + calState +
            "\nMaintenance: " + (s_maintMode ? "ON" : "OFF") +
            "\nOTA recovery: " + String(otaRecoveryIsArmed() ? "ARMED" : "OFF") +
            "\nMirror: " + (s_camMirror ? "ON" : "OFF") +
            "\nFlip: " + (s_camFlip ? "ON" : "OFF"));
    }
    else if (text == "/maint_on") {
        s_maintMode = true;
        saveRuntimeConfig();
        telegramSend(chatId.c_str(), "Maintenance mode ON - deep sleep suppressed.");
        telegramSendDebug("Maintenance mode enabled by chat " + chatId);
    }
    else if (text == "/maint_off") {
        s_maintMode = false;
        saveRuntimeConfig();
        telegramSend(chatId.c_str(), "Maintenance mode OFF - deep sleep active.");
        telegramSendDebug("Maintenance mode disabled by chat " + chatId);

        // Live /maint_off should return to power-saving mode immediately.
        // Do not force sleep while replaying queued startup messages.
        if (allowResetConfig && s_sleepCb && s_sleepSec > 0) {
            telegramSendDebug("Entering deep sleep now after /maint_off", 1);
            delay(200);
            s_sleepCb(s_sleepSec);
        }
    }
    else if (text == "/photo") {
        telegramSend(chatId.c_str(), "Taking photo...");
        telegramSendDebug("Manual /photo requested by chat " + chatId, 2);
        if (s_photoCb) s_photoCb(chatId.c_str());
    }
    else if (text == "/reset_config") {
        if (!allowResetConfig) {
            Serial.println("[TG] skipped stale /reset_config");
            telegramSendDebug("Skipped stale /reset_config from queued message");
            return;
        }
        telegramSend(chatId.c_str(),
            "Resetting config. Connect to AP \"" AP_NAME "\" to reconfigure.");
        telegramSendDebug("Executing /reset_config from chat " + chatId);
        delay(1000);
        wifiReset();
    }
    else if (text.startsWith("/sleep") && text.length() == 8) {
        String numStr = text.substring(6); // two digits after /sleep
        bool isDigits = isdigit((unsigned char)numStr[0]) &&
                        isdigit((unsigned char)numStr[1]);
        if (isDigits) {
            uint32_t minutes = numStr.toInt();
            s_sleepSec = minutes * 60;
            saveRuntimeConfig();
            if (s_sleepSec == 0) {
                telegramSend(chatId.c_str(), "Deep sleep disabled.");
                telegramSendDebug("Deep sleep disabled by /sleep00 from chat " + chatId);
            } else {
                telegramSend(chatId.c_str(),
                    "Deep sleep set to " + String(minutes) + " min. Going to sleep now.");
                telegramSendDebug("Deep sleep set to " + String(minutes) + " min by chat " + chatId);

                // Only execute immediate sleep for live commands.
                // Startup queue replay must not force the device back to sleep.
                if (allowResetConfig && s_sleepCb) {
                    delay(200);
                    s_sleepCb(s_sleepSec);
                }
            }
        } else {
            telegramSend(chatId.c_str(),
                "Usage: /sleepXX where XX is 00-99 minutes (00 = off).");
        }
    }
    else if (text == "/debug0" || text == "/debug1" || text == "/debug2") {
        uint8_t level = static_cast<uint8_t>(text.charAt(6) - '0');
        s_debugVerbosity = level;
        saveRuntimeConfig();
        telegramSend(chatId.c_str(), "Debug verbosity set to " + String(level));
        telegramSendDebug("Debug verbosity changed to " + String(level) + " by chat " + chatId, 0);
    }
    else if (text == "/mirror0" || text == "/mirror1") {
        s_camMirror = (text.charAt(7) == '1');
        saveRuntimeConfig();
        telegramSend(chatId.c_str(), "Camera mirror set to " + String(s_camMirror ? "ON" : "OFF"));
        telegramSendDebug("Camera mirror set to " + String(s_camMirror ? "ON" : "OFF") + " by chat " + chatId, 0);
    }
    else if (text == "/flip0" || text == "/flip1") {
        s_camFlip = (text.charAt(5) == '1');
        saveRuntimeConfig();
        telegramSend(chatId.c_str(), "Camera flip set to " + String(s_camFlip ? "ON" : "OFF"));
        telegramSendDebug("Camera flip set to " + String(s_camFlip ? "ON" : "OFF") + " by chat " + chatId, 0);
    }
    else if (text.startsWith("/battcalset ") || text.startsWith("/batcalset ") || text.startsWith("/battcal ") || text.startsWith("/batcal ")) {
        float realV1 = 0.0f;
        float measuredV1 = 0.0f;
        float realV2 = 0.0f;
        float measuredV2 = 0.0f;
        if (!parseBatteryCalibrationArgs(text, realV1, measuredV1, realV2, measuredV2)) {
            telegramSend(chatId.c_str(),
                "Usage: /battcalset <real1> <measured1> <real2> <measured2>\n"
                "Example: /battcalset 4.13 3.21 3.78 3.08\n"
                "Alias: /batcalset ... or /batcal ...");
            return;
        }

        if (!batterySetTwoPointCalibration(realV1, measuredV1, realV2, measuredV2)) {
            telegramSend(chatId.c_str(),
                "Calibration failed. Ensure measured points differ enough (at least ~0.01V).");
            return;
        }

        float slope = 1.0f;
        float offset = 0.0f;
        float rv1 = 0.0f;
        float mv1 = 0.0f;
        float rv2 = 0.0f;
        float mv2 = 0.0f;
        batteryGetCalibration(slope, offset, rv1, mv1, rv2, mv2);

        telegramSend(chatId.c_str(),
            "Battery calibration saved.\n"
            "a=" + String(slope, 6) + ", b=" + String(offset, 6) +
            "\nNow: raw=" + String(batteryReadRawVoltage(), 3) + " V"
            ", calibrated=" + String(batteryReadVoltage(), 3) + " V");
        telegramSendDebug("Battery calibration updated by chat " + chatId, 0);
    }
    else if (text == "/battcal" || text == "/batcal") {
        float slope = 1.0f;
        float offset = 0.0f;
        float realV1 = 0.0f;
        float measuredV1 = 0.0f;
        float realV2 = 0.0f;
        float measuredV2 = 0.0f;
        batteryGetCalibration(slope, offset, realV1, measuredV1, realV2, measuredV2);

        String msgOut = "Battery calibration: " + String(batteryIsCalibrationEnabled() ? "ON" : "OFF") +
                        "\nCurrent raw: " + String(batteryReadRawVoltage(), 3) + " V" +
                        "\nCurrent calibrated: " + String(batteryReadVoltage(), 3) + " V" +
                        "\nModel: Vreal = a*Vmeasured + b" +
                        "\na=" + String(slope, 6) + ", b=" + String(offset, 6) +
                        "\nP1: real=" + String(realV1, 3) + " V, measured=" + String(measuredV1, 3) + " V" +
                        "\nP2: real=" + String(realV2, 3) + " V, measured=" + String(measuredV2, 3) + " V" +
                        "\n\nSet: /battcalset <real1> <measured1> <real2> <measured2>" +
                        "\nAlias: /batcalset ... or /batcal ..." +
                        "\nExample: /battcalset 4.13 3.21 3.78 3.08" +
                        "\nClear: /battcalclear";
        telegramSend(chatId.c_str(), msgOut);
    }
    else if (text == "/battcalclear") {
        batteryClearCalibration();
        telegramSend(chatId.c_str(),
            "Battery calibration cleared.\n"
            "Now: raw=" + String(batteryReadRawVoltage(), 3) + " V"
            ", calibrated=" + String(batteryReadVoltage(), 3) + " V");
        telegramSendDebug("Battery calibration cleared by chat " + chatId, 0);
    }
    else if (text == "/reboot") {
        if (!allowResetConfig) {
            telegramSendDebug("Skipped stale /reboot from queued message");
            return;
        }
        telegramSend(chatId.c_str(), "Rebooting now.");
        telegramSendDebug("/reboot requested by chat " + chatId, 0);
        delay(500);
        ESP.restart();
    }
}

// ============================================================
// Public API
// ============================================================

void telegramInit() {
    const char* token = getBotToken();
    if (!token || token[0] == '\0') return;

    loadRuntimeConfig();

    s_token = String(token);
    s_client.setInsecure();
    s_client.setTimeout(5000);

    delete s_bot;
    s_bot = new UniversalTelegramBot(s_token, s_client);

    // Set the bot's message cursor to the last processed message
    // so we don't replay old messages on restart
    if (s_lastMessageId > 0) {
        s_bot->last_message_received = s_lastMessageId;
    }
}

bool telegramSend(const char* chatId, const String& message) {
    if (!s_bot)                         { Serial.println("[TG] send: no bot"); return false; }
    if (!chatId || chatId[0] == '\0')   { Serial.println("[TG] send: empty chatId"); return false; }
    bool ok = s_bot->sendMessage(chatId, message, "");
    if (!ok) Serial.println("[TG] sendMessage FAILED to " + String(chatId));
    return ok;
}

bool telegramSendDebug(const String& message, uint8_t level) {
    if (level > s_debugVerbosity) return true;
    const char* debugChat = getDebugChatId();
    if (!debugChat || debugChat[0] == '\0') return false;
    return telegramSend(debugChat, "[DEBUG] " + message);
}

bool telegramSendWelcome() {
    int32_t rssi = WiFi.RSSI();
    float temp = tempRead();
    float battRaw = batteryReadRawVoltage();
    float battV = batteryReadVoltage();
    int battPct = batteryReadPercent();
    String tempStr = (temp > -100) ? String(temp, 1) + " °C" : "N/A";
    String battStr = String(battV, 2) + " V (" + String(battPct) + "%)";
    String msg = "BirdNest camera online!\n"
                 "IP: " + WiFi.localIP().toString() + "\n"
                 "WiFi RSSI: " + String(rssi) + " dBm\n"
                 "Battery: " + battStr + "\n"
                 "Battery raw: " + String(battRaw, 2) + " V\n"
                 "Battery calibration: " + String(batteryIsCalibrationEnabled() ? "ON" : "OFF") + "\n"
                 "Temp: " + tempStr + "\n\n"
                 "NVS runtime config:\n"
                 "Sleep: " + String(s_sleepSec / 60) + " min\n"
                 "Maintenance: " + String(s_maintMode ? "ON" : "OFF") + "\n"
                 "OTA recovery: " + String(otaRecoveryIsArmed() ? "ARMED" : "OFF") + "\n"
                 "Debug verbosity: " + String(s_debugVerbosity) + "\n"
                 "Camera mirror: " + String(s_camMirror ? "ON" : "OFF") + "\n"
                 "Camera flip: " + String(s_camFlip ? "ON" : "OFF") + "\n"
                 "Last message ID: " + String(s_lastMessageId) + "\n\n"
                 "Commands:\n"
                 "/photo – take a photo now\n"
                 "/status – show status\n"
                 "/reboot – reboot now\n"
                 "/maint_on – maintenance mode ON (deep sleep suppressed)\n"
                 "/maint_off – maintenance mode OFF\n"
                 "/sleepXX – deep sleep interval in minutes (00 = off)\n"
                 "/mirror0|1 – camera mirror OFF/ON\n"
                 "/flip0|1 – camera vertical flip OFF/ON\n"
                 "/battcal – show battery calibration\n"
                 "/battcalset r1 m1 r2 m2 – set two-point battery calibration\n"
                 "/battcalclear – clear battery calibration\n"
                 "/reset_config – erase WiFi and stored credentials\n"
                 "/debug0|1|2 – debug verbosity (minimal/normal/verbose)";
    bool ok = telegramSend(getChatId(), msg);
    telegramSendDebug(msg);
    return ok;
}

void telegramProcessStartupMessages() {
    if (!s_bot) return;

    const uint8_t maxAttempts = 3;
    int msgCount = 0;
    for (uint8_t attempt = 1; attempt <= maxAttempts; ++attempt) {
        msgCount = s_bot->getUpdates(s_bot->last_message_received + 1);
        if (msgCount > 0) break;
        Serial.println("[TG] startup queue empty/error, retry " + String(attempt) + "/" + String(maxAttempts));
        delay(250);
    }

    // Process queued commands from sleep/offline periods, but drop only
    // unsafe destructive commands that should not be replayed on boot.
    uint16_t processed = 0;
    unsigned long startMs = millis();

    while (msgCount) {
        if (processed >= STARTUP_MSG_PROCESS_LIMIT || (millis() - startMs) >= STARTUP_MSG_TIME_LIMIT_MS) {
            telegramSendDebug("Startup queue limit reached, deferring remaining messages", 1);
            break;
        }

        Serial.println("[TG] processing " + String(msgCount) + " queued message(s)");
        telegramSendDebug("Processing " + String(msgCount) + " queued Telegram message(s)", 2);
        for (int i = 0; i < msgCount; i++) {
            if (processed >= STARTUP_MSG_PROCESS_LIMIT || (millis() - startMs) >= STARTUP_MSG_TIME_LIMIT_MS) {
                break;
            }
            handleMessage(s_bot->messages[i], false);
            ++processed;
        }
        persistLastMessageId(false);
        msgCount = s_bot->getUpdates(s_bot->last_message_received + 1);
    }
    persistLastMessageId(true);
    s_lastBotCheck = millis();
}

void telegramLoop() {
    if (!s_bot) return;

    unsigned long now = millis();

    if (now - s_lastBotCheck < BOT_POLL_INTERVAL_MS) return;
    s_lastBotCheck = now;

    int numNewMessages = s_bot->getUpdates(s_bot->last_message_received + 1);
    if (numNewMessages > 0) {
        for (int i = 0; i < numNewMessages; i++) handleMessage(s_bot->messages[i]);
        persistLastMessageId(false);
    }
}

bool telegramIsMaintMode()  { return s_maintMode; }
uint32_t telegramGetSleepSec() { return s_sleepSec; }
uint8_t telegramGetDebugVerbosity() { return s_debugVerbosity; }
void telegramSetDebugVerbosity(uint8_t level) {
    s_debugVerbosity = (level > 2) ? 2 : level;
    saveRuntimeConfig();
}
bool telegramGetCamMirror() { return s_camMirror; }
bool telegramGetCamFlip() { return s_camFlip; }
void telegramSetCamMirror(bool enabled) {
    s_camMirror = enabled;
    saveRuntimeConfig();
}
void telegramSetCamFlip(bool enabled) {
    s_camFlip = enabled;
    saveRuntimeConfig();
}
void telegramSetPhotoCallback(PhotoCallback cb) { s_photoCb = cb; }
void telegramSetSleepCallback(SleepCallback cb) { s_sleepCb = cb; }
