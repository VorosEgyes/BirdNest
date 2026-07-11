#include "camera.h"
#include "wifi_manager.h"
#include "telegram.h"
#include "config.h"

#include <Arduino.h>
#include "esp_camera.h"
#include <WiFiClientSecure.h>

// ============================================================
// AI-Thinker ESP32-CAM pin definitions
// ============================================================
#define CAM_PIN_PWDN     32
#define CAM_PIN_RESET    -1
#define CAM_PIN_XCLK      0
#define CAM_PIN_SIOD     26
#define CAM_PIN_SIOC     27
#define CAM_PIN_Y9       35
#define CAM_PIN_Y8       34
#define CAM_PIN_Y7       39
#define CAM_PIN_Y6       36
#define CAM_PIN_Y5       21
#define CAM_PIN_Y4       19
#define CAM_PIN_Y3       18
#define CAM_PIN_Y2        5
#define CAM_PIN_VSYNC    25
#define CAM_PIN_HREF     23
#define CAM_PIN_PCLK     22

// Flash LED
#define FLASH_LED_PIN     4
#define FLASH_CHANNEL     7
#define FLASH_FREQ     5000
#define FLASH_RES         8

static bool s_flashInited = false;
static bool s_cameraInitialized = false;
static String s_lastPhotoError = "none";

static void setLastPhotoError(const String& reason) {
    s_lastPhotoError = reason;
    Serial.println("[CAM] fail reason: " + reason);
}

static camera_fb_t* getFrameWithRetries(const char* phase, int index) {
    const int retries = CAMERA_FB_GET_RETRIES > 0 ? CAMERA_FB_GET_RETRIES : 1;
    for (int attempt = 1; attempt <= retries; ++attempt) {
        camera_fb_t* fb = esp_camera_fb_get();
        if (fb) return fb;

        Serial.println("[CAM] fb_get failed at " + String(phase) + " " + String(index) +
                       " attempt " + String(attempt) + "/" + String(retries));
        if (attempt < retries) {
            delay(CAMERA_FB_GET_RETRY_DELAY_MS);
            yield();
        }
    }
    return nullptr;
}

static bool writeAll(WiFiClientSecure& client, const uint8_t* data, size_t len, unsigned long timeoutMs) {
    size_t totalWritten = 0;
    unsigned long start = millis();
    while (totalWritten < len) {
        if (!client.connected()) {
            Serial.println("[CAM] writeAll: client disconnected");
            return false;
        }
        size_t written = client.write(data + totalWritten, len - totalWritten);
        if (written == 0) {
            if ((millis() - start) > timeoutMs) {
                Serial.println("[CAM] writeAll timeout");
                return false;
            }
            delay(5);
            continue;
        }
        totalWritten += written;
        start = millis();
        yield();
    }
    return true;
}

static void flashOff() {
    if (!s_flashInited) {
        ledcSetup(FLASH_CHANNEL, FLASH_FREQ, FLASH_RES);
        ledcAttachPin(FLASH_LED_PIN, FLASH_CHANNEL);
        s_flashInited = true;
    }
    ledcWrite(FLASH_CHANNEL, 0);
}

