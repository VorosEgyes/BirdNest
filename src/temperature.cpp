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

void tempInit() {
    // GPIO13 (MTCK) has a weak internal pull-down during boot.
    // Enable internal pull-up first so the bus line is stable before OneWire starts.
    pinMode(TEMP_PIN, INPUT_PULLUP);
    delay(50); // let the line settle

    s_sensors.begin();
    s_sensorCount   = s_sensors.getDeviceCount();
    s_parasitePower = s_sensors.isParasitePowerMode();
}

uint8_t tempGetSensorCount()   { return s_sensorCount; }
bool    tempIsParasitePower()  { return s_parasitePower; }

float tempRead() {
    const uint8_t sampleCount = TEMP_SAMPLE_COUNT;
    float sum = 0.0f;
    uint8_t valid = 0;

    for (uint8_t i = 0; i < sampleCount; ++i) {
        s_sensors.requestTemperatures();
        float t = s_sensors.getTempCByIndex(0);
        if (t != DEVICE_DISCONNECTED_C) {
            sum += t;
            ++valid;
        }
    }

    if (valid == 0) {
        return -127.0f; // Sensor not found or disconnected
    }

    return sum / valid;
}
