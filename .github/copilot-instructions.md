# BirdNest — Copilot Instructions

## What this project is
Battery-aware ESP32-CAM (AI-Thinker) wildlife/bird-nest camera. Captures
photos on schedule or Telegram command, uploads via HTTPS multipart to
Telegram, optional MQTT telemetry, deep sleep power management, OTA updates.
Multiple physical camera units share one codebase, differentiated only by
PlatformIO build environments.

## Multi-camera build model — critical, don't break this
`platformio.ini` has ONE shared `[env]` block with all build_flags, and thin
per-camera envs (`cam1`..`cam4`, plus `_ota` variants) that only override
`AP_NAME`, `CAMERA_LABEL`, `OTA_HOSTNAME`, and `upload_port`/`upload_protocol`.
- When adding a new build flag or feature, put it in the shared `[env]` block,
  not in an individual `camN` env, unless the feature is genuinely per-camera.
- When adding a new physical camera, copy the `cam3`/`cam3_ota` pattern, not
  `cam1` (cam1 has commented-out `upload_port`, less representative).
- `default_envs` is currently `cam3_ota` — don't assume `cam1` is the active
  target when reasoning about "the" build.
- OTA envs use either a static IP (`192.168.0.14`, `.232`) or an mDNS hostname
  (`BravoNest.local`, `BirdNestDelta.local`). Both patterns are valid; match
  whichever the specific camera already uses.

## Two preset profiles — respect the active/inactive convention
The `.ini` encodes two tuning presets as comment-toggle pairs:
- **AGGRESSIVE RELIABILITY** (currently active) — more retries, longer
  timeouts, tuned for remote/unstable links (`CAMERA_FB_GET_RETRIES=3`,
  `PHOTO_SEND_MAX_RETRIES=4`, `WIFI_RUNTIME_REBOOT_AFTER_SEC=300`)
- **CONSERVATIVE POWER** (commented out) — fewer retries, shorter timeouts,
  tuned for battery life
When asked to tune reliability/power tradeoffs, edit the *active* block and
keep the *inactive* block's values in sync as a commented alternative —
this is the established pattern, don't delete the inactive block.

## Camera pipeline (PHASE 2) — exact sequence, don't reorder
1. `cameraInit()` — AI-Thinker pin config (D0–D7, HREF/VSYNC/PCLK, XCLK 20MHz)
2. PSRAM detected → `CAMERA_FRAMESIZE_PSRAM`/`CAMERA_JPEG_QUALITY_PSRAM`
   (currently UXGA/quality 3, "live-parity" profile); no PSRAM → fallback
   profile with `fb_count=1`
3. Init retry on `ESP_ERR_INVALID_STATE` (deinit + 500ms retry)
4. Sensor tuning: white balance, AGC/AEC, mirror/flip, light-based register
   ladder against ambient register `0x2f` vs `CAMERA_DAY_THRESHOLD` (140)
5. `CAMERA_WARMUP_FRAMES` (4) warm-up captures with `CAMERA_FB_GET_RETRIES`
6. Final single retried fallback grab if all warm-up attempts fail
7. HTTPS multipart upload to Telegram `sendPhoto`, 8KB chunks, `WiFiClientSecure`
8. Response validated by `"ok":true` parsing only — don't treat HTTP 200 alone
   as success
9. Outer retry in `captureAndSendPhoto()`: WiFi reconnect + backoff
   (`PHOTO_SEND_RETRY_BACKOFF_MS * attempt`)
10. `cameraDeinit()` + 100ms wait before any next init

## Exposure/lowlight logic — implementation reality, not the flag names
AGC is OFF (`set_gain_ctrl(0)`), gain is manual (`set_agc_gain(0)`); exposure
is controlled entirely by a register ladder against `0x2f`, with fine-tuning
on `0x47`/`0x2a`/`0x2b` post-frame. **`CAMERA_DYNAMIC_EXPOSURE_PROFILE` and
the `CAMERA_DAY_*`/`CAMERA_LOWLIGHT_*` flag families are NOT used by the
current implementation** — don't suggest using them or assume they're wired
up; they're vestigial build flags. If asked to improve exposure handling,
work within the register-ladder approach unless explicitly asked to replace it.

