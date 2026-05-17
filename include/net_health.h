#pragma once

#include <Arduino.h>

// Runtime network health counters for diagnostics via Telegram.
void netHealthOnBootConnected();
void netHealthOnWifiDown();
void netHealthOnReconnectAttempt();
void netHealthOnReconnectSuccess();

uint32_t netHealthGetReconnectAttempts();
uint32_t netHealthGetDisconnectCount();
unsigned long netHealthGetLastDisconnectUptimeSec();
unsigned long netHealthGetCurrentDisconnectDurationSec();
bool netHealthIsDisconnected();
