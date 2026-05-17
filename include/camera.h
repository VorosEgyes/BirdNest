#pragma once

#include <Arduino.h>

// Initialise the camera hardware and apply auto-exposure settings.
// Returns true on success, reboots on failure.
bool cameraInit();

// Deinitialise the camera to save power before deep sleep.
void cameraDeinit();

// Capture a JPEG photo and send it to the given Telegram chat ID.
// Returns true if the photo was successfully uploaded.
bool cameraSendPhoto(const char* chatId);

// Returns details about the last photo send failure for remote diagnostics.
String cameraGetLastError();
