#include "battery.h"
#include "config.h"

#include <Arduino.h>
#include <math.h>
#include <Preferences.h>
#include <WiFi.h>

static float s_lastVoltage = 0.0f;
static float s_lastRawVoltage = 0.0f;
static bool s_hasVoltage = false;

static bool s_calEnabled = false;
static float s_calSlope = 1.0f;
static float s_calOffset = 0.0f;
static float s_calRealV1 = 0.0f;
static float s_calMeasuredV1 = 0.0f;
static float s_calRealV2 = 0.0f;
static float s_calMeasuredV2 = 0.0f;

static constexpr const char* KEY_CAL_ENABLED = "bCalEn";
static constexpr const char* KEY_CAL_SLOPE = "bCalA";
static constexpr const char* KEY_CAL_OFFSET = "bCalB";
static constexpr const char* KEY_CAL_REAL_V1 = "bCalR1";
static constexpr const char* KEY_CAL_MEAS_V1 = "bCalM1";
static constexpr const char* KEY_CAL_REAL_V2 = "bCalR2";
static constexpr const char* KEY_CAL_MEAS_V2 = "bCalM2";

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

static float applyCalibration(float rawVoltage) {
    if (!s_calEnabled) return rawVoltage;
    return (rawVoltage * s_calSlope) + s_calOffset;
}

static void loadCalibration() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/true);
    s_calEnabled = prefs.getBool(KEY_CAL_ENABLED, false);
    s_calSlope = prefs.getFloat(KEY_CAL_SLOPE, 1.0f);
    s_calOffset = prefs.getFloat(KEY_CAL_OFFSET, 0.0f);
    s_calRealV1 = prefs.getFloat(KEY_CAL_REAL_V1, 0.0f);
    s_calMeasuredV1 = prefs.getFloat(KEY_CAL_MEAS_V1, 0.0f);
    s_calRealV2 = prefs.getFloat(KEY_CAL_REAL_V2, 0.0f);
    s_calMeasuredV2 = prefs.getFloat(KEY_CAL_MEAS_V2, 0.0f);
    prefs.end();

    if (!isfinite(s_calSlope) || !isfinite(s_calOffset)) {
        s_calEnabled = false;
        s_calSlope = 1.0f;
        s_calOffset = 0.0f;
    }
}

static void saveCalibration() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.putBool(KEY_CAL_ENABLED, s_calEnabled);
    prefs.putFloat(KEY_CAL_SLOPE, s_calSlope);
    prefs.putFloat(KEY_CAL_OFFSET, s_calOffset);
    prefs.putFloat(KEY_CAL_REAL_V1, s_calRealV1);
    prefs.putFloat(KEY_CAL_MEAS_V1, s_calMeasuredV1);
    prefs.putFloat(KEY_CAL_REAL_V2, s_calRealV2);
    prefs.putFloat(KEY_CAL_MEAS_V2, s_calMeasuredV2);
    prefs.end();
}

void batteryInit() {
    analogReadResolution(12);
    analogSetPinAttenuation(BATTERY_ADC_PIN, ADC_11db);
    loadCalibration();
}

float batteryRefresh() {
    const float raw = sampleBatteryVoltageNow();
    s_lastRawVoltage = raw;
    s_lastVoltage = applyCalibration(raw);
    s_hasVoltage = true;
    return s_lastVoltage;
}

float batteryReadVoltage() {
    // ESP32 ADC2 cannot be read while WiFi is active.
    // Return last valid pre-WiFi sample on ADC2-based hardware.
    if (isAdc2Pin(BATTERY_ADC_PIN) && WiFi.status() == WL_CONNECTED) {
        return s_hasVoltage ? s_lastVoltage : 0.0f;
    }

    return batteryRefresh();
}

float batteryReadRawVoltage() {
    if (isAdc2Pin(BATTERY_ADC_PIN) && WiFi.status() == WL_CONNECTED) {
        return s_hasVoltage ? s_lastRawVoltage : 0.0f;
    }

    batteryRefresh();
    return s_lastRawVoltage;
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

bool batteryIsCalibrationEnabled() {
    return s_calEnabled;
}

bool batterySetTwoPointCalibration(float realV1, float measuredV1, float realV2, float measuredV2) {
    const float dx = measuredV2 - measuredV1;
    if (fabsf(dx) < 0.01f) return false;

    const float slope = (realV2 - realV1) / dx;
    const float offset = realV1 - (slope * measuredV1);
    if (!isfinite(slope) || !isfinite(offset)) return false;

    s_calSlope = slope;
    s_calOffset = offset;
    s_calRealV1 = realV1;
    s_calMeasuredV1 = measuredV1;
    s_calRealV2 = realV2;
    s_calMeasuredV2 = measuredV2;
    s_calEnabled = true;
    saveCalibration();

    if (s_hasVoltage) {
        s_lastVoltage = applyCalibration(s_lastRawVoltage);
    }
    return true;
}

void batteryClearCalibration() {
    s_calEnabled = false;
    s_calSlope = 1.0f;
    s_calOffset = 0.0f;
    s_calRealV1 = 0.0f;
    s_calMeasuredV1 = 0.0f;
    s_calRealV2 = 0.0f;
    s_calMeasuredV2 = 0.0f;
    saveCalibration();

    if (s_hasVoltage) {
        s_lastVoltage = s_lastRawVoltage;
    }
}

void batteryGetCalibration(float& slope, float& offset, float& realV1, float& measuredV1, float& realV2, float& measuredV2) {
    slope = s_calSlope;
    offset = s_calOffset;
    realV1 = s_calRealV1;
    measuredV1 = s_calMeasuredV1;
    realV2 = s_calRealV2;
    measuredV2 = s_calMeasuredV2;
}
