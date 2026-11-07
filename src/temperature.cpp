#include "temperature.h"
#include "config.h"

#include <OneWire.h>
#include <DallasTemperature.h>
#include <Arduino.h>

// ============================================================
// DS18B20 – OneWire temperature sensor
// ============================================================

static OneWire           s_oneWire(TEMP_PIN);
static DallasTemperature s_sensors(&s_oneWire);
static uint8_t           s_sensorCount = 0;
static bool              s_parasitePower = false;
static constexpr uint32_t kTemperatureCacheMs = 60000UL;
static float              s_cachedTemperature = -127.0f;
static uint32_t           s_lastReadMs = 0;
static bool               s_hasCachedReading = false;

void tempInit() {
    // GPIO13 (MTCK) has a weak internal pull-down during boot.
    // Enable internal pull-up first so the bus line is stable before OneWire starts.
    pinMode(TEMP_PIN, INPUT_PULLUP);
    delay(50); // let the line settle

    s_sensors.begin();
    s_sensorCount   = s_sensors.getDeviceCount();
    s_parasitePower = s_sensors.isParasitePowerMode();
    s_cachedTemperature = -127.0f;
    s_lastReadMs = 0;
    s_hasCachedReading = false;
}

uint8_t tempGetSensorCount()   { return s_sensorCount; }
bool    tempIsParasitePower()  { return s_parasitePower; }

float tempRead() {
    if (s_sensorCount == 0) return -127.0f;

    const uint32_t now = millis();
    if (s_hasCachedReading && (now - s_lastReadMs) < kTemperatureCacheMs) {
        return s_cachedTemperature;
    }

    s_sensors.requestTemperatures();
    const float temperature = s_sensors.getTempCByIndex(0);
    s_cachedTemperature = (temperature == DEVICE_DISCONNECTED_C) ? -127.0f : temperature;
    s_lastReadMs = millis();
    s_hasCachedReading = true;
    return s_cachedTemperature;
}
