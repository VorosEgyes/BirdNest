# BirdNest ESP32-CAM Project

## Complete Boot Sequence (PHASE 1 in setup())

1. **Serial init** — initialize UART at 115200 baud for debug output
2. **tempInit()** — DS18B20 on GPIO13 OneWire bus with internal pull-up
3. **batteryInit()** — GPIO12 ADC setup for battery voltage reading
4. **WiFi connect phase** — STA connect with boot retries; rescue captive portal on repeated failures; deep-sleep fallback when boot connectivity cannot be recovered
5. **otaInit()** and startup OTA window — check for OTA updates (`OTA_STARTUP_WINDOW_SEC`, or `OTA_RECOVERY_WINDOW_SEC` when recovery is armed)
6. **syncTimeIfNeeded()** — NTP sync with up to 30 retries, 200ms between each
7. **telegramInit()** and startup message processing — initialize Telegram bot and handle first message
8. **nightSleepIfNeeded()** — if after sunset, sleep until sunrise using week-number lookup table
9. **Welcome / startup photo decision** — send welcome message only on normal boot; on timer wake, capture+send photo if maintenance mode is off
10. **Final deep sleep decision** — call `esp_deep_sleep_start()` when sleep interval is enabled and OTA is not active

---

## Photo Capture Sequence (PHASE 2)

1. **cameraInit()** — configure AI-Thinker pins (D0-D7, HREF, VSYNC, PCLK, XCLK, SCCB), JPEG mode, and grab mode
2. **PSRAM profile select** — if PSRAM is present use PSRAM frame/quality flags and `fb_count=2`, otherwise fallback profile with `fb_count=1`
3. **Init resilience** — handle `ESP_ERR_INVALID_STATE` with deinit+retry, plus second init retry after 500 ms
4. **Sensor tuning** — apply white balance, AGC/AEC settings, orientation (`/mirror` and `/flip`), and light-based OV2640 register ladder
5. **Warm-up capture phase** — capture `CAMERA_WARMUP_FRAMES` frames (current active profile: 4), with frame-grab retries (`CAMERA_FB_GET_RETRIES`)
6. **Final fallback capture** — if all warm-up grabs fail, run one final retried frame-grab attempt
7. **HTTPS multipart upload** — send Telegram `sendPhoto` request with chunked JPEG write (`8 KB` chunks) over `WiFiClientSecure`
8. **Response validation** — parse response body and treat only `"ok":true` as success; store detailed failure reason otherwise
9. **Upload retry loop** — outer retry in `captureAndSendPhoto()` with WiFi reconnect and progressive backoff (`PHOTO_SEND_RETRY_BACKOFF_MS * attempt`)
10. **cameraDeinit()** — deinitialize camera and wait 100 ms before any next init

---

## Telegram Command Processing (PHASE 3 in loop())

- 5-second polling interval
- Update ID persistence every 30 seconds
- Command table: `/photo`, `/sleepXX`, `/maint_on`, `/maint_off`, `/status`, `/netdiag`, `/reboot`, `/reset_config`, `/debug0|1|2`, `/mirror0|1`, `/flip0|1`, `/battcal`, `/battcalset`, `/battcalclear`, `/mqtt`, `/mqttset`, `/mqtttopic`, `/mqtttopic_reset`, `/mqttoff`
- Callback execution for each command

---

## Deep Sleep & Wakeup (PHASE 4)

- ESP32 hibernates: CPU off, RTC timer running
- Current draw: 100–500 µA during deep sleep
- Wakeup detection via `esp_sleep_get_wakeup_cause()`
- `fromSleep` flag behavior: sets `fromSleep` to true on wake, false on normal boot

---

## Detailed Module Descriptions

### WiFi Manager
- Telegram credential check from NVS (`botToken`, `chatId`, `debugChatId`) before connect flow
- Fail-fast STA reconnect path (`WIFI_FAIL_FAST_SEC`) when captive portal is disabled
- Rescue captive portal opens on missing Telegram fields or repeated boot failures
- Persistent WiFi failure counter (`wifiFail`) in NVS; reset to 0 on successful connect

