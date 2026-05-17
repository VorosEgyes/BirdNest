#include "net_health.h"

static uint32_t s_reconnectAttempts = 0;
static uint32_t s_disconnectCount = 0;
static unsigned long s_lastDisconnectMs = 0;
static unsigned long s_disconnectStartMs = 0;
static bool s_disconnected = false;

void netHealthOnBootConnected() {
    s_disconnected = false;
    s_disconnectStartMs = 0;
}

void netHealthOnWifiDown() {
    if (s_disconnected) return;

    s_disconnected = true;
    s_disconnectStartMs = millis();
    s_lastDisconnectMs = s_disconnectStartMs;
    ++s_disconnectCount;
}

void netHealthOnReconnectAttempt() {
    ++s_reconnectAttempts;
}

void netHealthOnReconnectSuccess() {
    s_disconnected = false;
    s_disconnectStartMs = 0;
}

uint32_t netHealthGetReconnectAttempts() {
    return s_reconnectAttempts;
}

uint32_t netHealthGetDisconnectCount() {
    return s_disconnectCount;
}

unsigned long netHealthGetLastDisconnectUptimeSec() {
    return s_lastDisconnectMs / 1000UL;
}

unsigned long netHealthGetCurrentDisconnectDurationSec() {
    if (!s_disconnected || s_disconnectStartMs == 0) return 0;
    return (millis() - s_disconnectStartMs) / 1000UL;
}

bool netHealthIsDisconnected() {
    return s_disconnected;
}
