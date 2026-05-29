#include "mqtt_client.h"

#include "config.h"
#include "battery.h"
#include "temperature.h"
#include "telegram.h"

#include <WiFi.h>
#include <PubSubClient.h>
#include <Preferences.h>

static WiFiClient s_mqttNetClient;
static PubSubClient s_mqttClient(s_mqttNetClient);

static char s_host[64] = {0};
static uint16_t s_port = MQTT_DEFAULT_PORT;
static char s_user[64] = {0};
static char s_pass[64] = {0};
static char s_topic[128] = {0};
static bool s_hasConfig = false;
static const uint8_t MQTT_SCHEMA_VERSION = 1;

static unsigned long s_lastReconnectAttemptMs = 0;
static unsigned long s_lastStatusPublishMs = 0;

static String makeTopic(const char* suffix) {
    if (suffix && suffix[0] == '\0' && s_topic[0] != '\0') {
        return String(s_topic);
    }

    String topic = "birdnest/";
    topic += CAMERA_LABEL;
    if (suffix && suffix[0] != '\0') {
        topic += "/";
        topic += suffix;
    }
    return topic;
}

static String getStateTopic() {
    return (s_topic[0] != '\0') ? makeTopic("") : makeTopic("status");
}

static String deriveSiblingTopic(const String& stateTopic, const char* suffix) {
    const String statusSuffix = "/status";
    if (stateTopic.endsWith(statusSuffix)) {
        return stateTopic.substring(0, stateTopic.length() - statusSuffix.length()) + "/" + suffix;
    }
    return stateTopic + "/" + suffix;
}

static String getEventTopic() {
    return deriveSiblingTopic(getStateTopic(), "event");
}

static String getAvailabilityTopic() {
    return deriveSiblingTopic(getStateTopic(), "availability");
}

static void publishEvent(const char* eventType, const char* detail) {
    if (!s_mqttClient.connected()) return;

    char payload[256];
    snprintf(payload, sizeof(payload),
             "{\"schema_version\":%u,\"device\":\"%s\",\"event\":\"%s\",\"detail\":\"%s\",\"uptime_s\":%lu}",
             static_cast<unsigned>(MQTT_SCHEMA_VERSION),
             CAMERA_LABEL,
             eventType ? eventType : "unknown",
             detail ? detail : "",
             static_cast<unsigned long>(millis() / 1000UL));

    const String topic = getEventTopic();
    s_mqttClient.publish(topic.c_str(), payload, false);
}

static String makeClientId() {
    uint64_t chipId = ESP.getEfuseMac();
    uint32_t shortId = static_cast<uint32_t>(chipId & 0xFFFFFFFFUL);
    return String(CAMERA_LABEL) + "-" + String(shortId, HEX);
}

static void loadConfig() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/true);
    prefs.getString("mqttHost", s_host, sizeof(s_host));
    s_port = prefs.getUShort("mqttPort", MQTT_DEFAULT_PORT);
    prefs.getString("mqttUser", s_user, sizeof(s_user));
    prefs.getString("mqttPass", s_pass, sizeof(s_pass));
    prefs.getString("mqttTopic", s_topic, sizeof(s_topic));
    prefs.end();

    if (s_port == 0) s_port = MQTT_DEFAULT_PORT;
    s_hasConfig = (s_host[0] != '\0');

    if (s_hasConfig) {
        s_mqttClient.setServer(s_host, s_port);
    }
}

static void saveConfig() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.putString("mqttHost", s_host);
    prefs.putUShort("mqttPort", s_port);
    prefs.putString("mqttUser", s_user);
    prefs.putString("mqttPass", s_pass);
    prefs.putString("mqttTopic", s_topic);
    prefs.end();
}

static bool ensureConnected() {
    if (!s_hasConfig) return false;
    if (WiFi.status() != WL_CONNECTED) return false;
    if (s_mqttClient.connected()) return true;

    const unsigned long now = millis();
    if ((now - s_lastReconnectAttemptMs) < MQTT_RECONNECT_INTERVAL_MS) {
        return false;
    }
    s_lastReconnectAttemptMs = now;

    const String clientId = makeClientId();
    const String availabilityTopic = getAvailabilityTopic();
    bool ok = false;
    if (s_user[0] != '\0') {
        ok = s_mqttClient.connect(
            clientId.c_str(),
            s_user,
            s_pass,
            availabilityTopic.c_str(),
            1,
            true,
            "offline");
    } else {
        ok = s_mqttClient.connect(
            clientId.c_str(),
            nullptr,
            nullptr,
            availabilityTopic.c_str(),
            1,
            true,
            "offline");
    }

    if (ok) {
        s_lastStatusPublishMs = 0;
        s_mqttClient.publish(availabilityTopic.c_str(), "online", true);
        publishEvent("connected", "broker_session_open");
        telegramSendDebug("[MQTT] connected to " + String(s_host) + ":" + String(s_port), 1);
    } else {
        telegramSendDebug("[MQTT] connect failed, state=" + String(s_mqttClient.state()), 2);
    }

    return ok;
}