## WiFi Connection Lifecycle (full program behavior)

### 1) Boot-time connection strategy

- The device first loads Telegram credentials and WiFi failure counter from NVS.
- If captive portal is disabled and Telegram fields are present, it tries normal STA reconnect first (`wifiInit()`).
- Boot retries are applied by the main program:
	- `WIFI_BOOT_CONNECT_RETRIES`
	- `WIFI_BOOT_RETRY_BACKOFF_SEC`
- In fail-fast mode, each WiFi attempt uses `WIFI_FAIL_FAST_SEC` timeout.

### 2) Rescue captive portal fallback

- If Telegram credentials are missing, captive portal is opened immediately.
- If `WIFI_ENABLE_CAPTIVE_PORTAL != 0`, portal path is always allowed.
- With repeated STA failures, rescue portal opens after `WIFI_RESCUE_FAIL_COUNT` failures.
- Optional periodic rescue windows use `WIFI_RESCUE_PORTAL_INTERVAL_FAILS`.
- Portal timeout uses `WIFI_RESCUE_PORTAL_TIMEOUT` (rescue) or `CONFIG_PORTAL_TIMEOUT` (normal).
- Captive portal includes custom fields for Telegram token, main chat ID, and debug chat ID.

### 3) Boot failure fallback (failsafe deep sleep)

- If WiFi cannot be established after boot retries, device enters deep sleep backoff.
- Default backoff path uses `WIFI_RETRY_BACKOFF_SEC`.
- If OTA recovery is armed, recovery sleep timing is used instead (`otaGetRecoverySleepSeconds`), including low-battery protection.

### 4) Runtime link-loss handling (while running)

- The loop continuously checks WiFi state before network-heavy tasks.
- On disconnect:
	- reconnect attempts are triggered every `WIFI_RUNTIME_RECONNECT_INTERVAL_SEC`
	- diagnostics counters are updated (`/netdiag`)
- If disconnected too long, failsafe reboot is triggered after `WIFI_RUNTIME_REBOOT_AFTER_SEC`.

### 5) OTA interaction

- OTA processing runs first in loop (`otaLoop()`).
- While OTA is active, other network work is deferred.
- Deep sleep is suppressed during active OTA transfer.
- Startup OTA polling window is dynamic: normal `OTA_STARTUP_WINDOW_SEC`, or extended `OTA_RECOVERY_WINDOW_SEC` when recovery mode is armed.
- OTA transfer watchdog restarts the device if no OTA events arrive for `OTA_STALL_TIMEOUT_SEC`.

### 6) Maintenance mode behavior

- Maintenance mode suppresses automatic sleep/photo cycle decisions, but does not bypass WiFi requirements.
- If network quality is poor, runtime reconnect/failsafe logic still applies.
- Manual diagnostics command: `/netdiag`.

### Telegram
- Bot token stored in NVS
- Poll loop every 5 seconds
- NVS persistence of sleep/maintenance settings
- `lastMsgId` tracking for message updates

### Camera
- AI-Thinker pin mapping: D0–D7 data, HREF/VSYNC/PCLK control, XCLK 20 MHz
- PSRAM-aware frame profile (`CAMERA_FRAMESIZE_*`, `CAMERA_JPEG_QUALITY_*`, `fb_count`)
- Warm-up frames from build flag (`CAMERA_WARMUP_FRAMES`, active profile uses 4)
- JPEG capture and frame buffer
- Upload via HTTPS multipart POST using `WiFiClientSecure` and `writeAll()` helper
- Manual lowlight/day exposure register ladder based on ambient light register (`0x2f`)
- Multi-attempt Telegram photo upload with reconnect/backoff on failure
- Remote error diagnostics via Telegram debug messages (serial not required)

