#pragma once

#include <Arduino.h>

// ============================================================
// mqtt_client.h
// MQTT runtime configuration and telemetry publishing.
// Configuration is stored in NVS and can be updated via Telegram.
// ============================================================

void mqttInit();
void mqttLoop();

// Publish one status packet immediately (if connected/configured).
void mqttPublishNow(const char* reason = "manual");

// MQTT runtime config management.
bool mqttHasConfig();
bool mqttSetConfig(const String& host, uint16_t port, const String& username, const String& password);
void mqttClearConfig();
void mqttGetConfig(String& host, uint16_t& port, String& username, String& password);

// MQTT status topic (channel) management.
bool mqttSetStatusTopic(const String& topic);
void mqttResetStatusTopic();
String mqttGetStatusTopic();
String mqttGetEventTopic();
String mqttGetAvailabilityTopic();

// Convenience formatter for a single-message Telegram setup command.
String mqttBuildSetupCommand(const String& host, uint16_t port, const String& username, const String& password);
