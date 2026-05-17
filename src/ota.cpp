#include "ota.h"
#include "config.h"
#include "telegram.h"

#include <ArduinoOTA.h>
#include <Arduino.h>
#include <Preferences.h>

// ============================================================
// OTA – password-protected over-the-air firmware update
// ============================================================

static volatile bool s_otaActive = false;
static unsigned long s_lastOtaEventMs = 0;
static bool s_lastTransferSuccessful = false;
static bool s_recoveryArmed = false;
static uint16_t s_recoveryCyclesRemaining = 0;
static bool s_recoveryStateLoaded = false;

static void loadRecoveryState() {
    if (s_recoveryStateLoaded) return;

    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/true);
    s_recoveryArmed = prefs.getBool("otaArmed", false);
    s_recoveryCyclesRemaining = prefs.getUShort("otaCycles", 0);
    prefs.end();
    s_recoveryStateLoaded = true;
}

static void saveRecoveryState() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.putBool("otaArmed", s_recoveryArmed);
    prefs.putUShort("otaCycles", s_recoveryCyclesRemaining);
    prefs.end();
}

static bool otaHandleWithWatchdog() {
    ArduinoOTA.handle();

    if (!s_otaActive) return true;

    const unsigned long stallTimeoutMs = static_cast<unsigned long>(OTA_STALL_TIMEOUT_SEC) * 1000UL;
    if (s_lastOtaEventMs != 0 && (millis() - s_lastOtaEventMs) <= stallTimeoutMs) {
        return true;
    }

    s_otaActive = false;
    s_lastOtaEventMs = 0;
    telegramSendDebug("[OTA] transfer stalled, restarting device", 0);
    Serial.println("[OTA] transfer stalled, restarting device");
    delay(100);
    ESP.restart();
    return false;
}

void otaArmRecovery() {
    loadRecoveryState();
    s_recoveryArmed = true;
    s_recoveryCyclesRemaining = OTA_RECOVERY_CYCLES;
    saveRecoveryState();
}

void otaClearRecovery() {
    loadRecoveryState();
    s_recoveryArmed = false;
    s_recoveryCyclesRemaining = 0;
    saveRecoveryState();
}

bool otaRecoveryIsArmed() {
    loadRecoveryState();
    return s_recoveryArmed;
}

unsigned long otaGetRecoverySleepSeconds(float batteryVoltage) {
    loadRecoveryState();
    if (batteryVoltage > 0.0f && batteryVoltage < OTA_RECOVERY_MIN_BATTERY_V) {
        return OTA_RECOVERY_LOW_BATTERY_SLEEP_SEC;
    }
    return OTA_RECOVERY_SLEEP_SEC;
}

void otaInit() {
    loadRecoveryState();

    ArduinoOTA.setHostname(OTA_HOSTNAME);
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.setTimeout(OTA_TIMEOUT_MS);

    ArduinoOTA.onStart([]() {
        s_otaActive = true;
        s_lastOtaEventMs = millis();
        s_lastTransferSuccessful = false;
        Serial.println("[OTA] start");
        telegramSendDebug("[OTA] update started", 1);
    });

    ArduinoOTA.onEnd([]() {
        s_otaActive = false;
        s_lastOtaEventMs = 0;
        s_lastTransferSuccessful = true;
        otaClearRecovery();
        Serial.println("[OTA] finished");
        telegramSendDebug("[OTA] update finished, rebooting", 1);
    });

    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        static unsigned int lastPercent = 0;
        s_lastOtaEventMs = millis();
        unsigned int percent = total ? (progress * 100U) / total : 0;
        if (percent >= lastPercent + 25U || percent == 100U) {
            lastPercent = percent;
            Serial.println("[OTA] progress " + String(percent) + "%");
        }
    });


    ArduinoOTA.onError([](ota_error_t error) {
        s_otaActive = false;
        s_lastOtaEventMs = 0;
        const char* name = "UNKNOWN";
        switch (error) {
            case OTA_AUTH_ERROR:    name = "AUTH_ERROR";    break;
            case OTA_BEGIN_ERROR:   name = "BEGIN_ERROR";   break;
            case OTA_CONNECT_ERROR: name = "CONNECT_ERROR"; break;
            case OTA_RECEIVE_ERROR: name = "RECEIVE_ERROR"; break;
            case OTA_END_ERROR:     name = "END_ERROR";     break;
        }
        String msg = "[OTA] error " + String(static_cast<int>(error)) + " (" + name + ")";
        Serial.println(msg);
        telegramSendDebug(msg, 0);

        if (error == OTA_CONNECT_ERROR) {
            telegramSendDebug("[OTA] CONNECT_ERROR: check upload IP, same WiFi/LAN, and firewall", 0);
        } else if (error == OTA_RECEIVE_ERROR) {
            telegramSendDebug("[OTA] RECEIVE_ERROR: unstable link or timeout during transfer", 0);
        } else if (error == OTA_END_ERROR) {
            telegramSendDebug("[OTA] END_ERROR: transfer interrupted or incomplete", 0);
        }
    });

    ArduinoOTA.begin();
}

bool otaStartupWindow(float batteryVoltage) {
    const bool batteryTooLowForRecovery =
        batteryVoltage > 0.0f && batteryVoltage < OTA_RECOVERY_MIN_BATTERY_V;

    if (s_recoveryArmed && s_recoveryCyclesRemaining == 0) {
        telegramSendDebug("[OTA] recovery attempts exhausted, clearing latch", 1);
        otaClearRecovery();
    }

    const bool extendedRecovery =
        s_recoveryArmed && !batteryTooLowForRecovery && s_recoveryCyclesRemaining > 0;
    const uint32_t windowSec = extendedRecovery ? OTA_RECOVERY_WINDOW_SEC : OTA_STARTUP_WINDOW_SEC;
    const unsigned long windowMs = static_cast<unsigned long>(windowSec) * 1000UL;
    unsigned long windowStart = millis();

    if (extendedRecovery) {
        telegramSendDebug("[OTA] recovery window open " + String(windowSec) + "s, attempts left after this: " +
                              String(s_recoveryCyclesRemaining > 0 ? s_recoveryCyclesRemaining - 1 : 0), 1);
    } else if (s_recoveryArmed && batteryTooLowForRecovery) {
        telegramSendDebug("[OTA] recovery deferred, battery too low (" + String(batteryVoltage, 2) +
                              " V < " + String(OTA_RECOVERY_MIN_BATTERY_V, 2) + " V)", 1);
    } else {
        telegramSendDebug("[OTA] startup window open " + String(windowSec) + "s - start upload now", 2);
    }

    while ((millis() - windowStart) < windowMs) {
        if (!otaHandleWithWatchdog()) return false;
        if (s_otaActive) {
            telegramSendDebug("[OTA] transfer started", 1);
            while (s_otaActive) {
                if (!otaHandleWithWatchdog()) return false;
                delay(2);
            }

            if (s_lastTransferSuccessful) {
                return true;
            }
        }
        delay(10);
    }

    if (extendedRecovery && s_recoveryCyclesRemaining > 0) {
        --s_recoveryCyclesRemaining;
        saveRecoveryState();
        telegramSendDebug("[OTA] recovery window closed, sleeping before retry", 1);
        return false;
    }

    if (s_recoveryArmed && batteryTooLowForRecovery) {
        telegramSendDebug("[OTA] recovery remains armed, sleeping to protect battery", 1);
        return false;
    }

    telegramSendDebug("[OTA] window closed, continuing boot", 2);
    return true;
}

void otaLoop() {
    otaHandleWithWatchdog();
}

bool otaIsActive() {
    return s_otaActive;
}