### Camera Exposure / Lowlight Logic (actual implementation)
- Ambient light value is read from sensor register `0x2f`
- `CAMERA_DAY_THRESHOLD` separates lowlight and daylight branches
- AGC is disabled (`set_gain_ctrl(0)`), gain is manual (`set_agc_gain(0)`), and exposure is controlled by register ladder writes
- A post-frame fine-tuning pass adjusts `0x47`, `0x2a`, and `0x2b` for very low to medium light
- Current implementation does not use `CAMERA_DYNAMIC_EXPOSURE_PROFILE`, `CAMERA_DAY_*`, or `CAMERA_LOWLIGHT_*` flag families

### Photo Upload Reliability and Remote Diagnostics
- Upload attempts are retried with progressive backoff and WiFi reconnect between tries.
- Retry behavior is configurable with:
	- `PHOTO_SEND_MAX_RETRIES`
	- `PHOTO_SEND_RETRY_BACKOFF_MS`
	- `CAMERA_FB_GET_RETRIES`
	- `CAMERA_FB_GET_RETRY_DELAY_MS`
- On each failed attempt, the device sends detailed failure reason to Telegram debug chat.
- Final failure message includes the last known upload error cause.

Common remote error reasons (`cameraGetLastError`):

- `empty_chat_id` - no chat ID was provided
- `missing_bot_token` - Telegram bot token is missing/empty
- `wifi_not_connected_before_upload` - WiFi dropped before upload start
- `telegram_tls_connect_failed` - TLS connection to `api.telegram.org:443` failed
- `camera_fb_get_failed_final` - frame grab failed after warm-up and final fallback attempt
- `upload_failed_headers_or_prefix` - multipart request header/prefix write failed
- `upload_chunk_write_failed_offset_N` - JPEG data upload interrupted at byte offset
- `upload_multipart_tail_failed` - multipart tail write failed
- `telegram_response_not_ok_empty_body` - Telegram returned non-OK with empty body
- `telegram_response_not_ok_...` - Telegram API responded with `ok:false` and body snippet

### Temperature
- DS18B20 on GPIO13 OneWire protocol with internal pull-up
- `TEMP_SAMPLE_COUNT` samples averaged (1–2)

### Battery
- ADC on GPIO12 with resistor divider formula
- Two-point calibration math using `bCalA`/`bCalB`

### OTA
- Startup OTA window: `OTA_STARTUP_WINDOW_SEC` (default 8 s)
- Extended recovery window: `OTA_RECOVERY_WINDOW_SEC` (default 120 s) when recovery latch is armed
- OTA stall watchdog: restart if transfer is idle for `OTA_STALL_TIMEOUT_SEC`
- Recovery sleep policy: `OTA_RECOVERY_SLEEP_SEC`, with low-battery fallback `OTA_RECOVERY_LOW_BATTERY_SLEEP_SEC` below `OTA_RECOVERY_MIN_BATTERY_V`
- Recovery state is persisted in NVS via `otaArmed` and `otaCycles`

### MQTT
- Runtime MQTT client with automatic reconnect
- JSON status publish to a configurable state topic (channel)
- Config stored in NVS and editable from Telegram
- Supports auth and no-auth brokers
- Periodic publish (`MQTT_STATUS_INTERVAL_SEC`) and immediate publish on boot/config change
- LWT availability support (`online` / `offline`, retained)
- Separate state/event/availability topic model
- Payload schema versioning (`schema_version`)

---

## MQTT Setup and Usage

### Default Topics

If no custom topic is set, these topics are used:

- State topic: `birdnest/CAMERA_LABEL/status`
- Event topic: `birdnest/CAMERA_LABEL/event`
- Availability topic: `birdnest/CAMERA_LABEL/availability`

Where `CAMERA_LABEL` comes from `platformio.ini` build flags.

If you set a custom topic with `/mqtttopic`:

- The custom value is used as the state topic.
- If it ends with `/status`, event and availability are derived as sibling topics.
- Otherwise `/event` and `/availability` are appended.

### Telegram Commands for MQTT

- `/mqtt` - show current MQTT config and active channel
- `/mqttset <ip-or-host> <port> <user|-> <pass|->` - set broker and auth in one message
- `/mqtttopic <topic>` - set custom publish channel/topic
- `/mqtttopic_reset` - reset topic to default (`birdnest/CAMERA_LABEL/status`)
- `/mqttoff` - disable MQTT and clear broker credentials

