#include "ota.h"
#include "config.h"
#include "telegram.h"

#include <ArduinoOTA.h>
#include <Arduino.h>

// ============================================================
// OTA – password-protected over-the-air firmware update
// ============================================================

static volatile bool s_otaActive = false;

void otaInit() {
    ArduinoOTA.setHostname(OTA_HOSTNAME);

    ArduinoOTA.onStart([]() {
        s_otaActive = true;
        Serial.println("[OTA] start");
        telegramSendDebug("OTA update started", 0);
    });

    ArduinoOTA.onEnd([]() {
        s_otaActive = false;
        Serial.println("[OTA] finished");
        telegramSendDebug("OTA update finished, rebooting...", 0);
    });

    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        static unsigned int lastPercent = 0;
        unsigned int percent = total ? (progress * 100U) / total : 0;
        if (percent >= lastPercent + 25U || percent == 100U) {
            lastPercent = percent;
            Serial.println("[OTA] progress " + String(percent) + "%");
        }
    });


    ArduinoOTA.onError([](ota_error_t error) {
        s_otaActive = false;
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
    });

    ArduinoOTA.begin();

}

void otaLoop() {
    ArduinoOTA.handle();
}

bool otaIsActive() {
    return s_otaActive;
}
