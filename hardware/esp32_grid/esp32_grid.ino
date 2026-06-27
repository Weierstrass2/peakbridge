#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <EmonLib.h>
#include <math.h>

// Wi-Fi / MQTT 설정
const char* WIFI_SSID = "여기에_와이파이_이름";
const char* WIFI_PASSWORD = "여기에_와이파이_비밀번호";
const char* MQTT_SERVER = "여기에_라즈베리파이_IP";
const int MQTT_PORT = 1883;
const char* BUILDING_ID = "building-A";
const char* DEVICE_ID = "esp32-grid-01";

// 하드웨어 설정
constexpr uint8_t CURRENT_SENSOR_PIN = 34;        // ADC1 권장 핀
constexpr float CURRENT_CALIBRATION = 9.09f;      // SCT-013(100A:50mA) + 220Ω 기준 시작값, 실측 보정 필요
constexpr int IRMS_SAMPLE_COUNT = 1480;           // 50/60Hz AC 측정용 샘플 수
constexpr unsigned long PUBLISH_INTERVAL_MS = 5000;
constexpr unsigned long RECONNECT_INTERVAL_MS = 5000;
constexpr unsigned long WIFI_CONNECT_TIMEOUT_MS = 10000;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
EnergyMonitor currentMonitor;

unsigned long lastPublishMs = 0;
unsigned long lastWiFiRetryMs = 0;
unsigned long lastMqttRetryMs = 0;
char gridCurrentTopic[96];

float roundToSingleDecimal(float value) {
  return roundf(value * 10.0f) / 10.0f;
}

void connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.disconnect();
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] Connection timeout");
  }
}

void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  char clientId[64];
  const uint64_t chipId = ESP.getEfuseMac();
  snprintf(clientId, sizeof(clientId), "%s-%04X", DEVICE_ID, (uint16_t)(chipId & 0xFFFF));

  Serial.printf("[MQTT] Connecting to %s:%d\n", MQTT_SERVER, MQTT_PORT);
  if (mqttClient.connect(clientId)) {
    Serial.println("[MQTT] Connected");
  } else {
    Serial.printf("[MQTT] Connect failed, state=%d\n", mqttClient.state());
  }
}

void maintainConnections() {
  const unsigned long now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastWiFiRetryMs >= RECONNECT_INTERVAL_MS) {
      lastWiFiRetryMs = now;
      connectWiFi();
    }
    return;
  }

  if (!mqttClient.connected() && now - lastMqttRetryMs >= RECONNECT_INTERVAL_MS) {
    lastMqttRetryMs = now;
    connectMqtt();
  }
}

float readGridCurrentRms() {
  float irms = currentMonitor.calcIrms(IRMS_SAMPLE_COUNT);

  if (!isfinite(irms) || irms < 0.0f) {
    return 0.0f;
  }

  return roundToSingleDecimal(irms);
}

void publishGridCurrent() {
  const float currentRms = readGridCurrentRms();

  StaticJsonDocument<192> payload;
  payload["value"] = currentRms;
  payload["unit"] = "A";
  payload["device_id"] = DEVICE_ID;
  payload["building_id"] = BUILDING_ID;

  char message[192];
  const size_t length = serializeJson(payload, message, sizeof(message));
  const bool published = mqttClient.publish(gridCurrentTopic, (const uint8_t*)message, length, false);

  if (published) {
    Serial.printf("[MQTT] Published %s -> %s\n", gridCurrentTopic, message);
  } else {
    Serial.println("[MQTT] Publish failed");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  analogReadResolution(12);
  analogSetPinAttenuation(CURRENT_SENSOR_PIN, ADC_11db);
  currentMonitor.current(CURRENT_SENSOR_PIN, CURRENT_CALIBRATION);

  snprintf(gridCurrentTopic, sizeof(gridCurrentTopic), "peakbridge/%s/grid/current", BUILDING_ID);

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setBufferSize(256);
  mqttClient.setKeepAlive(30);

  connectWiFi();
  connectMqtt();

  Serial.println("[System] esp32_grid ready");
}

void loop() {
  maintainConnections();

  if (mqttClient.connected()) {
    mqttClient.loop();
  }

  const unsigned long now = millis();
  if (WiFi.status() == WL_CONNECTED &&
      mqttClient.connected() &&
      now - lastPublishMs >= PUBLISH_INTERVAL_MS) {
    lastPublishMs = now;
    publishGridCurrent();
  }
}
