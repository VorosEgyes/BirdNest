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

void tempInit() {
    s_sensors.begin();
    // Sensor count is not logged (no serial in remote-only deployment)
}

float tempRead() {
    s_sensors.requestTemperatures();
    float t = s_sensors.getTempCByIndex(0);
    if (t == DEVICE_DISCONNECTED_C) {
        return -127.0f; // Sensor not found or disconnected
    }
    return t;
}
