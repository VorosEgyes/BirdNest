#include <Arduino.h>
#include <WiFi.h>
#include <time.h>
#include "esp_camera.h"
#include "esp_sleep.h"

#include "config.h"
#include "wifi_manager.h"
#include "telegram.h"
#include "camera.h"
#include "ota.h"
#include "temperature.h"
#include "battery.h"
#include "sun_times.h"

// ============================================================
// Global timers
// ============================================================

static unsigned long s_lastPhotoMs = 0;
static const unsigned long PHOTO_INTERVAL_MS =
    static_cast<unsigned long>(PHOTO_INTERVAL_SEC) * 1000UL;
static const uint32_t WIFI_RETRY_BACKOFF_SEC = 300;
static bool s_timeSynced = false;

static bool syncTimeIfNeeded() {
    if (s_timeSynced) return true;

    configTzTime(NTP_TZ, NTP_SERVER_1, NTP_SERVER_2, NTP_SERVER_3);

    struct tm timeInfo;
    for (int i = 0; i < 30; ++i) {
        if (getLocalTime(&timeInfo, 500)) {
            s_timeSynced = true;
            Serial.printf("[NTP] synced: %02d:%02d:%02d\n",
                          timeInfo.tm_hour,
                          timeInfo.tm_min,
                          timeInfo.tm_sec);
            return true;
        }
        delay(200);
    }

    Serial.println("[NTP] sync failed");
    telegramSendDebug("NTP sync failed");
    return false;
}

static String formatNextWakeTime(uint32_t seconds) {
    time_t now = time(nullptr);
    if (now <= 100000) return "unknown";

    time_t wakeAt = now + seconds;
    struct tm wakeTm;
    localtime_r(&wakeAt, &wakeTm);

    char buf[16];
    snprintf(buf, sizeof(buf), "%02d:%02d:%02d",
             wakeTm.tm_hour, wakeTm.tm_min, wakeTm.tm_sec);
    return String(buf);
}

static void enterDeepSleepSeconds(uint32_t seconds) {
    // Never enter deep sleep while an OTA transfer is in progress.
    if (otaIsActive()) {
        Serial.println("[PWR] deep sleep suppressed – OTA active");
        return;
    }
    String nextWake = syncTimeIfNeeded() ? formatNextWakeTime(seconds) : "unknown";
    String sleepMsg = "Going to deep sleep. Next wake-up: " + nextWake;

    telegramSendDebug(sleepMsg, 0);

    Serial.println("[PWR] entering deep sleep for " + String(seconds) + "s");
    esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(seconds) * 1000000ULL);
    esp_deep_sleep_start();
}

static bool captureAndSendPhoto(const char* chatId, bool retryOnce) {
    if (!chatId || chatId[0] == '\0') return false;

    if (!cameraInit()) {
        Serial.println("[PHOTO] cameraInit FAILED");
        telegramSendDebug("cameraInit failed");
        return false;
    }

    bool ok = cameraSendPhoto(chatId);
    if (!ok && retryOnce) {
        Serial.println("[PHOTO] first send failed, retrying once...");
        telegramSendDebug("Photo send failed, retrying once");
        delay(500);
        ok = cameraSendPhoto(chatId);
    }

    cameraDeinit();
    Serial.println(ok ? "[PHOTO] sent OK" : "[PHOTO] send FAILED");
    if (!ok) telegramSendDebug("Photo send failed after retry");
    return ok;
}

// ============================================================
// Photo callback – called by telegramLoop() on /photo command
// ============================================================

static void onPhotoRequest(const char* chatId) {
    Serial.println("[PHOTO] starting...");
    telegramSendDebug("Starting manual photo capture");
    if (!captureAndSendPhoto(chatId, true)) {
        telegramSend(chatId, "Photo capture/send failed.");
    }
}

static void onSleepRequest(uint32_t sleepSec) {
    if (sleepSec > 0) {
        enterDeepSleepSeconds(sleepSec);
    }
}

