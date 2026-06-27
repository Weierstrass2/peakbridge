#include &lt;WiFi.h&gt;
#include &lt;PubSubClient.h&gt;
#include &lt;ArduinoJson.h&gt;
#include &lt;EmonLib.h&gt;

const char* WIFI_SSID = "여기에_와이파이_이름";
const char* WIFI_PASSWORD = "여기에_와이파이_비밀번호";
const char* MQTT_SERVER = "여기에_라즈베리파이_IP";
const int MQTT_PORT = 1883;
const char* BUILDING_ID = "building-A";
const char* DEVICE_ID = "esp32-grid-01";

const char* MQTT_TOPIC = "peakbridge/building-A/grid/current";

const int CT_PIN = 34;
const float CT_CALIBRATION = 30;
const int LED_PIN = 2;

WiFiClient espClient;
PubSubClient client(espClient);
EnergyMonitor emon;

unsigned long previousMillis = 0;
long ledInterval = 1000;
bool ledState = LOW;

void setupWiFi() {
  int attempts = 0;
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED &amp;&amp; attempts &lt; 10) {
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
    if (client.connect(DEVICE_ID)) {
      Serial.println("MQTT 연결 완료");
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
  client.setServer(MQTT_SERVER, MQTT_PORT);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  double Irms = emon.calcIrms(1480);
  
  Serial.println("전류: " + String(Irms) + "A");
  
  if (Irms &gt; 15.0) {
    Serial.println("⚠️ 피크 감지! " + String(Irms) + "A");
    ledInterval = 200;
  } else {
    ledInterval = 1000;
  }

  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis &gt;= ledInterval) {
    previousMillis = currentMillis;
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState);
  }

  StaticJsonDocument&lt;256&gt; doc;
  doc["value"] = Irms;
  doc["unit"] = "A";
  doc["device_id"] = DEVICE_ID;
  doc["building_id"] = BUILDING_ID;
  doc["sensor_type"] = "grid_current";
  doc["timestamp"] = millis();

  String payload;
  serializeJson(doc, payload);

  client.publish(MQTT_TOPIC, payload.c_str());

  delay(5000);
}
