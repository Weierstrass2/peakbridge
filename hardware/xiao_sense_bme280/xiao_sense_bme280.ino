// xiao_sense_bme280.ino
// 목적: XIAO ESP32S3 Sense에서 BME280 2개(배터리 옆 / 인버터 옆)의 온·습도를 읽어
//       MQTT로 발행한다. 메인 보드(xiao_peak_shaving)가 이 온도를 구독해서
//       과열 시 스스로 열 차단(강제 NC)을 판정한다 — 두 보드 사이 전선은 없다.
//
// 판단 원칙(메인 보드와 동일): 통신은 어디까지나 부가 기능이다. 네트워크가 죽어도
//   센서 읽기·발행 '시도'는 논블로킹으로 계속 돈다. 여기서 절대 무한 대기하지 않는다.
//   (기존 sense 스케치의 while 블로킹 재연결은 네트워크가 끊기면 온도 발행이 통째로
//    멈춰 열 차단 신호원이 죽으므로, 메인 보드의 maintainNetwork 패턴으로 교체했다.)
//
// 배선:
//   배터리 옆 BME280: VCC->3V3, GND->GND, SDA->D4(GPIO5), SCL->D5(GPIO6)  (Wire)
//   인버터 옆 BME280: VCC->3V3, GND->GND, SDA->D0(GPIO1), SCL->D1(GPIO2)  (I2C_2)
//   두 모듈 모두 주소 0x76 (SDO->GND). 서로 다른 I2C 버스라 주소 충돌 없음.
//
// 필요 라이브러리: Adafruit BME280 (+Adafruit Unified Sensor), PubSubClient, ArduinoJson

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_BME280.h>

// ---------- 네트워크 (실제 SSID/PW/브로커IP는 현장에서 기입 — git 커밋 금지) ----------
const char* WIFI_SSID     = "Galaxy A90 5G0201";
const char* WIFI_PASSWORD = "2580kkjo";
const char* MQTT_SERVER   = "10.36.50.248";   // 메인 보드와 '같은' 브로커여야 한다(라즈베리파이/노트북 IP)
const int   MQTT_PORT     = 1883;
const char* DEVICE_ID     = "ess-sense-01";
const char* TOPIC_PUB     = "peakbridge/demo/sense_telemetry";   // 메인 보드가 구독하는 토픽

// ---------- 발행 주기 ----------
const unsigned long PUBLISH_INTERVAL_MS = 2000;   // 2초마다 발행
unsigned long lastPublish = 0;

// ---------- BME280 (둘 다 0x76, 서로 다른 I2C 버스) ----------
Adafruit_BME280 bmeBattery;
Adafruit_BME280 bmeInverter;
TwoWire I2C_2 = TwoWire(1);
bool batteryOK  = false;
bool inverterOK = false;
unsigned long lastSensorRetryMs = 0;
const unsigned long SENSOR_RETRY_MS = 5000;   // 실패한 센서 재초기화 주기(접촉 불량 회복용)

bool beginBattery()  { return bmeBattery.begin(0x76, &Wire); }
bool beginInverter() { return bmeInverter.begin(0x76, &I2C_2); }

// ---------- 통신 상태 (전부 논블로킹) ----------
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
unsigned long lastWifiAttemptMs = 0;
unsigned long lastMqttAttemptMs = 0;
const unsigned long WIFI_RETRY_MS = 15000;   // Wi-Fi 재시도 간격
const unsigned long MQTT_RETRY_MS = 5000;    // MQTT 재시도 간격

