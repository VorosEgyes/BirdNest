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
#ifndef WIFI_RESCUE_FAIL_COUNT
  #define WIFI_RESCUE_FAIL_COUNT 12
#endif
#ifndef WIFI_RESCUE_PORTAL_INTERVAL_FAILS
  #define WIFI_RESCUE_PORTAL_INTERVAL_FAILS 24
#endif
#ifndef WIFI_RESCUE_PORTAL_TIMEOUT
  #define WIFI_RESCUE_PORTAL_TIMEOUT 180
#endif

// --- OTA ---
#ifndef OTA_HOSTNAME
  #define OTA_HOSTNAME "BirdNestCam"
#endif
#ifndef OTA_PASSWORD
#define OTA_PASSWORD ""
#endif
#ifndef OTA_STALL_TIMEOUT_SEC
  #define OTA_STALL_TIMEOUT_SEC 180
#endif
#ifndef OTA_TIMEOUT_MS
  #define OTA_TIMEOUT_MS 10000
#endif
#ifndef OTA_STARTUP_WINDOW_SEC
  #define OTA_STARTUP_WINDOW_SEC 8
#endif
#ifndef OTA_RECOVERY_WINDOW_SEC
  #define OTA_RECOVERY_WINDOW_SEC 120
#endif
#ifndef OTA_RECOVERY_SLEEP_SEC
  #define OTA_RECOVERY_SLEEP_SEC 900
#endif
#ifndef OTA_RECOVERY_LOW_BATTERY_SLEEP_SEC
  #define OTA_RECOVERY_LOW_BATTERY_SLEEP_SEC 3600
#endif
#ifndef OTA_RECOVERY_CYCLES
  #define OTA_RECOVERY_CYCLES 16
#endif
#ifndef OTA_RECOVERY_MIN_BATTERY_V
  #define OTA_RECOVERY_MIN_BATTERY_V 3.70f
#endif

// --- Hardware ---
#ifndef TEMP_PIN
  #define TEMP_PIN 13
#endif
#ifndef TEMP_SAMPLE_COUNT
  #define TEMP_SAMPLE_COUNT 2
#endif

// --- Camera ---
// FRAMESIZE: 8=VGA(640x480) 9=SVGA(800x600) 10=XGA(1024x768) 12=SXGA 13=UXGA
#ifndef CAMERA_FRAMESIZE_PSRAM
  #define CAMERA_FRAMESIZE_PSRAM 9
#endif
#ifndef CAMERA_JPEG_QUALITY_PSRAM
  #define CAMERA_JPEG_QUALITY_PSRAM 12
#endif
#ifndef CAMERA_FRAMESIZE_NOPSRAM
  #define CAMERA_FRAMESIZE_NOPSRAM 8
#endif
#ifndef CAMERA_JPEG_QUALITY_NOPSRAM
  #define CAMERA_JPEG_QUALITY_NOPSRAM 12
#endif
#ifndef CAMERA_WARMUP_FRAMES
  #define CAMERA_WARMUP_FRAMES 2
#endif
#ifndef CAMERA_UPLOAD_CHUNK_TIMEOUT_MS
  #define CAMERA_UPLOAD_CHUNK_TIMEOUT_MS 8000
#endif
#ifndef CAMERA_RESPONSE_TIMEOUT_MS
  #define CAMERA_RESPONSE_TIMEOUT_MS 15000
#endif
// Image quality adjustments (range -2 to +2; 0 = sensor default)
#ifndef CAMERA_SATURATION
  #define CAMERA_SATURATION 1
#endif
#ifndef CAMERA_CONTRAST
  #define CAMERA_CONTRAST 1
#endif
#ifndef CAMERA_BRIGHTNESS
  #define CAMERA_BRIGHTNESS 0
#endif
#ifndef CAMERA_SHARPNESS
  #define CAMERA_SHARPNESS 1
#endif
// Ambient light register threshold separating night/day mode (0-255)
#ifndef CAMERA_DAY_THRESHOLD
  #define CAMERA_DAY_THRESHOLD 140
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
