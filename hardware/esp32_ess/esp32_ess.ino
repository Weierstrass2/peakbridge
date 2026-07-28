#include &lt;WiFi.h&gt;
#include &lt;PubSubClient.h&gt;
#include &lt;ArduinoJson.h&gt;
#include &lt;Adafruit_INA219.h&gt;

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
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect(DEVICE_ID)) {
    } else {
      delay(5000);
    }
  }
}

float calculateSOC(float voltage) {
  if (voltage &gt;= VOLTAGE_MAX) {
    return 100.0;
  } else if (voltage &lt;= VOLTAGE_MIN) {
    return 0.0;
  } else {
    return ((voltage - VOLTAGE_MIN) / (VOLTAGE_MAX - VOLTAGE_MIN)) * 100.0;
  }
}

void setup() {
  ina219.begin();
  setupWiFi();
  client.setServer(MQTT_SERVER, MQTT_PORT);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  float voltage = ina219.getBusVoltage_V();
  float current = ina219.getCurrent_mA() / 1000.0;
  float soc = calculateSOC(voltage);

  StaticJsonDocument&lt;256&gt; doc;
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