`/mqtt` now reports:

- State topic
- Event topic
- Availability topic
- Schema version

### One-message setup examples

- Auth enabled:
	- `/mqttset 192.168.1.100 1883 mqtt_user mqtt_pass`
- No auth:
	- `/mqttset 192.168.1.100 1883 - -`

### Channel/topic examples

- Set custom channel:
	- `/mqtttopic birdnest/BirdNestCam1/status`
- Reset to default channel:
	- `/mqtttopic_reset`

### Published payloads

State payload (`status`) is JSON and includes:

- `schema_version`
- `device`
- `reason` (`boot`, `periodic`, `manual`, `config_updated`, ...)
- `ip`
- `rssi`
- `uptime_s`
- `temp_c`
- `battery_v`
- `battery_pct`
- `maint`

Event payload (`event`) is JSON and includes:

- `schema_version`
- `device`
- `event`
- `detail`
- `uptime_s`

Availability payload (`availability`) values:

- `online` (retained on successful connect)
- `offline` (retained via LWT or explicit MQTT disable)

---

## NVS Storage Structure

| Key | Type | Description |
|---|---|---|
| `botToken` | string | Telegram bot token |
| `chatId` | string | Telegram chat ID |
| `debugChatId` | string | Debug chat ID (WiFi) |
| `sleepSec` | int | Sleep interval in seconds |
| `maintMode` | int | Maintenance mode (0=off, 1=on) |
| `debugVerbosity` | int | Debug verbosity level |
| `camMirror` | int | Camera mirror flip |
| `camFlip` | int | Camera vertical flip |
| `lastMsgId` | int | Last Telegram message ID |
| `bCalEn` | int | Battery calibration enabled |
| `bCalA` / `bCalB` | float | Two-point calibration coefficients |
| `calibrationPoints` | array | Array of (voltage, temp) calibration points |
| `otaArmed` | int | OTA armed flag |
| `otaCycles` | int | OTA recovery cycles |
| `wifiFail` | int | WiFi connection failure counter |
| `mqttHost` | string | MQTT broker host/IP |
| `mqttPort` | int | MQTT broker port |
| `mqttUser` | string | MQTT username (optional) |
| `mqttPass` | string | MQTT password (optional) |
| `mqttTopic` | string | Custom MQTT publish topic (optional) |

---

## Power Consumption & Battery Life

- Awake: ~80–150 mA
- WiFi connecting: ~150 mA
- Camera: ~200 mA
- Deep sleep: ~0.1–0.5 mA

Example: 2000 mAh battery with 5-min photo interval = 100+ hours of operation
Night sleep (12 hours OFF) saves 50%+ battery

---

## Complete Hardware Pin Mapping (AI-Thinker ESP32-CAM)

| Function | Pin | Notes |
|---|---|---|
| XCLK | GPIO0 | 20 MHz camera clock |
| Camera D0 (Y2) | GPIO5 | Data pin |
| Camera D1 (Y3) | GPIO18 | Data pin |
| Camera D2 (Y4) | GPIO19 | Data pin |
| Camera D3 (Y5) | GPIO21 | Data pin |
| Camera D4 (Y6) | GPIO36 | Data pin |
| Camera D5 (Y7) | GPIO39 | Data pin |
| Camera D6 (Y8) | GPIO34 | Data pin |
| Camera D7 (Y9) | GPIO35 | Data pin |
| HREF | GPIO23 | Control line |
| VSYNC | GPIO25 | Control line |
| PCLK | GPIO22 | Control line |
| SDA (I2C) | GPIO26 | Camera I2C data |
| SCL (I2C) | GPIO27 | Camera I2C clock |
| OneWire (DS18B20) | GPIO13 | OneWire bus |
| ADC (Battery) | GPIO12 | Battery voltage measurement |
| Flash LED | GPIO4 | PWM control |

