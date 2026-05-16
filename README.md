# BirdNest ESP32-CAM Project

## Complete Boot Sequence (PHASE 1 in setup())

1. **Serial init** — initialize UART at 115200 baud for debug output
2. **tempInit()** — DS18B20 on GPIO13 OneWire bus with internal pull-up
3. **batteryInit()** — GPIO12 ADC setup for battery voltage reading
4. **wifiInit()** — attempt STA connection (15 sec timeout); if fails, enter captive portal mode (180 sec)
5. **otaInit()** and 8-second startup window — check for OTA updates
6. **syncTimeIfNeeded()** — NTP sync with up to 30 retries, 200ms between each
7. **telegramInit()** and startup message processing — initialize Telegram bot and handle first message
8. **nightSleepIfNeeded()** — if after sunset, sleep until sunrise using week-number lookup table
9. **Welcome message** — display welcome message (if not from sleep) and capture startup photo
10. **Final deep sleep** — call `esp_deep_sleep_start()` with saved interval for next wake

---

## Photo Capture Sequence (PHASE 2)

1. **cameraInit()** — configure all 8-bit video pins (D0–D7), control lines (HREF, VSYNC, PCLK), and I2C (SDA, SCL)
2. **PSRAM detection** — detect PSRAM presence and select resolution/quality (SXGA vs VGA)
3. **Warm-up frames** — capture 2 default warm-up frames for AEC/AWB stabilization
4. **Actual JPEG capture** — capture a single JPEG frame into frame buffer
5. **Temperature reading** — read 1–2 samples averaged from DS18B20
6. **Battery voltage reading** — read ADC with calibration
7. **Telegram sendPhoto** — upload JPEG via HTTPS multipart form data to Telegram
8. **Retry logic** — retry upload on failure with exponential backoff
9. **cameraDeinit()** and power-down modes — deinitialize camera and enter low-power state

---

## Telegram Command Processing (PHASE 3 in loop())

- 5-second polling interval
- Update ID persistence every 30 seconds
- Command table: `/photo`, `/sleepXX`, `/maint_on`, `/maint_off`, `/status`, `/reboot`, `/debug0|1|2`, `/mirror0|1`, `/flip0|1`, `/battcal`, `/battcalset`, `/battcalclear`, `/mqtt`, `/mqttset`, `/mqtttopic`, `/mqtttopic_reset`, `/mqttoff`
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
- STA connection attempt (15 sec timeout)
- Rescue captive portal after 12 consecutive failures
- Failure counter tracking

### Telegram
- Bot token stored in NVS
- Poll loop every 5 seconds
- NVS persistence of sleep/maintenance settings
- `lastMsgId` tracking for message updates

### Camera
- AI-Thinker pin mapping: D0–D7 data, HREF/VSYNC/PCLK control, XCLK 20 MHz
- PSRAM detection and resolution/quality selection (SXGA vs VGA)
- Warm-up frames (2 default) for AEC/AWB
- JPEG capture and frame buffer
- Upload chunking via `esp_camera_send_frame()`

### Temperature
- DS18B20 on GPIO13 OneWire protocol with internal pull-up
- `TEMP_SAMPLE_COUNT` samples averaged (1–2)

### Battery
- ADC on GPIO12 with resistor divider formula
- Two-point calibration math using `bCalA`/`bCalB`

### OTA
- 8-second startup window for OTA
- Stall timeout (180 sec) if no response
- Recovery cycles (16) with battery thresholds

### MQTT
- Runtime MQTT client with automatic reconnect
- JSON status publish to a configurable topic (channel)
- Config stored in NVS and editable from Telegram
- Supports auth and no-auth brokers
- Periodic publish (`MQTT_STATUS_INTERVAL_SEC`) and immediate publish on boot/config change

---

## MQTT Setup and Usage

### Default Topic (Channel)

If no custom topic is set, status is published to:

- `birdnest/CAMERA_LABEL/status`

Where `CAMERA_LABEL` comes from `platformio.ini` build flags.

### Telegram Commands for MQTT

- `/mqtt` - show current MQTT config and active channel
- `/mqttset <ip-or-host> <port> <user|-> <pass|->` - set broker and auth in one message
- `/mqtttopic <topic>` - set custom publish channel/topic
- `/mqtttopic_reset` - reset topic to default (`birdnest/CAMERA_LABEL/status`)
- `/mqttoff` - disable MQTT and clear broker credentials

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

### Published payload (status)

Status message is JSON and includes:

- `device`
- `reason` (`boot`, `periodic`, `manual`, `config_updated`, ...)
- `ip`
- `rssi`
- `uptime_s`
- `temp_c`
- `battery_v`
- `battery_pct`
- `maint`

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

