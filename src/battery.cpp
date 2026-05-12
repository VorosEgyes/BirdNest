#include "battery.h"
#include "config.h"

#include <Arduino.h>
#include <WiFi.h>

static float s_lastVoltage = 0.0f;
static bool s_hasVoltage = false;

static bool isAdc2Pin(int pin) {
    switch (pin) {
        case 0:
        case 2:
        case 4:
        case 12:
        case 13:
        case 14:
        case 15:
        case 25:
        case 26:
        case 27:
            return true;
        default:
            return false;
    }
}

static float sampleBatteryVoltageNow() {
    uint32_t sumMv = 0;
    const uint8_t samples = BATTERY_ADC_SAMPLES > 0 ? BATTERY_ADC_SAMPLES : 1;

    for (uint8_t i = 0; i < samples; ++i) {
        delayMicroseconds(BATTERY_ADC_SETTLE_US);
        (void)analogRead(BATTERY_ADC_PIN); // discard first conversion to settle ADC sample cap
        delayMicroseconds(BATTERY_ADC_SETTLE_US);
        uint32_t mv = static_cast<uint32_t>(analogReadMilliVolts(BATTERY_ADC_PIN));
        if (mv == 0U) {
            const uint32_t raw = static_cast<uint32_t>(analogRead(BATTERY_ADC_PIN));
            mv = static_cast<uint32_t>((static_cast<float>(raw) / BATTERY_ADC_MAX) * BATTERY_ADC_VREF * 1000.0f);
        }
        sumMv += mv;
    }

    const float vAdc = (static_cast<float>(sumMv) / static_cast<float>(samples)) / 1000.0f;
    const float divider = (BATTERY_DIVIDER_RTOP + BATTERY_DIVIDER_RBOTTOM) / BATTERY_DIVIDER_RBOTTOM;
    return vAdc * divider * BATTERY_CAL_MULT;
}

void batteryInit() {
    analogReadResolution(12);
    analogSetPinAttenuation(BATTERY_ADC_PIN, ADC_11db);
}

float batteryRefresh() {
    const float v = sampleBatteryVoltageNow();
    s_lastVoltage = v;
    s_hasVoltage = true;
    return v;
}

float batteryReadVoltage() {
    // ESP32 ADC2 cannot be read while WiFi is active.
    // Return last valid pre-WiFi sample on ADC2-based hardware.
    if (isAdc2Pin(BATTERY_ADC_PIN) && WiFi.status() == WL_CONNECTED) {
        return s_hasVoltage ? s_lastVoltage : 0.0f;
    }

    return batteryRefresh();
}

int batteryReadPercent() {
    const float v = batteryReadVoltage();
    const float denom = BATTERY_FULL_V - BATTERY_EMPTY_V;
    if (denom <= 0.0f) return 0;

    float pct = ((v - BATTERY_EMPTY_V) / denom) * 100.0f;
    if (pct < 0.0f) pct = 0.0f;
    if (pct > 100.0f) pct = 100.0f;
    return static_cast<int>(pct + 0.5f);
}
