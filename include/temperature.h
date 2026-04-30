#pragma once

// ============================================================
// temperature.h
// DS18B20 temperature sensor over OneWire bus (TEMP_PIN).
// ============================================================

// Initialise the sensor. Call from setup().
void tempInit();

// Read temperature in Celsius.
// Returns -127.0 if the sensor is not reachable.
float tempRead();
