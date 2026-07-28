#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "여기에_와이파이_이름";
const char* WIFI_PASSWORD = "여기에_와이파이_비밀번호";
const char* MQTT_SERVER = "여기에_라즈베리파이_IP";
const int MQTT_PORT = 1883;
const char* BUILDING_ID = "building-A";
const char* DEVICE_ID = "esp32-relay-01";
const char* MQTT_SUB_TOPIC = "peakbridge/building-A/control/relay";
const char* MQTT_PUB_TOPIC = "peakbridge/building-A/control/relay/ack";

const int RED_LED_PIN = 25;
const int BLUE_LED_PIN = 26;
const int GREEN_LED_PIN = 27;
const int SSR_PIN = 14;

String currentMode = "standby";

WiFiClient espClient;
PubSubClient client(espClient);

void setLEDs(String mode) {
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(BLUE_LED_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, LOW);

  if (mode == "discharge") {
    digitalWrite(RED_LED_PIN, HIGH);
    digitalWrite(SSR_PIN, HIGH);
  } else if (mode == "charge") {
    digitalWrite(BLUE_LED_PIN, HIGH);
    digitalWrite(SSR_PIN, LOW);
  } else if (mode == "standby") {
    digitalWrite(GREEN_LED_PIN, HIGH);
    digitalWrite(SSR_PIN, LOW);
  }

  currentMode = mode;
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

void callback(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  deserializeJson(doc, payload, length);

  String action = doc["action"];
  setLEDs(action);

  StaticJsonDocument<256> ackDoc;
  ackDoc["status"] = "ok";
  ackDoc["action"] = action;
  ackDoc["device_id"] = DEVICE_ID;

  String ackPayload;
  serializeJson(ackDoc, ackPayload);

  client.publish(MQTT_PUB_TOPIC, ackPayload.c_str());
}

void reconnect() {
  while (!client.connected()) {
    // Wi-Fi가 죽어 있으면 MQTT 재시도는 무의미 — loop()의 Wi-Fi 복구로 반환
    if (WiFi.status() != WL_CONNECTED) return;
    if (client.connect(DEVICE_ID)) {
      Serial.println("MQTT 연결 완료");
      client.subscribe(MQTT_SUB_TOPIC);
    } else {
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BLUE_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(SSR_PIN, OUTPUT);

  setLEDs("standby");

  setupWiFi();
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
}