void mqttInit() {
    s_mqttClient.setBufferSize(512);
    loadConfig();
}

void mqttLoop() {
    if (!s_hasConfig) return;

    const bool connected = ensureConnected();
    if (!connected) return;

    s_mqttClient.loop();

    const unsigned long now = millis();
    const unsigned long statusIntervalMs = static_cast<unsigned long>(MQTT_STATUS_INTERVAL_SEC) * 1000UL;
    if ((now - s_lastStatusPublishMs) >= statusIntervalMs) {
        mqttPublishNow("periodic");
    }
}

void mqttPublishNow(const char* reason) {
    if (!s_hasConfig) return;
    if (!ensureConnected()) return;

    const float temp = tempRead();
    const float batt = batteryReadVoltage();
    const int battPct = batteryReadPercent();
    const int32_t rssi = WiFi.RSSI();
    const String ipStr = WiFi.localIP().toString();

    char payload[320];
    snprintf(payload, sizeof(payload),
             "{\"schema_version\":%u,\"device\":\"%s\",\"reason\":\"%s\",\"ip\":\"%s\",\"rssi\":%ld,\"uptime_s\":%lu,\"temp_c\":%.2f,\"battery_v\":%.3f,\"battery_pct\":%d,\"maint\":%s}",
             static_cast<unsigned>(MQTT_SCHEMA_VERSION),
             CAMERA_LABEL,
             reason ? reason : "manual",
             ipStr.c_str(),
             static_cast<long>(rssi),
             static_cast<unsigned long>(millis() / 1000UL),
             temp,
             batt,
             battPct,
             telegramIsMaintMode() ? "true" : "false");

    const String topic = getStateTopic();
    s_mqttClient.publish(topic.c_str(), payload, true);
    s_lastStatusPublishMs = millis();
}

bool mqttHasConfig() {
    return s_hasConfig;
}

bool mqttSetConfig(const String& host, uint16_t port, const String& username, const String& password) {
    String h = host;
    h.trim();

    if (h.length() == 0) return false;
    if (h.length() >= sizeof(s_host)) return false;

    if (port == 0) port = MQTT_DEFAULT_PORT;

    String user = username;
    String pass = password;
    user.trim();
    pass.trim();

    if (user.length() >= sizeof(s_user) || pass.length() >= sizeof(s_pass)) return false;

    strncpy(s_host, h.c_str(), sizeof(s_host) - 1);
    s_host[sizeof(s_host) - 1] = '\0';

    s_port = port;

    strncpy(s_user, user.c_str(), sizeof(s_user) - 1);
    s_user[sizeof(s_user) - 1] = '\0';

    strncpy(s_pass, pass.c_str(), sizeof(s_pass) - 1);
    s_pass[sizeof(s_pass) - 1] = '\0';

    s_hasConfig = true;
    saveConfig();
    s_mqttClient.disconnect();
    s_mqttClient.setServer(s_host, s_port);
    publishEvent("config_updated", "mqtt_connection_settings_changed");

    return true;
}

void mqttClearConfig() {
    if (s_mqttClient.connected()) {
        const String availabilityTopic = getAvailabilityTopic();
        s_mqttClient.publish(availabilityTopic.c_str(), "offline", true);
        publishEvent("disabled", "mqtt_disabled_via_command");
    }

    s_host[0] = '\0';
    s_user[0] = '\0';
    s_pass[0] = '\0';
    s_topic[0] = '\0';
    s_port = MQTT_DEFAULT_PORT;
    s_hasConfig = false;

    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
    prefs.remove("mqttHost");
    prefs.remove("mqttPort");
    prefs.remove("mqttUser");
    prefs.remove("mqttPass");
    prefs.remove("mqttTopic");
    prefs.end();

    s_mqttClient.disconnect();
}

void mqttGetConfig(String& host, uint16_t& port, String& username, String& password) {
    host = String(s_host);
    port = s_port;
    username = String(s_user);
    password = String(s_pass);
}

bool mqttSetStatusTopic(const String& topic) {
    String t = topic;
    t.trim();
    if (t.length() == 0) return false;
    if (t.length() >= sizeof(s_topic)) return false;
    if (t.indexOf(' ') >= 0) return false;

    strncpy(s_topic, t.c_str(), sizeof(s_topic) - 1);
    s_topic[sizeof(s_topic) - 1] = '\0';
    saveConfig();
    return true;
}

void mqttResetStatusTopic() {
    s_topic[0] = '\0';
    saveConfig();
}

String mqttGetStatusTopic() {
    if (s_topic[0] != '\0') return String(s_topic);
    return makeTopic("status");
}

String mqttGetEventTopic() {
    return getEventTopic();
}

String mqttGetAvailabilityTopic() {
    return getAvailabilityTopic();
}

String mqttBuildSetupCommand(const String& host, uint16_t port, const String& username, const String& password) {
    const String userToken = username.length() > 0 ? username : "-";
    const String passToken = password.length() > 0 ? password : "-";
    return "/mqttset " + host + " " + String(port) + " " + userToken + " " + passToken;
}
