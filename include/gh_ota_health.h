#pragma once

#include <ArduinoJson.h>

inline const char* ghOtaHealthResponseError(const char* body, size_t length) {
    StaticJsonDocument<128> filter;
    filter["rate"]["limit"] = true;

    StaticJsonDocument<256> doc;
    const DeserializationError error = deserializeJson(
        doc, body, length, DeserializationOption::Filter(filter));
    if (error) return error.c_str();
    if (!doc["rate"]["limit"].is<unsigned long>()) return "InvalidResponse";
    return nullptr;
}
