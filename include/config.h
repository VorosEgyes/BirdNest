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
#ifndef CAMERA_LABEL
  #define CAMERA_LABEL AP_NAME
#endif
#ifndef AP_PASSWORD
  #define AP_PASSWORD "birdnest123"
#endif
#ifndef CONFIG_PORTAL_TIMEOUT
  #define CONFIG_PORTAL_TIMEOUT 180
#endif
#ifndef WIFI_FAIL_FAST_SEC
  #define WIFI_FAIL_FAST_SEC 15
#endif
#ifndef WIFI_ENABLE_CAPTIVE_PORTAL
  #define WIFI_ENABLE_CAPTIVE_PORTAL 0
#endif

// --- OTA ---
#ifndef OTA_HOSTNAME
  #define OTA_HOSTNAME "BirdNestCam"
#endif
#ifndef OTA_PASSWORD
  #define OTA_PASSWORD "birdnest_ota"
#endif
#ifndef OTA_STALL_TIMEOUT_SEC
  #define OTA_STALL_TIMEOUT_SEC 180
#endif
#ifndef OTA_TIMEOUT_MS
  #define OTA_TIMEOUT_MS 10000
#endif

// --- Hardware ---
#ifndef TEMP_PIN
  #define TEMP_PIN 13
#endif
#ifndef TEMP_SAMPLE_COUNT
  #define TEMP_SAMPLE_COUNT 2
#endif

#ifndef BATTERY_ADC_PIN
  #define BATTERY_ADC_PIN 12
#endif
#ifndef BATTERY_ADC_SAMPLES
  #define BATTERY_ADC_SAMPLES 8
#endif
#ifndef BATTERY_ADC_SETTLE_US
  #define BATTERY_ADC_SETTLE_US 5000
#endif
#ifndef BATTERY_CAL_MULT
  #define BATTERY_CAL_MULT 1.00f
#endif
#ifndef BATTERY_ADC_VREF
  #define BATTERY_ADC_VREF 3.3f
#endif
#ifndef BATTERY_ADC_MAX
  #define BATTERY_ADC_MAX 4095.0f
#endif
#ifndef BATTERY_DIVIDER_RTOP
  #define BATTERY_DIVIDER_RTOP 2000000.0f
#endif
#ifndef BATTERY_DIVIDER_RBOTTOM
  #define BATTERY_DIVIDER_RBOTTOM 1000000.0f
#endif
#ifndef BATTERY_EMPTY_V
  #define BATTERY_EMPTY_V 3.20f
#endif
#ifndef BATTERY_FULL_V
  #define BATTERY_FULL_V 4.20f
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