// ============================================================
// Camera init  (identical settings to the working live project)
// ============================================================
bool cameraInit() {
    if (s_cameraInitialized) {
        return true;
    }

    camera_config_t cfg;
    cfg.ledc_channel  = LEDC_CHANNEL_0;
    cfg.ledc_timer    = LEDC_TIMER_0;
    cfg.pin_d0        = CAM_PIN_Y2;
    cfg.pin_d1        = CAM_PIN_Y3;
    cfg.pin_d2        = CAM_PIN_Y4;
    cfg.pin_d3        = CAM_PIN_Y5;
    cfg.pin_d4        = CAM_PIN_Y6;
    cfg.pin_d5        = CAM_PIN_Y7;
    cfg.pin_d6        = CAM_PIN_Y8;
    cfg.pin_d7        = CAM_PIN_Y9;
    cfg.pin_xclk      = CAM_PIN_XCLK;
    cfg.pin_pclk      = CAM_PIN_PCLK;
    cfg.pin_vsync     = CAM_PIN_VSYNC;
    cfg.pin_href      = CAM_PIN_HREF;
    cfg.pin_sccb_sda  = CAM_PIN_SIOD;
    cfg.pin_sccb_scl  = CAM_PIN_SIOC;
    cfg.pin_pwdn      = CAM_PIN_PWDN;
    cfg.pin_reset     = CAM_PIN_RESET;
    cfg.xclk_freq_hz  = 20000000;
    cfg.pixel_format  = PIXFORMAT_JPEG;
    cfg.grab_mode     = CAMERA_GRAB_LATEST;

    if (psramFound()) {
        cfg.frame_size   = static_cast<framesize_t>(CAMERA_FRAMESIZE_PSRAM);
        cfg.jpeg_quality = CAMERA_JPEG_QUALITY_PSRAM;
        cfg.fb_count     = 2;
    } else {
        cfg.frame_size   = static_cast<framesize_t>(CAMERA_FRAMESIZE_NOPSRAM);
        cfg.jpeg_quality = CAMERA_JPEG_QUALITY_NOPSRAM;
        cfg.fb_count     = 1;
    }

    esp_err_t initErr = esp_camera_init(&cfg);
    if (initErr == ESP_ERR_INVALID_STATE) {
        // Camera was already initialized (e.g. deinit did not complete cleanly).
        // Deinit, wait for hardware I2C/DMA to settle, then retry.
        Serial.println("[CAM] already init – deiniting and retrying");
        esp_camera_deinit();
        delay(150);
        initErr = esp_camera_init(&cfg);
    }
    if (initErr != ESP_OK) {
        Serial.println("[CAM] init failed, retrying (500ms)...");
        delay(500);
        if (esp_camera_init(&cfg) != ESP_OK) {
            Serial.println("[CAM] init FAILED (2nd attempt)");
            return false;
        }
    }
    // Allow I2C and DMA to stabilise before sensor register writes and fb_get.
    // This is the critical gap the live project relies on (it never deinits mid-session).
    delay(120);
    Serial.println("[CAM] init OK");

    flashOff();

    // Apply auto-exposure / sensor settings from the live project
    sensor_t* s = esp_camera_sensor_get();
    if (!s) return true;

    // White balance
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);

    // Gain + Exposure – live project parity:
    // AGC is OFF; gain is set to 0 (minimum). The manual OV2640 register ladder
    // in the init sequence below is responsible for controlling exposure time.
    // With AGC ON the hardware would fight our manual 0x45/0x46/0x2a/0x2b writes.
    s->set_gain_ctrl(s, 0);              // AGC OFF – manual exposure via register ladder
    s->set_agc_gain(s, 0);              // manual gain value = 0 (no amplification)
    s->set_gainceiling(s, (gainceiling_t)6); // ceiling retained (used if AGC ever re-enabled)
    s->set_exposure_ctrl(s, 1);          // AEC ON – auto exposure timing (sensor default)
    s->set_aec2(s, 1);                   // AEC DSP ON (sensor default)

    // Lens / correction
    // set_lenc: 0 = lens distortion correction OFF (it can darken the corners on some modules)
    // set_bpc:  1 = black pixel correction ON (repairs dead/dark pixels in software)
    // set_wpc:  1 = white pixel correction ON (repairs hot/bright pixels in software)
    // set_raw_gma: 1 = RAW gamma correction ON (gives a more natural tone curve)
    s->set_lenc(s, 0);
    s->set_bpc(s, 1);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 1);

    // Image quality controls (color, contrast, brightness, sharpness) from build flags, range -2..+2
    // NOTE: baseline defaults remain active; dynamic profile below can override by light condition.
    // Saturation: -2 = grayscale-like, 0 = neutral, +2 = vivid colors
    s->set_saturation(s, CAMERA_SATURATION);
    // Contrast: -2 = flat/washed out, 0 = neutral, +2 = punchy and more defined
    s->set_contrast(s, CAMERA_CONTRAST);
    // Brightness: -2 = darker, 0 = neutral, +2 = brighter (AEC still does the main correction)
    s->set_brightness(s, CAMERA_BRIGHTNESS);
    // Sharpness: -2 = softer, 0 = neutral, +2 = stronger edge enhancement for feather/twig detail
    s->set_sharpness(s, CAMERA_SHARPNESS);

    // Orientation
    s->set_special_effect(s, 0);
    s->set_hmirror(s, telegramGetCamMirror() ? 1 : 0);
    s->set_vflip(s, telegramGetCamFlip() ? 1 : 0);
    s->set_dcw(s, 0);
    s->set_colorbar(s, 0);

    // Read ambient light and apply exposure registers (from live project)
    s->set_reg(s, 0xff, 0xff, 0x01); // bank sel
    int light = s->get_reg(s, 0x2f, 0xff);
    // CAMERA_DAY_THRESHOLD (build flag, default 140): values below this switch to lowlight mode
    // Lower it if dark/cloudy conditions are still treated as daytime; raise it if daytime falls into lowlight mode
    const int DAY_THRESHOLD = CAMERA_DAY_THRESHOLD;
    if (light < DAY_THRESHOLD) {
        // Lowlight mode
        if (light < 45) s->set_reg(s, 0x11, 0xff, 1);
        s->set_reg(s, 0x13, 0xff, 0);
        s->set_reg(s, 0x0c, 0x6,  0x8);
        s->set_reg(s, 0x45, 0x3f, 0x3f);
    } else {
        // Daylight mode – exposure ladder
        s->set_reg(s, 0x2d, 0xff, 0x0);
        s->set_reg(s, 0x2e, 0xff, 0x0);
        s->set_reg(s, 0x47, 0xff, 0x0);

        // 0x45 = exposure fine-tune (live project parity: each bracket includes it)
        if      (light < 150) { s->set_reg(s,0x46,0xff,0xd0); s->set_reg(s,0x2a,0xff,0xff); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0xff); }
        else if (light < 160) { s->set_reg(s,0x46,0xff,0xc0); s->set_reg(s,0x2a,0xff,0xb0); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0x10); }
        else if (light < 170) { s->set_reg(s,0x46,0xff,0xb0); s->set_reg(s,0x2a,0xff,0x80); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0x10); }
        else if (light < 180) { s->set_reg(s,0x46,0xff,0xa8); s->set_reg(s,0x2a,0xff,0x80); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0x10); }
        else if (light < 190) { s->set_reg(s,0x46,0xff,0xa6); s->set_reg(s,0x2a,0xff,0x80); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0x90); }
        else if (light < 200) { s->set_reg(s,0x46,0xff,0xa4); s->set_reg(s,0x2a,0xff,0x80); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0x10); }
        else if (light < 210) { s->set_reg(s,0x46,0xff,0x98); s->set_reg(s,0x2a,0xff,0x60); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0x10); }
        else if (light < 220) { s->set_reg(s,0x46,0xff,0x80); s->set_reg(s,0x2a,0xff,0x20); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0x10); }
        else if (light < 230) { s->set_reg(s,0x46,0xff,0x70); s->set_reg(s,0x2a,0xff,0x20); s->set_reg(s,0x2b,0xff,0xff); s->set_reg(s,0x45,0xff,0x10); }
        else if (light < 240) { s->set_reg(s,0x46,0xff,0x60); s->set_reg(s,0x2a,0xff,0x20); s->set_reg(s,0x2b,0xff,0x80); s->set_reg(s,0x45,0xff,0x10); }
        else if (light < 253) { s->set_reg(s,0x46,0xff,0x10); s->set_reg(s,0x2a,0xff,0x0);  s->set_reg(s,0x2b,0xff,0x40); s->set_reg(s,0x45,0xff,0x10); }
        else                  { s->set_reg(s,0x46,0xff,0x0);  s->set_reg(s,0x2a,0xff,0x0);  s->set_reg(s,0x2b,0xff,0x0);
                                s->set_reg(s,0x45,0xff,0x0);  s->set_reg(s,0x10,0xff,0x0); }

        s->set_reg(s, 0x0f, 0xff, 0x4b);
        s->set_reg(s, 0x03, 0xff, 0xcf);
        s->set_reg(s, 0x3d, 0xff, 0x34);
        s->set_reg(s, 0x11, 0xff, 0x0);
        s->set_reg(s, 0x43, 0xff, 0x11);
    }

    // Consume one warm-up frame after exposure setup.
    // After the grab, apply the fine-grained per-light-value register ladder
    // (ported 1:1 from the live project's configInitCamera).
    // This is the critical second-pass tuning that the live project does post-fb_get.
    camera_fb_t* fb = esp_camera_fb_get();

    // Post-fb fine-tuning for lowlight / medium-light (light < DAY_THRESHOLD).
    // Registers 0x47 (Frame Length MSB), 0x2a/0x2b (line adjust) control
    // effective exposure time. Values decrease as light increases.
    if (light < DAY_THRESHOLD) {
        if      (light == 0)   { s->set_reg(s,0x47,0xff,0x40); s->set_reg(s,0x2a,0xf0,0xf0); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 1)   { s->set_reg(s,0x47,0xff,0x40); s->set_reg(s,0x2a,0xf0,0xd0); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 2)   { s->set_reg(s,0x47,0xff,0x40); s->set_reg(s,0x2a,0xf0,0xb0); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 3)   { s->set_reg(s,0x47,0xff,0x40); s->set_reg(s,0x2a,0xf0,0x70); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 4)   { s->set_reg(s,0x47,0xff,0x40); s->set_reg(s,0x2a,0xf0,0x40); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 5)   { s->set_reg(s,0x47,0xff,0x20); s->set_reg(s,0x2a,0xf0,0x80); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 6)   { s->set_reg(s,0x47,0xff,0x20); s->set_reg(s,0x2a,0xf0,0x40); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 7)   { s->set_reg(s,0x47,0xff,0x20); s->set_reg(s,0x2a,0xf0,0x30); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 8)   { s->set_reg(s,0x47,0xff,0x20); s->set_reg(s,0x2a,0xf0,0x20); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 9)   { s->set_reg(s,0x47,0xff,0x20); s->set_reg(s,0x2a,0xf0,0x10); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light == 10)  { s->set_reg(s,0x47,0xff,0x10); s->set_reg(s,0x2a,0xf0,0x70); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 12)  { s->set_reg(s,0x47,0xff,0x10); s->set_reg(s,0x2a,0xf0,0x60); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 14)  { s->set_reg(s,0x47,0xff,0x10); s->set_reg(s,0x2a,0xf0,0x40); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 18)  { s->set_reg(s,0x47,0xff,0x08); s->set_reg(s,0x2a,0xf0,0xb0); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 20)  { s->set_reg(s,0x47,0xff,0x08); s->set_reg(s,0x2a,0xf0,0x80); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 23)  { s->set_reg(s,0x47,0xff,0x08); s->set_reg(s,0x2a,0xf0,0x60); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 27)  { s->set_reg(s,0x47,0xff,0x04); s->set_reg(s,0x2a,0xf0,0xd0); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 31)  { s->set_reg(s,0x47,0xff,0x04); s->set_reg(s,0x2a,0xf0,0x80); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 35)  { s->set_reg(s,0x47,0xff,0x04); s->set_reg(s,0x2a,0xf0,0x60); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light <= 40)  { s->set_reg(s,0x47,0xff,0x02); s->set_reg(s,0x2a,0xf0,0x70); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 45)   { s->set_reg(s,0x47,0xff,0x02); s->set_reg(s,0x2a,0xf0,0x40); s->set_reg(s,0x2b,0xff,0xff); }
        // medium-light (frame rate higher after 45, so compensate)
        else if (light < 50)   { s->set_reg(s,0x47,0xff,0x04); s->set_reg(s,0x2a,0xf0,0xa0); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 55)   { s->set_reg(s,0x47,0xff,0x04); s->set_reg(s,0x2a,0xf0,0x70); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 65)   { s->set_reg(s,0x47,0xff,0x04); s->set_reg(s,0x2a,0xf0,0x30); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 75)   { s->set_reg(s,0x47,0xff,0x02); s->set_reg(s,0x2a,0xf0,0x80); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 90)   { s->set_reg(s,0x47,0xff,0x02); s->set_reg(s,0x2a,0xf0,0x50); s->set_reg(s,0x2b,0xff,0xbf); }
        else if (light < 100)  { s->set_reg(s,0x47,0xff,0x02); s->set_reg(s,0x2a,0xf0,0x20); s->set_reg(s,0x2b,0xff,0x8f); }
        else if (light < 110)  { s->set_reg(s,0x47,0xff,0x02); s->set_reg(s,0x2a,0xf0,0x10); s->set_reg(s,0x2b,0xff,0x7f); }
        else if (light < 120)  { s->set_reg(s,0x47,0xff,0x01); s->set_reg(s,0x2a,0xf0,0x10); }
        else if (light < 130)  { s->set_reg(s,0x47,0xff,0x00); s->set_reg(s,0x2a,0xf0,0x00); s->set_reg(s,0x2b,0xff,0x2f); }
        else                   { s->set_reg(s,0x47,0xff,0x00); s->set_reg(s,0x2a,0xf0,0x00); s->set_reg(s,0x2b,0xff,0x00); }
        // Magic value: speeds up frame delivery while keeping exposure effective
        s->set_reg(s, 0x43, 0xff, 0x40);
    }

    s->set_reg(s, 0xff, 0xff, 0x00);
    s->set_reg(s, 0xd3, 0xff, 0x8);
    s->set_reg(s, 0x42, 0xff, 0x2f);
    s->set_reg(s, 0x44, 0xff, 3);
    s->set_reg(s, 0x92, 0xff, 0x1);
    s->set_reg(s, 0x93, 0xff, 0x0);

    if (fb) esp_camera_fb_return(fb);

    s_cameraInitialized = true;
    return true;
}

