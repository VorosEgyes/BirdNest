#pragma once

#include <Arduino.h>

// ============================================================
// telegram.h
// Telegram bot: message sending and incoming command handling.
// Each camera uses its own token and chat IDs (loaded from NVS).
// ============================================================

// Initialise the bot using the stored token.
// Must be called after wifiInit() returns true.
void telegramInit();

// Send a message to a specific chat_id.
// Returns true on success.
bool telegramSend(const char* chatId, const String& message);

// Send a debug message to debugChatId (prefixed with [DEBUG]).
// Returns false when debug chat is not configured or send fails.
// Level: 0=minimal, 1=normal, 2=verbose.
bool telegramSendDebug(const String& message, uint8_t level = 1);

// Runtime debug verbosity (persisted in NVS).
uint8_t telegramGetDebugVerbosity();
void telegramSetDebugVerbosity(uint8_t level);

// Camera orientation runtime settings (persisted in NVS).
bool telegramGetCamMirror();
bool telegramGetCamFlip();
void telegramSetCamMirror(bool enabled);
void telegramSetCamFlip(bool enabled);

// Send a welcome message to the main chat.
// Optionally emits a brief verbose debug note when sending succeeds.
// Returns true if the main chat message was sent successfully.
bool telegramSendWelcome();

// Read and process all messages that arrived while the device was offline.
// Call once in setup(), after telegramInit().
void telegramProcessStartupMessages();

// Handle incoming commands – call periodically from loop().
void telegramLoop();

// Register a callback that telegramLoop() will invoke when /photo is received.
// The callback receives the chat_id to send the photo to.
typedef void (*PhotoCallback)(const char* chatId);
void telegramSetPhotoCallback(PhotoCallback cb);

// Register a callback that telegramLoop() will invoke when a live /sleepXX
// command should put the device to sleep immediately.
typedef void (*SleepCallback)(uint32_t sleepSec);
void telegramSetSleepCallback(SleepCallback cb);
bool telegramIsMaintMode();

// Returns the current deep sleep duration in seconds (0 = disabled).
// Initial value comes from the DEEP_SLEEP_SEC build flag.
// Can be changed at runtime via the /sleepXX Telegram command.
uint32_t telegramGetSleepSec();
