#pragma once

// ============================================================
// ota.h
// ArduinoOTA handler – remote firmware upload over WiFi.
// ============================================================

// Initialise the OTA server. Call after WiFi is connected.
void otaInit();

// Handle OTA events – call on every loop() iteration.
void otaLoop();

// True while an OTA transfer is in progress.
bool otaIsActive();
