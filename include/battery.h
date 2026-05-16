#pragma once

// ============================================================
// battery.h
// Battery voltage measurement via ADC + resistor divider.
// ============================================================

// Configure ADC pin and mode. Call once from setup().
void batteryInit();

// Force a fresh ADC sample and update cached voltage value.
float batteryRefresh();

// Returns measured battery voltage in volts.
// On ADC2 pins during active WiFi, returns the cached value from the last
// successful refresh (sample before WiFi is recommended).
float batteryReadVoltage();

// Returns uncalibrated measured battery voltage in volts.
// On ADC2 pins during active WiFi, returns cached value from the last refresh.
float batteryReadRawVoltage();

// Returns charge estimate in percent [0..100] using linear mapping
// between BATTERY_EMPTY_V and BATTERY_FULL_V.
int batteryReadPercent();

// Battery calibration status and parameters.
bool batteryIsCalibrationEnabled();
bool batterySetTwoPointCalibration(float realV1, float measuredV1, float realV2, float measuredV2);
void batteryClearCalibration();
void batteryGetCalibration(float& slope, float& offset, float& realV1, float& measuredV1, float& realV2, float& measuredV2);