// ============================================================
// Night-time sleep check
// Skips if: maintenance mode is on, NTP not synced, or daytime.
// Sleeps until sunrise (- SUNRISE_BUFFER_MIN), capped at 12 h.
// ============================================================
static void nightSleepIfNeeded() {
    if (telegramIsMaintMode()) return; // maintenance override
    if (!s_timeSynced)         return; // no NTP – can't determine night

    struct tm t;
    if (!getLocalTime(&t, 500)) return;

    // ISO week number (01-53)
    char weekBuf[4];
    strftime(weekBuf, sizeof(weekBuf), "%V", &t);
    int isoWeek    = atoi(weekBuf);
    int currentMin = t.tm_hour * 60 + t.tm_min;

    uint32_t sleepSecs = secondsUntilSunrise(isoWeek, currentMin);
    if (sleepSecs == 0) return; // daytime – proceed normally

    // Format expected wake time for the notification
    int idx = (isoWeek < 1 ? 0 : isoWeek > 52 ? 51 : isoWeek - 1);
    uint16_t wakeMin = (SUN_TABLE[idx].sunrise > SUNRISE_BUFFER_MIN)
                       ? SUN_TABLE[idx].sunrise - SUNRISE_BUFFER_MIN : 0;
    char wakeBuf[6];
    snprintf(wakeBuf, sizeof(wakeBuf), "%02d:%02d", wakeMin / 60, wakeMin % 60);

    uint32_t sleepHours = sleepSecs / 3600;
    uint32_t sleepMinutes = (sleepSecs % 3600) / 60;

    Serial.printf("[NIGHT] Night mode - sleeping for %uh %um until sunrise ~%s\n",
                  sleepHours, sleepMinutes, wakeBuf);

    String msg = "Night mode: sleeping for " + String(sleepHours) + "h " + String(sleepMinutes) +
                 "m, until sunrise (~" + String(wakeBuf) + ").";
    const char* chatId = getChatId();
    if (chatId && chatId[0] != '\0') telegramSend(chatId, msg);
    telegramSendDebug("[NIGHT] Sleep " + String(sleepHours) + "h " + String(sleepMinutes) +
                      "m until sunrise ~" + String(wakeBuf));

    esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(sleepSecs) * 1000000ULL);
    esp_deep_sleep_start();
}

// ============================================================
// setup
// ============================================================

