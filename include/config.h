#pragma once

// ============================================================
// config.h – default fallbacks for values defined in platformio.ini
// Do NOT edit here – platformio.ini build_flags are the single source
// of truth; these values are only used if a flag is missing.
// ============================================================

// --- WiFi captive portal ---
#ifndef AP_NAME
  #define AP_NAME "BirdNestCam"
#endif
#ifndef AP_PASSWORD
  #define AP_PASSWORD "birdnest123"
#endif
#ifndef CONFIG_PORTAL_TIMEOUT
  #define CONFIG_PORTAL_TIMEOUT 180
#endif

// --- OTA ---
#ifndef OTA_HOSTNAME
  #define OTA_HOSTNAME "BirdNestCam"
#endif
#ifndef OTA_PASSWORD
  #define OTA_PASSWORD "birdnest_ota"
#endif

// --- Hardware ---
#ifndef TEMP_PIN
  #define TEMP_PIN 13
#endif

// --- Telegram ---
#ifndef PHOTO_INTERVAL_SEC
  #define PHOTO_INTERVAL_SEC 300
#endif

// --- Power saving ---
#ifndef DEEP_SLEEP_SEC
  #define DEEP_SLEEP_SEC 0
#endif

// --- NTP / local time ---
#ifndef NTP_TZ
  #define NTP_TZ "CET-1CEST,M3.5.0/2,M10.5.0/3"
#endif
#ifndef NTP_SERVER_1
  #define NTP_SERVER_1 "pool.ntp.org"
#endif
#ifndef NTP_SERVER_2
  #define NTP_SERVER_2 "time.google.com"
#endif
#ifndef NTP_SERVER_3
  #define NTP_SERVER_3 "time.cloudflare.com"
#endif

// --- NVS (Preferences) namespace ---
#define NVS_NAMESPACE "birdnest"

// --- Buffer sizes ---
#define BOT_TOKEN_LEN  150
#define CHAT_ID_LEN     32
