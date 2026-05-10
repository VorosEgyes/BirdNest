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
        cfg.frame_size   = FRAMESIZE_UXGA;
        cfg.jpeg_quality = 5;  // Faster than 3, still high quality
        cfg.fb_count     = 2;
    } else {
        cfg.frame_size   = FRAMESIZE_VGA;
        cfg.jpeg_quality = 12;
        cfg.fb_count     = 1;
    }

    if (esp_camera_init(&cfg) != ESP_OK) {
        Serial.println("[CAM] init failed, retrying...");
        delay(500);
        if (esp_camera_init(&cfg) != ESP_OK) {
            Serial.println("[CAM] init FAILED (2nd attempt)");
            return false;
        }
    }
    Serial.println("[CAM] init OK");

    flashOff();

    // Apply auto-exposure / sensor settings from the live project
    sensor_t* s = esp_camera_sensor_get();
    if (!s) return true;

    // White balance
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);

    // Gain + Exposure – auto mode so the sensor adapts to any light condition
    s->set_gain_ctrl(s, 1);              // AGC ON - auto gain
    s->set_gainceiling(s, (gainceiling_t)6); // max auto gain ceiling (128x)
    s->set_exposure_ctrl(s, 1);          // AEC ON - auto exposure
    s->set_aec2(s, 1);                   // AEC DSP algorithm ON

    // Lens / correction
    s->set_lenc(s, 0);
    s->set_bpc(s, 1);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 1);

    // Orientation
    s->set_special_effect(s, 0);
    s->set_hmirror(s, telegramGetCamMirror() ? 1 : 0);
    s->set_vflip(s, telegramGetCamFlip() ? 1 : 0);
    s->set_dcw(s, 0);
    s->set_colorbar(s, 0);

    // Read ambient light and apply exposure registers (from live project)
    s->set_reg(s, 0xff, 0xff, 0x01); // bank sel
    int light = s->get_reg(s, 0x2f, 0xff);
    const int DAY_THRESHOLD = 140;

    if (light < DAY_THRESHOLD) {
        // Night mode
        if (light < 45) s->set_reg(s, 0x11, 0xff, 1);
        s->set_reg(s, 0x13, 0xff, 0);
        s->set_reg(s, 0x0c, 0x6,  0x8);
        s->set_reg(s, 0x45, 0x3f, 0x3f);
    } else {
        // Daylight mode – exposure ladder
        s->set_reg(s, 0x2d, 0xff, 0x0);
        s->set_reg(s, 0x2e, 0xff, 0x0);
        s->set_reg(s, 0x47, 0xff, 0x0);

        if      (light < 150) { s->set_reg(s,0x46,0xff,0xd0); s->set_reg(s,0x2a,0xff,0xff); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 160) { s->set_reg(s,0x46,0xff,0xc0); s->set_reg(s,0x2a,0xff,0xb0); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 170) { s->set_reg(s,0x46,0xff,0xb0); s->set_reg(s,0x2a,0xff,0x80); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 180) { s->set_reg(s,0x46,0xff,0xa8); s->set_reg(s,0x2a,0xff,0x80); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 190) { s->set_reg(s,0x46,0xff,0xa6); s->set_reg(s,0x2a,0xff,0x80); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 200) { s->set_reg(s,0x46,0xff,0xa4); s->set_reg(s,0x2a,0xff,0x80); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 210) { s->set_reg(s,0x46,0xff,0x98); s->set_reg(s,0x2a,0xff,0x60); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 220) { s->set_reg(s,0x46,0xff,0x80); s->set_reg(s,0x2a,0xff,0x20); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 230) { s->set_reg(s,0x46,0xff,0x70); s->set_reg(s,0x2a,0xff,0x20); s->set_reg(s,0x2b,0xff,0xff); }
        else if (light < 240) { s->set_reg(s,0x46,0xff,0x60); s->set_reg(s,0x2a,0xff,0x20); s->set_reg(s,0x2b,0xff,0x80); }
        else if (light < 253) { s->set_reg(s,0x46,0xff,0x10); s->set_reg(s,0x2a,0xff,0x0);  s->set_reg(s,0x2b,0xff,0x40); }
        else                  { s->set_reg(s,0x46,0xff,0x0);  s->set_reg(s,0x2a,0xff,0x0);  s->set_reg(s,0x2b,0xff,0x0);
                                s->set_reg(s,0x45,0xff,0x0);  s->set_reg(s,0x10,0xff,0x0); }

        s->set_reg(s, 0x0f, 0xff, 0x4b);
        s->set_reg(s, 0x03, 0xff, 0xcf);
        s->set_reg(s, 0x3d, 0xff, 0x34);
        s->set_reg(s, 0x11, 0xff, 0x0);
        s->set_reg(s, 0x43, 0xff, 0x11);
    }

    // Consume one warm-up frame after exposure setup
    camera_fb_t* fb = esp_camera_fb_get();

    if (light < DAY_THRESHOLD) s->set_reg(s, 0x43, 0xff, 0x40);

    s->set_reg(s, 0xff, 0xff, 0x00);
    s->set_reg(s, 0xd3, 0xff, 0x8);
    s->set_reg(s, 0x42, 0xff, 0x2f);
    s->set_reg(s, 0x44, 0xff, 3);
    s->set_reg(s, 0x92, 0xff, 0x1);
    s->set_reg(s, 0x93, 0xff, 0x0);

    if (fb) esp_camera_fb_return(fb);

    return true;
}