void cameraDeinit() {
    if (!s_cameraInitialized) return;

    esp_camera_deinit();
    s_cameraInitialized = false;
    // Brief delay so I2C/DMA hardware fully settles before any subsequent init.
    delay(100);
}

// ============================================================
// Photo capture + Telegram upload
// ============================================================
bool cameraSendPhoto(const char* chatId) {
    setLastPhotoError("none");
    if (!chatId || chatId[0] == '\0') {
        setLastPhotoError("empty_chat_id");
        return false;
    }

     unsigned long t_start = millis();
     const char* token = getBotToken();
     if (!token || token[0] == '\0') {
         setLastPhotoError("missing_bot_token");
         return false;
     }
     if (WiFi.status() != WL_CONNECTED) {
         Serial.println("[CAM] WiFi not connected before upload");
         setLastPhotoError("wifi_not_connected_before_upload");
         return false;
     }

     flashOff();

     // Take warm-up frames so AEC/AWB stabilises.
     // Keep the last successful warmup frame as final capture candidate.
     const int warmupFrames = CAMERA_WARMUP_FRAMES > 0 ? CAMERA_WARMUP_FRAMES : 1;
     unsigned long t_capture_start = millis();
     camera_fb_t* fb = nullptr;
     for (int i = 0; i < warmupFrames; i++) {
         camera_fb_t* warmupFb = getFrameWithRetries("warmup", i);
         if (!warmupFb) {
             Serial.println("[CAM] warmup frame skipped at index " + String(i));
         } else {
             if (fb) esp_camera_fb_return(fb);
             fb = warmupFb;
         }

         if (i < warmupFrames - 1) {
             // Live-parity stabilization delay between warmup frames.
             // Rollback option: reduce if capture latency is more important than exposure stability.
             for (int d = 0; d < 4; d++) { delay(100); yield(); }
         }
     }

     // If all warmup captures failed, do one mandatory final capture attempt group.
     if (!fb) {
         fb = getFrameWithRetries("final", 0);
     }
     if (!fb) {
         setLastPhotoError("camera_fb_get_failed_final");
         return false;
     }
     unsigned long t_capture_done = millis();
     Serial.println("[CAM] captured " + String(fb->len) + " bytes in " + String(t_capture_done - t_capture_start) + "ms");

    // POST multipart/form-data to Telegram sendPhoto
    const char* host = "api.telegram.org";
    String boundary = "BirdNestBound";

    // Trim token (NVS may include trailing whitespace)
    String tokenStr = String(token);
    tokenStr.trim();

    String head = "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"chat_id\"\r\n\r\n" +
        String(chatId) + "\r\n"
        "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"caption\"\r\n\r\n" +
        String("Cam: ") + String(getDeviceLabel()) + "\r\n"
        "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"photo\"; filename=\"nest.jpg\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n";
    String tail = "\r\n--" + boundary + "--\r\n";

    uint32_t totalLen = head.length() + fb->len + tail.length();
    Serial.println("[CAM] POST length=" + String(totalLen));

    WiFiClientSecure client;
    client.setInsecure();
    client.setTimeout(15000);

    Serial.println("[CAM] connecting to api.telegram.org:443...");
     unsigned long t_connect_start = millis();
     if (!client.connect(host, 443)) {
         Serial.println("[CAM] connect FAILED");
         setLastPhotoError("telegram_tls_connect_failed");
         esp_camera_fb_return(fb);
         return false;
     }
    client.setNoDelay(true);
     unsigned long t_connect_done = millis();
     Serial.println("[CAM] connected in " + String(t_connect_done - t_connect_start) + "ms, sending POST...");

    String requestHeaders =
        "POST /bot" + tokenStr + "/sendPhoto HTTP/1.1\r\n"
        "Host: " + String(host) + "\r\n"
        "Content-Type: multipart/form-data; boundary=" + boundary + "\r\n"
        "Content-Length: " + String(totalLen) + "\r\n"
        "Connection: close\r\n\r\n";
    if (!writeAll(client, reinterpret_cast<const uint8_t*>(requestHeaders.c_str()), requestHeaders.length(), CAMERA_UPLOAD_CHUNK_TIMEOUT_MS) ||
        !writeAll(client, reinterpret_cast<const uint8_t*>(head.c_str()), head.length(), CAMERA_UPLOAD_CHUNK_TIMEOUT_MS)) {
        Serial.println("[CAM] failed to send HTTP headers/body prefix");
        setLastPhotoError("upload_failed_headers_or_prefix");
        esp_camera_fb_return(fb);
        return false;
    }

    uint8_t* buf = fb->buf;
    size_t   len = fb->len;
    const size_t uploadChunk = 8192;
    const size_t progressStep = 65536;
    unsigned long t_send_start = millis();
    size_t sentBytes = 0;
    size_t nextProgressAt = progressStep;
    bool writeFailed = false;
    for (size_t n = 0; n < len; n += uploadChunk) {
        size_t chunk = ((n + uploadChunk) < len) ? uploadChunk : (len - n);
        if (!writeAll(client, buf + n, chunk, CAMERA_UPLOAD_CHUNK_TIMEOUT_MS)) {
            Serial.println("[CAM] upload write failed at offset " + String(n));
            setLastPhotoError("upload_chunk_write_failed_offset_" + String(n));
            writeFailed = true;
            break;
        }
        sentBytes += chunk;
        yield();
        if (sentBytes >= nextProgressAt || sentBytes == len) {
            unsigned long elapsed = millis() - t_send_start;
            unsigned long bps = elapsed > 0 ? static_cast<unsigned long>((sentBytes * 1000ULL) / elapsed) : 0;
            Serial.println("[CAM] upload progress " + String(sentBytes) + "/" + String(len) + " bytes, " + String(bps) + " B/s");
            nextProgressAt += progressStep;
        }
    }
    if (!writeFailed && !writeAll(client, reinterpret_cast<const uint8_t*>(tail.c_str()), tail.length(), CAMERA_UPLOAD_CHUNK_TIMEOUT_MS)) {
        Serial.println("[CAM] failed to send multipart tail");
        setLastPhotoError("upload_multipart_tail_failed");
        writeFailed = true;
    }
    unsigned long t_send_done = millis();
    esp_camera_fb_return(fb);
    fb = nullptr;

    if (writeFailed) {
        client.stop();
        return false;
    }

    Serial.println("[CAM] data sent in " + String(t_send_done - t_send_start) + "ms, waiting for response... (total " + String(t_send_done - t_start) + "ms from start)");

    // Same pattern as the live project:
    // reset timer on every received character so we never cut off mid-response
    String getAll = "";
    String getBody = "";
    bool   state = false;
    unsigned long lastByteMs = millis();
    const unsigned long responseTimeoutMs = CAMERA_RESPONSE_TIMEOUT_MS;
    while ((millis() - lastByteMs) < responseTimeoutMs) {
        delay(50);
        yield();
        while (client.available()) {
            char c = client.read();
            if (state) getBody += c;
            if (c == '\n') {
                if (getAll.length() == 0) state = true;
                getAll = "";
            } else if (c != '\r') {
                getAll += c;
            }
            lastByteMs = millis(); // reset idle timer on every byte
            yield();
        }
        // Exit early on definitive result
        if (getBody.indexOf("\"ok\":true")  >= 0) break;
        if (getBody.indexOf("\"ok\":false") >= 0) break;
        // Exit if server closed the connection and nothing left to read
        if (!client.connected() && !client.available()) break;
    }
    bool ok = getBody.indexOf("\"ok\":true") >= 0;
        unsigned long t_done = millis();
        Serial.println("[CAM] response OK=" + String(ok ? "true" : "false") + ", total time " + String(t_done - t_start) + "ms");
    Serial.println("[CAM] response body: " + getBody.substring(0, 120));
    if (!ok) {
        String bodySnippet = getBody.substring(0, 120);
        bodySnippet.replace("\n", " ");
        bodySnippet.replace("\r", " ");
        if (bodySnippet.length() == 0) {
            setLastPhotoError("telegram_response_not_ok_empty_body");
        } else {
            setLastPhotoError("telegram_response_not_ok_" + bodySnippet);
        }
    }
    client.stop();

    if (fb) esp_camera_fb_return(fb);
    return ok;
}

String cameraGetLastError() {
    return s_lastPhotoError;
}