## Error string contract
`cameraGetLastError()` returns specific lowercase_snake_case strings
(`empty_chat_id`, `missing_bot_token`, `wifi_not_connected_before_upload`,
`telegram_tls_connect_failed`, `camera_fb_get_failed_final`,
`upload_failed_headers_or_prefix`, `upload_chunk_write_failed_offset_N`,
`upload_multipart_tail_failed`, `telegram_response_not_ok_empty_body`,
`telegram_response_not_ok_...`). When adding new failure paths, follow this
naming convention and report through the same channel (Telegram debug chat),
not just Serial — these devices run headless in the field.

## Battery / ADC2 constraint — do not regress this
`BATTERY_ADC_PIN=12` is ADC2 on ESP32. **ADC2 is unreliable while WiFi is
connected.** The firmware works around this by sampling once at boot
(`batteryRefresh()` in setup, before WiFi connects) and caching that value
for the rest of the awake period — `/status` reports the cached boot-time
sample, not a live read, whenever WiFi is up. Any code touching battery
reading must preserve this cache-before-WiFi pattern; reading ADC2 live while
WiFi is connected will silently return garbage.

## NVS-backed runtime config — don't hardcode what's already a Telegram setting
These are persisted in NVS and editable at runtime via Telegram commands —
don't add a second compile-time path for the same thing:
`botToken`, `chatId`, `debugChatId`, `sleepSec`, `maintMode`, `debugVerbosity`,
`camMirror`, `camFlip`, `lastMsgId`, `bCalEn`, `bCalA`/`bCalB`,
`calibrationPoints`, `otaArmed`, `otaCycles`, `wifiFail`, `mqttHost`,
`mqttPort`, `mqttUser`, `mqttPass`, `mqttTopic`.

## WiFi state machine — five distinct phases, don't collapse them
1. Boot-time STA connect (`WIFI_BOOT_CONNECT_RETRIES`,
   `WIFI_BOOT_RETRY_BACKOFF_SEC`, fail-fast via `WIFI_FAIL_FAST_SEC`)
2. Rescue captive portal (opens on missing Telegram creds, or after
   `WIFI_RESCUE_FAIL_COUNT` repeated failures; separate timeout
   `WIFI_RESCUE_PORTAL_TIMEOUT` vs normal `CONFIG_PORTAL_TIMEOUT`)
3. Boot failure fallback → deep sleep backoff (`WIFI_RETRY_BACKOFF_SEC`, or
   OTA recovery sleep timing if recovery is armed)
4. Runtime link-loss handling while looping (`WIFI_RUNTIME_RECONNECT_INTERVAL_SEC`,
   failsafe reboot after `WIFI_RUNTIME_REBOOT_AFTER_SEC`)
5. OTA interaction: `otaLoop()` runs first each loop iteration; deep sleep is
   suppressed during active OTA; stall watchdog is `OTA_STALL_TIMEOUT_SEC`
Maintenance mode suppresses sleep/photo decisions but does NOT bypass WiFi
requirements — don't let a maintenance-mode code path skip reconnect logic.

## MQTT topic/payload contract — keep schema_version in sync
Default topics: `birdnest/<CAMERA_LABEL>/status`, `.../event`,
`.../availability`. Custom topic via `/mqtttopic`: if it ends in `/status`,
event/availability are derived as siblings; otherwise `/event` and
`/availability` are appended — preserve this derivation logic, don't hardcode
suffixes. Status/event payloads carry `schema_version` — bump it if you
change the payload shape, since this is consumed by OpenHAB on the NAS side.
LWT: `online` (retained, on connect) / `offline` (retained, LWT or explicit
disable).

## Build / upload
```
pio run -e cam3_ota -t upload          # current default target
pio run -e cam1 -t upload --upload-port /dev/cu.usbserial-XXXX
```

## Network context
- MQTT broker: 192.168.0.196:1883, no auth, IoT VLAN (Pres-iot)
- OpenHAB on the same NAS consumes the MQTT status/event/availability topics

## What NOT to suggest
- Don't suggest reading ADC2 (GPIO12) live while WiFi is connected — see
  battery section above
- Don't suggest enabling `CAMERA_DYNAMIC_EXPOSURE_PROFILE` or the
  `CAMERA_DAY_*`/`CAMERA_LOWLIGHT_*` flags — they're disconnected from the
  current register-ladder exposure implementation
- Don't add a cloud dependency (Blynk, Adafruit IO, etc.) — local-only by design
- Don't suggest Arduino IDE workflows — PlatformIO multi-env only
- Don't flatten the per-camera env overrides into the shared `[env]` block
