#include "ota.h"
#include "config.h"
#include "telegram.h"

#include <ArduinoOTA.h>
#include <Arduino.h>

// ============================================================
// OTA – password-protected over-the-air firmware update
// ============================================================

static volatile bool s_otaActive = false;
static unsigned long s_lastOtaEventMs = 0;

void otaInit() {
    ArduinoOTA.setHostname(OTA_HOSTNAME);
    ArduinoOTA.setTimeout(OTA_TIMEOUT_MS);

    ArduinoOTA.onStart([]() {
        s_otaActive = true;
        s_lastOtaEventMs = millis();
        Serial.println("[OTA] start");
        telegramSendDebug("OTA update started", 0);
    });

    ArduinoOTA.onEnd([]() {
        s_otaActive = false;
        s_lastOtaEventMs = 0;
        Serial.println("[OTA] finished");
        telegramSendDebug("OTA update finished, rebooting...", 0);
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

void otaLoop() {
    ArduinoOTA.handle();

    if (!s_otaActive) return;

    const unsigned long stallTimeoutMs = static_cast<unsigned long>(OTA_STALL_TIMEOUT_SEC) * 1000UL;
    if (s_lastOtaEventMs == 0 || (millis() - s_lastOtaEventMs) <= stallTimeoutMs) return;

    s_otaActive = false;
    s_lastOtaEventMs = 0;
    telegramSendDebug("[OTA] transfer stalled, restarting device", 0);
    Serial.println("[OTA] transfer stalled, restarting device");
    delay(100);
    ESP.restart();
}

bool otaIsActive() {
    return s_otaActive;
}
