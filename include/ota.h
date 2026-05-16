#pragma once

// ============================================================
// ota.h
// ArduinoOTA handler – remote firmware upload over WiFi.
// ============================================================

// Initialise the OTA server. Call after WiFi is connected.
void otaInit();

// Poll OTA during startup.
// Returns true when normal boot should continue.
// Returns false when recovery mode should go back to sleep and retry later.
void otaArmRecovery();
void otaClearRecovery();
bool otaRecoveryIsArmed();
unsigned long otaGetRecoverySleepSeconds(float batteryVoltage);
bool otaStartupWindow(float batteryVoltage);

// Handle OTA events – call on every loop() iteration.
void otaLoop();

// True while an OTA transfer is in progress.
bool otaIsActive();
