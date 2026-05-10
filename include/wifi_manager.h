#pragma once

#include <Arduino.h>

// ============================================================
// wifi_manager.h
// WiFiManager initialisation with 3 custom fields (Telegram credentials).
// Credentials are persisted in ESP32 NVS and survive reboots.
// ============================================================

// Start WiFi connection / captive portal.
// Opens an AP portal when enabled and no saved credentials exist.
// In fail-fast mode it only attempts STA reconnect and returns quickly on failure.
// Portal is reachable at the AP IP (default 192.168.4.1).
// Returns true on successful connection, false on timeout/error.
bool wifiInit();

// Access saved Telegram credentials (valid after wifiInit() returns true)
const char* getBotToken();
const char* getChatId();
const char* getDebugChatId();

// Reset WiFi settings (clears saved credentials) and reboot
void wifiReset();
