#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_INA219.h>

const char* WIFI_SSID = "여기에_와이파이_이름";
const char* WIFI_PASSWORD = "여기에_와이파이_비밀번호";
const char* MQTT_SERVER = "여기에_라즈베리파이_IP";
const int MQTT_PORT = 1883;
const char* BUILDING_ID = "building-A";
const char* DEVICE_ID = "esp32-ess-01";
const char* MQTT_TOPIC = "peakbridge/building-A/ess/soc";

const float VOLTAGE_MAX = 3.65;
const float VOLTAGE_MIN = 3.20;

WiFiClient espClient;
PubSubClient client(espClient);
Adafruit_INA219 ina219;

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
    } else {
      delay(5000);
    }
  }
}

float calculateSOC(float voltage) {
  if (voltage >= VOLTAGE_MAX) {
    return 100.0;
  } else if (voltage <= VOLTAGE_MIN) {
    return 0.0;
  } else {
    return ((voltage - VOLTAGE_MIN) / (VOLTAGE_MAX - VOLTAGE_MIN)) * 100.0;
  }
}

void setup() {
  Serial.begin(115200);
  // 센서 미연결 상태로 0V→SOC 0%를 계속 발행하는 것을 막는다
  if (!ina219.begin()) {
    Serial.println("INA219를 찾지 못했다. 배선(SDA/SCL, 주소)을 확인하세요.");
    while (1) delay(1000);
  }
  setupWiFi();
  client.setServer(MQTT_SERVER, MQTT_PORT);
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

  float voltage = ina219.getBusVoltage_V();
  float current = ina219.getCurrent_mA() / 1000.0;
  float soc = calculateSOC(voltage);

  StaticJsonDocument<256> doc;
  doc["value"] = soc;
  doc["unit"] = "%";
  doc["voltage"] = voltage;
  doc["current"] = current;
  doc["device_id"] = DEVICE_ID;
  doc["building_id"] = BUILDING_ID;

  String payload;
  serializeJson(doc, payload);

  client.publish(MQTT_TOPIC, payload.c_str());

  delay(5000);
}