void cameraDeinit() {
    esp_camera_deinit();
}

// ============================================================
// Photo capture + Telegram upload
// ============================================================
bool cameraSendPhoto(const char* chatId) {
    if (!chatId || chatId[0] == '\0') return false;

     unsigned long t_start = millis();
     const char* token = getBotToken();
     if (!token || token[0] == '\0') return false;
     if (WiFi.status() != WL_CONNECTED) {
         Serial.println("[CAM] WiFi not connected before upload");
         return false;
     }

     flashOff();

     // Take 4 warm-up frames so AEC/AWB stabilises
     unsigned long t_capture_start = millis();
     camera_fb_t* fb = nullptr;
     for (int i = 0; i < 4; i++) {
         if (fb) esp_camera_fb_return(fb);
         fb = esp_camera_fb_get();
         if (!fb) {
             Serial.println("[CAM] fb_get failed at warmup " + String(i));
             if (i == 3) return false;
         }
         if (i < 3) {
             // split delay so watchdog stays fed
             for (int d = 0; d < 4; d++) { delay(100); yield(); }
         }
     }
     if (!fb) return false;
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
        String("Cam: ") + String(CAMERA_LABEL) + "\r\n"
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
    if (!writeAll(client, reinterpret_cast<const uint8_t*>(requestHeaders.c_str()), requestHeaders.length(), 5000) ||
        !writeAll(client, reinterpret_cast<const uint8_t*>(head.c_str()), head.length(), 5000)) {
        Serial.println("[CAM] failed to send HTTP headers/body prefix");
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
        if (!writeAll(client, buf + n, chunk, 5000)) {
            Serial.println("[CAM] upload write failed at offset " + String(n));
            writeFailed = true;
            break;
        }
        sentBytes += chunk;
        if (sentBytes >= nextProgressAt || sentBytes == len) {
            unsigned long elapsed = millis() - t_send_start;
            unsigned long bps = elapsed > 0 ? static_cast<unsigned long>((sentBytes * 1000ULL) / elapsed) : 0;
            Serial.println("[CAM] upload progress " + String(sentBytes) + "/" + String(len) + " bytes, " + String(bps) + " B/s");
            nextProgressAt += progressStep;
        }
    }
    if (!writeFailed && !writeAll(client, reinterpret_cast<const uint8_t*>(tail.c_str()), tail.length(), 5000)) {
        Serial.println("[CAM] failed to send multipart tail");
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
    unsigned long startTimer = millis();
    while ((startTimer + 10000) > millis()) {
        delay(100);
        while (client.available()) {
            char c = client.read();
            if (state) getBody += c;
            if (c == '\n') {
                if (getAll.length() == 0) state = true;
                getAll = "";
            } else if (c != '\r') {
                getAll += c;
            }
            startTimer = millis(); // reset timeout on every byte
        }
        // Only exit early when we found a definitive result
        if (getBody.indexOf("\"ok\":true")  >= 0) break;
        if (getBody.indexOf("\"ok\":false") >= 0) break;
        // Also exit if the server closed the connection
        if (!client.connected() && !client.available()) break;
    }
    bool ok = getBody.indexOf("\"ok\":true") >= 0;
        unsigned long t_done = millis();
        Serial.println("[CAM] response OK=" + String(ok ? "true" : "false") + ", total time " + String(t_done - t_start) + "ms");
    Serial.println("[CAM] response body: " + getBody.substring(0, 120));
    client.stop();

    if (fb) esp_camera_fb_return(fb);
    return ok;
}