void setup() {
    Serial.begin(115200);
    Serial.println("\n\n=== BirdNest boot ===");
    // Arduino framework: watchdog is fed by yield()/delay() in loop and long operations

    // Temperature sensor – does not depend on WiFi
    tempInit();
    batteryInit();
    batteryRefresh();
    const float batteryVoltage = batteryReadVoltage();

    // WiFi + captive portal (blocking until connected or timeout)
    Serial.println("[WIFI] connecting...");
    if (!wifiInit()) {
        Serial.println("[WIFI] FAILED – sleeping before retry");
        delay(500);
        uint32_t retrySleepSec = otaRecoveryIsArmed()
            ? otaGetRecoverySleepSeconds(batteryVoltage)
            : WIFI_RETRY_BACKOFF_SEC;
        enterDeepSleepSeconds(retrySleepSec);
    }
    WiFi.setSleep(false);
    Serial.println("[WIFI] connected: " + WiFi.localIP().toString());
    otaInit();

    // Give PlatformIO time to initiate an OTA connection before we do any
    // heavy/blocking work (Telegram HTTPS, photo capture, deep sleep).
    // Without this window, loop() may never run if sleepSec > 0.
    if (!otaStartupWindow(batteryVoltage)) {
        enterDeepSleepSeconds(otaGetRecoverySleepSeconds(batteryVoltage));
    }

    syncTimeIfNeeded();

    // OTA server
   
    // Telegram bot
    Serial.println("[TG] init...");
    telegramInit();
    telegramSetPhotoCallback(onPhotoRequest);
    telegramSetSleepCallback(onSleepRequest);

    // DS18B20 diagnostics via Telegram (tempInit() already ran before WiFi)
    {
        uint8_t cnt = tempGetSensorCount();
        float   t   = tempRead();
        String diagMsg = "DS18B20 diag:\n"
                         "Sensors found: " + String(cnt) + "\n"
                         "Parasite power: " + String(tempIsParasitePower() ? "YES" : "NO") + "\n"
                         "Temp: " + (cnt > 0 ? String(t, 1) + " C" : "N/A");
        telegramSendDebug(diagMsg, 0);
    }

    // Process queued commands first (e.g. /maint_on while device was sleeping)
    // so runtime flags are up to date before any sleep decision.
    telegramProcessStartupMessages();

    // Night-time check: if after sunset or before sunrise, sleep until sunrise (max 12 h)
    nightSleepIfNeeded();


    // Check if we woke from deep sleep – if so, take a photo immediately
    bool fromSleep = (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER);

     // Log current runtime config to serial and debug chat
     uint32_t sleepSec = telegramGetSleepSec();
     bool maintMode = telegramIsMaintMode();
     Serial.printf("[CFG] Deep sleep: %u sec (%u min), Maintenance: %s\n",
                   sleepSec, sleepSec / 60, maintMode ? "ON" : "OFF");
     String cfgMsg = "Config loaded from NVS:\n"
                     "Sleep: " + String(sleepSec / 60) + " min\n"
                     "Maintenance: " + String(maintMode ? "ON" : "OFF");
     telegramSendDebug(cfgMsg, 2);

     // Send welcome FIRST if not from sleep
     if (!fromSleep) {
         Serial.println("[TG] sending welcome...");
         bool ok = telegramSendWelcome();
         Serial.println(ok ? "[TG] welcome sent OK" : "[TG] welcome FAILED");
         if (!ok) telegramSendDebug("Welcome message send failed");
     }

    // Take a photo on startup unless maintenance mode is enabled.
    if (getChatId() && getChatId()[0] != '\0') {
        if (maintMode) {
            Serial.println("[PHOTO] startup capture skipped (maintenance mode)");
            telegramSendDebug("📸 Startup photo skipped (maintenance mode)", 1);
        } else {
            // Ensure no photos are sent in maintenance mode
            if (getChatId() && getChatId()[0] != '\0' && !maintMode) {
                if (fromSleep) {
                    Serial.println("[PHOTO] starting capture...");
                    telegramSendDebug("📸 Capturing photo...", 1);
                    if (!captureAndSendPhoto(getChatId(), true)) {
                        String msg = "[wakeup] Photo capture/send failed.";
                        telegramSend(getChatId(), msg);
                        telegramSendDebug("📸 Photo send failed", 1);
                    } else {
                        telegramSendDebug("📸 Photo sent", 1);
                    }
                }
            } else {
                Serial.println("[PHOTO] skipped due to maintenance mode");
            }
        }
    }

    if (fromSleep) {
        telegramSendDebug("Wakeup cause: timer deep sleep");
    }

    // After startup photo and startup queue processing, continue the deep sleep cycle immediately.
    // This applies to both first boot and timer wakeups.
    uint32_t sleepSecNow = telegramGetSleepSec();
    if (sleepSecNow > 0 && !telegramIsMaintMode() && !otaIsActive()) {
        enterDeepSleepSeconds(sleepSecNow);
    }

    Serial.println("=== setup done ===");
}

// ============================================================
// loop
// ============================================================

void loop() {
    yield();
    // OTA updates – always first
    otaLoop();

    // While OTA is active, do not run any other blocking network work.
    if (otaIsActive()) {
        delay(2);
        return;
    }

    // Handle incoming Telegram commands
    telegramLoop();

    // Periodic photo + deep sleep cycle
    unsigned long now = millis();
    if (now - s_lastPhotoMs >= PHOTO_INTERVAL_MS) {
        s_lastPhotoMs = now;

        // Enter deep sleep if configured and maintenance mode is off.
        // On wakeup, setup() will take the photo automatically.
        uint32_t sleepSec = telegramGetSleepSec();
        if (sleepSec > 0 && !telegramIsMaintMode()) {
            enterDeepSleepSeconds(sleepSec);
        }

        // Deep sleep disabled – take photo inline
        if (getChatId() && getChatId()[0] != '\0') {
            captureAndSendPhoto(getChatId(), true);
        }
    }

    // Short delay to feed watchdog
    delay(10);
}