// 연결이 안 돼도 절대 무한 대기하지 않는다 (메인 보드 maintainNetwork와 동일 패턴)
void maintainNetwork() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWifiAttemptMs >= WIFI_RETRY_MS) {
      lastWifiAttemptMs = millis();
      Serial.println("[통신] Wi-Fi 재연결 시도...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
    return;   // Wi-Fi 없으면 MQTT 시도 무의미
  }
  if (!mqtt.connected()) {
    if (millis() - lastMqttAttemptMs >= MQTT_RETRY_MS) {
      lastMqttAttemptMs = millis();
      String clientId = String(DEVICE_ID) + "-" + String(random(0xffff), HEX);
      if (mqtt.connect(clientId.c_str())) {
        Serial.println("[통신] MQTT 연결 완료");
      } else {
        Serial.print("[통신] MQTT 연결 실패 rc=");
        Serial.println(mqtt.state());
      }
    }
    return;
  }
  mqtt.loop();
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);   // S3 네이티브 CDC: PC가 시리얼을 안 읽어도 print가
                              // 막히지 않게 (막히면 MQTT 킵얼라이브를 놓친다)
  delay(3000);                // CDC 열거 대기 — 없으면 초기 출력 유실
  Serial.println("Sense 보드 시작 (BME280 x2 -> MQTT)");

  Wire.begin(5, 6);     // 배터리 센서: SDA=GPIO5(D4), SCL=GPIO6(D5)
  I2C_2.begin(1, 2);    // 인버터 센서: SDA=GPIO1(D0), SCL=GPIO2(D1)
  batteryOK  = beginBattery();
  inverterOK = beginInverter();
  Serial.println(batteryOK  ? "배터리 옆 BME280 연결 성공" : "배터리 옆 BME280 실패(주기 재시도)");
  Serial.println(inverterOK ? "인버터 옆 BME280 연결 성공" : "인버터 옆 BME280 실패(주기 재시도)");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // 모뎀 슬립 OFF — 킵얼라이브 누락/지연 방지(안전 신호원이므로)
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (int i = 0; i < 16 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[통신] Wi-Fi 연결, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[통신] Wi-Fi 미연결 — 백그라운드 재시도(발행 루프는 계속 돈다)");
  }

  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setSocketTimeout(3);   // 연결 실패 시 블로킹 3초로 제한
  mqtt.setKeepAlive(15);
  mqtt.setBufferSize(384);
}

void loop() {
  // 실패한 센서 주기적 재초기화 (부팅 후 늦게 인식됐거나 접촉 회복된 경우)
  if ((!batteryOK || !inverterOK) && millis() - lastSensorRetryMs >= SENSOR_RETRY_MS) {
    lastSensorRetryMs = millis();
    if (!batteryOK)  batteryOK  = beginBattery();
    if (!inverterOK) inverterOK = beginInverter();
  }

  unsigned long now = millis();
  if (now - lastPublish >= PUBLISH_INTERVAL_MS) {
    lastPublish = now;

    StaticJsonDocument<256> doc;
    doc["device_id"] = DEVICE_ID;

    // 읽기 실패(NaN)면 해당 필드를 아예 빼서 발행 → 메인 보드가 '데이터 없음'으로 인식
    float bt = NAN, it = NAN;
    if (batteryOK) {
      bt = bmeBattery.readTemperature();
      if (!isnan(bt)) {
        doc["battery_temp_c"]      = bt;
        doc["battery_humidity_pct"] = bmeBattery.readHumidity();
      } else {
        batteryOK = false;   // 읽기 실패 → 재초기화 대상으로
      }
    }
    if (inverterOK) {
      it = bmeInverter.readTemperature();
      if (!isnan(it)) {
        doc["inverter_temp_c"]      = it;
        doc["inverter_humidity_pct"] = bmeInverter.readHumidity();
      } else {
        inverterOK = false;
      }
    }

    if (mqtt.connected()) {
      char buf[256];
      size_t n = serializeJson(doc, buf);
      mqtt.publish(TOPIC_PUB, (uint8_t*)buf, n, false);
    }

    Serial.print("배터리 ");
    Serial.print(isnan(bt) ? String("--") : String(bt, 1) + "C");
    Serial.print(" / 인버터 ");
    Serial.print(isnan(it) ? String("--") : String(it, 1) + "C");
    Serial.println(mqtt.connected() ? "   [MQTT O]" : "   [MQTT X]");
  }

  maintainNetwork();
  delay(50);
}
