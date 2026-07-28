#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <EmonLib.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "여기에_와이파이_이름";
const char* WIFI_PASSWORD = "여기에_와이파이_비밀번호";
const char* MQTT_SERVER = "여기에_라즈베리파이_IP";
const int MQTT_PORT = 1883;
const char* BUILDING_ID = "building-A";
const char* DEVICE_ID = "esp32-grid-01";

const char* MQTT_TOPIC = "peakbridge/building-A/grid/current";
const char* MQTT_CONFIG_TOPIC = "peakbridge/building-A/config";

const int CT_PIN = 34;
const float CT_CALIBRATION = 30;
const int LED_PIN = 2;

// 서버 폴링 실패 시 폴백 임계치 — 실측 스케일(CT ~0.08A)에 맞춘 값.
// 정상 경로에서는 부팅 시 서버값(/settings)으로 덮어써진다.
const float FALLBACK_THRESHOLD = 0.1;
float PEAK_THRESHOLD = FALLBACK_THRESHOLD;

WiFiClient espClient;
PubSubClient client(espClient);
EnergyMonitor emon;

unsigned long previousMillis = 0;
long ledInterval = 1000;
bool ledState = LOW;

// 측정·발행 주기 (블로킹 delay 대신 millis 타이머 — LED 점멸을 막지 않기 위함)
unsigned long lastPublishMillis = 0;
const unsigned long PUBLISH_INTERVAL_MS = 5000;

float getThresholdFromServer() {
  // Railway는 HTTPS 전용 — 인증서 검증은 생략(setInsecure), 암호화만 사용
  WiFiClientSecure secureClient;
  secureClient.setInsecure();
  HTTPClient http;
  http.begin(secureClient, "https://peakbridge-production.up.railway.app/api/v1/control/building-A/settings");
  int httpCode = http.GET();
  float threshold = FALLBACK_THRESHOLD;
  if (httpCode == 200) {
    String payload = http.getString();
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, payload) == DeserializationError::Ok) {
      // 응답 봉투: {"success": true, "data": {"threshold": ..., "auto_mode": ...}}
      threshold = doc["data"]["threshold"] | FALLBACK_THRESHOLD;
    }
  }
  http.end();
  return threshold;
}

void callback(char* topic, byte* payload, unsigned int length) {
  String topicStr = String(topic);
  if (topicStr == "peakbridge/building-A/config") {
    StaticJsonDocument<256> doc;
    deserializeJson(doc, payload, length);
    if (doc.containsKey("threshold")) {
      PEAK_THRESHOLD = doc["threshold"];
      Serial.println("임계치 변경: " + String(PEAK_THRESHOLD) + "A");
    }
  }
}

void setupWiFi() {
  int attempts = 0;
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED && attempts < 10) {
    Serial.println("Wi-Fi 연결 중...");
    delay(500);
    attempts++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi 연결 실패, ESP32 재시작...");
    ESP.restart();
  }
}

void reconnect() {
  while (!client.connected()) {
    // Wi-Fi가 죽어 있으면 MQTT 재시도는 무의미 — loop()의 Wi-Fi 복구로 반환
    if (WiFi.status() != WL_CONNECTED) return;
    if (client.connect(DEVICE_ID)) {
      Serial.println("MQTT 연결 완료");
      client.subscribe(MQTT_CONFIG_TOPIC);
    } else {
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);

  emon.current(CT_PIN, CT_CALIBRATION);
  setupWiFi();

  PEAK_THRESHOLD = getThresholdFromServer();
  Serial.println("서버 임계치: " + String(PEAK_THRESHOLD) + "A");

  client.setServer(MQTT_SERVER, MQTT_PORT);
  client.setCallback(callback);
}

void loop() {
  // Wi-Fi가 운영 중 끊기면 MQTT 재연결만으로는 복구 불가 — Wi-Fi부터 재수립
  if (WiFi.status() != WL_CONNECTED) {
    setupWiFi();
  }
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long currentMillis = millis();

  if (currentMillis - lastPublishMillis >= PUBLISH_INTERVAL_MS) {
    lastPublishMillis = currentMillis;

    double Irms = emon.calcIrms(1480);

    Serial.println("전류: " + String(Irms) + "A");

    if (Irms > PEAK_THRESHOLD) {
      Serial.println("⚠️ 피크 감지! " + String(Irms) + "A");
      ledInterval = 200;
    } else {
      ledInterval = 1000;
    }

    StaticJsonDocument<256> doc;
    doc["value"] = Irms;
    doc["unit"] = "A";
    doc["device_id"] = DEVICE_ID;
    doc["building_id"] = BUILDING_ID;
    doc["sensor_type"] = "grid_current";
    doc["timestamp"] = millis();
    doc["threshold"] = PEAK_THRESHOLD;

    String payload;
    serializeJson(doc, payload);

    client.publish(MQTT_TOPIC, payload.c_str());
  }

  if (currentMillis - previousMillis >= ledInterval) {
    previousMillis = currentMillis;
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState);
  }
}
