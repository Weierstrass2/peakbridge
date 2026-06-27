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

WiFiClient espClient;
PubSubClient client(espClient);
EnergyMonitor emon;

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

void setup() {
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

  StaticJsonDocument&lt;256&gt; doc;
  doc["value"] = Irms;
  doc["unit"] = "A";
  doc["device_id"] = DEVICE_ID;
  doc["building_id"] = BUILDING_ID;

  String payload;
  serializeJson(doc, payload);

  client.publish(MQTT_TOPIC, payload.c_str());

  delay(5000);
}
