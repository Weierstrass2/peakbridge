// xiao_peak_shaving.ino
// 목적: CT 센서(한전 인입 전류) + INA219(배터리->인버터 전류)을 함께 이용해
//       릴레이를 자동으로 절체하는 핵심 로직 + MQTT 전송 계층 (XIAO ESP32S3용).
//
// 판단 원칙:
//   NC -> NO 전환: CT 값이 임계값을 넘으면 (한전 쪽에서 피크를 감지)
//   NO -> NC 전환: INA219 값이 대기 전류 수준으로 떨어지면
//
// 통신 원칙 (FIRMWARE_MQTT_SPEC.md):
//   - 발행: peakbridge/demo/telemetry (QoS0, 약 1초 주기)
//   - 구독: peakbridge/demo/config (QoS1, retained — 재접속 시 즉시 최신 설정 수신)
//   - Wi-Fi/MQTT가 죽어도 절체·복귀 판단은 로컬에서 독립적으로 계속 돈다.
//     통신은 어디까지나 부가 기능이다.
//
// 배선 (XIAO ESP32S3 기준):
//   ZMCT103C  VCC -> 3V3  / GND -> GND  / OUT -> D0 (GPIO1)
//   릴레이모듈 VCC(DC+) -> 5V / GND(DC-) -> GND / IN1,IN2(묶어서) -> D1 (GPIO2)
//   INA219    VCC -> 3V3 / GND -> GND(배터리 -와 공유)
//             SDA -> D4 (GPIO5) / SCL -> D5 (GPIO6)
//             VIN+ -> 배터리쪽 (+) / VIN- -> 인버터쪽 (+)
//
// 릴레이 결선: NC=한전, NO=인버터, COM=부하3
//
// 실측 확정값 (2026-07-29 벤치 검증):
//   노이즈 플로어 CT 0.008A / 부하1·2 0.073A / 절체 트리거 ~0.108A
//   인버터 대기 ~690mA(650~733) / ESS 공급 ~1320mA(1260~1384)

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_INA219.h>

// ---------- 네트워크 (합숙 1일차에 확정 — 실제 비밀번호는 git에 절대 커밋 금지) ----------
const char* WIFI_SSID     = "여기에_와이파이_이름";
const char* WIFI_PASSWORD = "여기에_와이파이_비밀번호";
const char* MQTT_SERVER   = "여기에_브로커_IP";   // 라즈베리파이(또는 서버 노트북) IP
const int   MQTT_PORT     = 1883;
const char* DEVICE_ID     = "ess-demo-01";        // 스펙 고정값
const char* TOPIC_PUB     = "peakbridge/demo/telemetry";
const char* TOPIC_SUB     = "peakbridge/demo/config";
const char* TOPIC_CMD     = "peakbridge/demo/command";  // 1회성 명령(비retained) — SOC 리셋 등

// ---------- CT 센서 ----------
const int CT_PIN = 1;                 // XIAO ESP32S3: D0 (GPIO1)
const int SAMPLE_COUNT = 1000;
int samples[SAMPLE_COUNT];
const float CALIBRATION = 0.727;
const int CONSEC_REQUIRED = 2;        // 노이즈 방지: 연속 이 횟수 넘어야 절체/복귀

// ---------- 릴레이 ----------
const int RELAY_PIN = 2;              // XIAO ESP32S3: D1 (GPIO2)

// ---------- INA219 ----------
Adafruit_INA219 ina219;               // 기본 주소 0x40

// ---------- 배터리 SOC (쿨롱 카운팅) ----------
// LiFePO4 4S 12.8V 12Ah. INA219가 이미 배터리→인버터 전류를 재므로, 전류를
// 시간 적분해 사용 용량을 누적한다(하드웨어 무변경). LiFePO4는 전압 곡선이
// 평평해 전압 단독 SOC는 부정확 — 쿨롱 카운팅이 정석. 시작 SOC만 전압으로 추정.
const float BATTERY_CAPACITY_MAH = 12000.0;   // 12Ah
float gSocPercent = 100.0;                     // 현재 SOC(%) — setup에서 전압으로 초기화
float gBatteryV = 0.0;                         // INA219 버스 전압(읽히면)
float gRemainHours = 0.0;                      // 현재 방전율 기준 잔여 가동시간
unsigned long lastSocMillis = 0;

// LiFePO4 4S 무부하 전압(V) → SOC(%) 대략 룩업 (시작 초기화용, 평평 구간은 근사)
float socFromVoltage(float v) {
  if (v >= 13.4) return 100.0;
  if (v >= 13.3) return 90.0;
  if (v >= 13.2) return 75.0;
  if (v >= 13.1) return 55.0;
  if (v >= 13.0) return 35.0;
  if (v >= 12.9) return 20.0;
  if (v >= 12.8) return 13.0;
  if (v >= 12.0) return 8.0;
  if (v >= 10.0) return 3.0;
  return 0.0;
}

// ---------- 임계값 (서버 config로 갱신 가능한 전역 — 기본값은 실측 확정값) ----------
float gThresholdHigh = 0.090;         // 절체 임계(A). 실측: 부하1·2=0.073 / 트리거=0.108
float gInaLowMa      = 850.0;         // 복귀 임계(mA). 실측: 대기 690 / 공급 1320의 사이값
const float THRESHOLD_LOW_A = 0.055;  // INA 방식에선 미사용 — 스키마상 필수라 그대로 발행

// ---------- 열 차단 (Sense 보드 온도 구독 → 과열 시 강제 NC) ----------
// Sense 보드(xiao_sense_bme280)가 BME280 온도를 MQTT로 발행 → 이 보드가 구독해
// 스스로 판정한다. 두 보드 사이 전선 없음. 판단은 여기(로컬)에서 도므로 절체 원칙 유지.
const char* TOPIC_SENSE = "peakbridge/demo/sense_telemetry";
const float THERMAL_TRIP_C    = 50.0;   // 이 온도 이상 → 차단(강제 NC 잠금)
const float THERMAL_RELEASE_C = 43.0;   // 이 온도 이하로 식으면 → 해제 (히스테리시스)
const unsigned long SENSE_STALE_MS = 15000;   // 온도 수신이 이만큼 끊기면 stale로 간주
bool  gThermalLock   = false;           // 과열 잠금 상태
float gSenseTempC    = NAN;             // 최근 수신 최고온도(배터리/인버터 중 큰 값)
float gBatteryTempC  = NAN;
float gInverterTempC = NAN;
unsigned long gLastSenseMs = 0;         // 마지막 온도 수신 시각(0 = 아직 없음)

// ---------- 상태 ----------
bool isPeak = false;
int overCount = 0;
int underCount = 0;
// 강제 방전 모드: 서버 command로 켜지면 부하3 on/off와 무관하게 NO(ESS)를 유지한다.
// 복귀 판단(INA<임계)을 건너뛰므로, 부하 없을 때 인버터 무부하로 즉시 복귀하던
// 채터링이 원천 차단된다. 릴레이 직접 원격제어가 아니라 '판단 모드'만 바꾸는 것 —
// 통신이 끊겨도 로컬에서 마지막 모드로 안전하게 돌고, 재부팅하면 기본값(해제)로 시작.
bool gForceDischarge = false;
// 안전장치: 강제 방전 중 SOC가 이 값 밑으로 내려가면 배터리 보호를 위해 자동 해제.
const float FORCE_DISCHARGE_MIN_SOC = 15.0;
// 절체/복귀 직후 판단 유예: 인버터 전류가 정격에 도달하기까지 2~3초 램프가 있어
// (실측 확인) 유예 없이는 램프 구간을 "부하3 꺼짐"으로 오판해 즉시 복귀한다.
const unsigned long STABILIZE_MS = 10000;
unsigned long lastSwitchMillis = 0;

// ---------- 통신 상태 ----------
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
unsigned long lastWifiAttemptMillis = 0;
unsigned long lastMqttAttemptMillis = 0;
const unsigned long WIFI_RETRY_MS = 15000;   // Wi-Fi 재시도 간격
const unsigned long MQTT_RETRY_MS = 5000;    // MQTT 재시도 간격

// 1회성 명령 (비retained) — 현재는 soc_set(쿨롱 카운터 기준값 보정)만 지원.
// 릴레이 제어 명령은 의도적으로 없다: 절체 판단은 항상 로컬 히스테리시스가 한다.
void onCommand(JsonDocument& doc) {
  const char* action = doc["action"] | "";
  if (strcmp(action, "soc_set") == 0) {
    float p = doc["percent"] | -1.0;
    if (p < 0.0 || p > 100.0) {
      Serial.println("command 거부: percent 범위 위반");
      return;
    }
    gSocPercent = p;
    lastSocMillis = millis();   // 적분 구간도 리셋 — 폴링 공백만큼의 오차 방지
    Serial.print("command 적용: SOC ");
    Serial.print(p, 0);
    Serial.println("%로 리셋 (쿨롱 카운터 기준값 보정)");
  } else if (strcmp(action, "force_discharge") == 0) {
    // 강제 방전 ON — 부하 무관 NO 유지. SOC 하한 미만이면 배터리 보호를 위해 거부.
    if (gSocPercent <= FORCE_DISCHARGE_MIN_SOC) {
      Serial.println("command 거부: SOC 하한 미만 — 강제 방전 불가");
      return;
    }
    gForceDischarge = true;
    if (!isPeak) goNO();   // 즉시 절체 (부하3 여부와 무관)
    Serial.println("command 적용: 강제 방전 ON (부하 무관 NO 유지)");
  } else if (strcmp(action, "auto") == 0 || strcmp(action, "release") == 0) {
    // 강제 방전 해제 — 자동 판단 복귀. 부하3이 없으면 다음 루프에서 자연스럽게 NC로.
    gForceDischarge = false;
    Serial.println("command 적용: 강제 방전 해제 — 자동 판단 복귀");
  } else {
    Serial.print("command 무시: 알 수 없는 action ");
    Serial.println(action);
  }
}

// Sense 보드 온도 텔레메트리 수신 — 판정은 loop에서 로컬로 한다(여기선 저장만).
// 두 온도 중 더 뜨거운 값을 판정 기준으로 삼는다. 없는 값(NaN)은 무시.
void onSense(JsonDocument& doc) {
  float bt = doc["battery_temp_c"]  | (float)NAN;
  float it = doc["inverter_temp_c"] | (float)NAN;
  gBatteryTempC  = bt;
  gInverterTempC = it;
  float m = NAN;
  if (!isnan(bt)) m = bt;
  if (!isnan(it)) m = isnan(m) ? it : max(m, it);
  gSenseTempC  = m;
  gLastSenseMs = millis();
}

// 서버가 내려주는 config (retained) — 펌웨어 자체 검증 후에만 적용, 불합격이면 기존 값 유지
void onConfig(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, len)) {
    Serial.println("config 거부: JSON 파싱 실패");
    return;
  }
  if (strcmp(topic, TOPIC_CMD) == 0) {
    onCommand(doc);
    return;
  }
  if (strcmp(topic, TOPIC_SENSE) == 0) {
    onSense(doc);
    return;
  }
  float high   = doc["threshold_high_a"] | gThresholdHigh;
  float low    = doc["threshold_low_a"]  | THRESHOLD_LOW_A;
  int   hold   = doc["min_hold_s"]       | 30;
  float inaLow = doc["ina_low_ma"]       | gInaLowMa;

  // 검증 규칙 (서버·대시보드와 동일): high > low > 0, 5<=hold<=300, 50<=inaLow<=8200
  if (!(high > low && low > 0) || hold < 5 || hold > 300 || inaLow < 50 || inaLow > 8200) {
    Serial.println("config 거부: 범위 위반");
    return;
  }
  gThresholdHigh = high;
  gInaLowMa = inaLow;
  Serial.print("config 적용: I_HIGH=");
  Serial.print(gThresholdHigh, 3);
  Serial.print("A, INA_LOW=");
  Serial.print(gInaLowMa, 0);
  Serial.println("mA");
}

// Wi-Fi/MQTT 유지 — 전부 논블로킹 성격(짧은 타임아웃 + 재시도 간격)으로,
// 연결이 안 돼도 판단 루프는 계속 돈다. 여기서 절대 무한 대기하지 말 것.
void maintainNetwork() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWifiAttemptMillis >= WIFI_RETRY_MS) {
      lastWifiAttemptMillis = millis();
      Serial.println("[통신] Wi-Fi 재연결 시도...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
    return;   // Wi-Fi 없으면 MQTT 시도 무의미
  }
  if (!mqtt.connected()) {
    if (millis() - lastMqttAttemptMillis >= MQTT_RETRY_MS) {
      lastMqttAttemptMillis = millis();
      if (mqtt.connect(DEVICE_ID)) {
        mqtt.subscribe(TOPIC_SUB, 1);     // QoS1 — retained config 즉시 수신
        mqtt.subscribe(TOPIC_CMD, 1);     // QoS1 — 1회성 명령(SOC 리셋 등)
        mqtt.subscribe(TOPIC_SENSE, 0);   // QoS0 — Sense 보드 온도(열 차단 판정 입력)
        Serial.println("[통신] MQTT 연결 완료, config·command·sense 구독");
      } else {
        Serial.println("[통신] MQTT 연결 실패 (판단은 계속 동작)");
      }
    }
    return;
  }
  mqtt.loop();
}

// 텔레메트리 발행 (FIRMWARE_MQTT_SPEC.md 페이로드 그대로)
void publishTelemetry(float ct, float inaMa) {
  if (!mqtt.connected()) return;   // 전송 실패가 판단을 막지 않는다
  StaticJsonDocument<512> doc;
  doc["device_id"]        = DEVICE_ID;
  doc["timestamp"]        = 0;               // NTP 미동기 — 스펙대로 0 그대로
  doc["grid_current_a"]   = ct;
  doc["relay_state"]      = isPeak ? "NO" : "NC";
  doc["threshold_high_a"] = gThresholdHigh;
  doc["threshold_low_a"]  = THRESHOLD_LOW_A;
  doc["hold_remaining_s"] = 0;               // 최소 유지시간 미사용 — 항상 0
  doc["ina_current_ma"]   = inaMa;
  doc["battery_soc"]      = gSocPercent;     // 쿨롱 카운팅 SOC(%)
  doc["battery_voltage_v"] = gBatteryV;      // INA219 버스 전압(읽히면)
  doc["remain_hours"]     = gRemainHours;    // 현재 방전율 기준 잔여 가동시간
  doc["force_discharge"]  = gForceDischarge; // 강제 방전 모드 여부(로컬 대시보드 표시용)
  doc["thermal_lock"]     = gThermalLock;    // 과열 잠금 여부(로컬 대시보드 표시용)
  if (!isnan(gBatteryTempC))  doc["battery_temp_c"]  = gBatteryTempC;
  if (!isnan(gInverterTempC)) doc["inverter_temp_c"] = gInverterTempC;

  char buf[512];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(TOPIC_PUB, (uint8_t*)buf, n, false);
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);   // PC가 시리얼을 안 읽을 때 print가 블로킹되어
                              // MQTT 킵얼라이브를 놓치는 것 방지 (S3 CDC 함정)
  delay(3000);   // XIAO는 네이티브 USB CDC — 열거 전 출력은 유실되므로 대기

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);   // 시작은 항상 NC(한전)

  analogReadResolution(12);
  analogSetPinAttenuation(CT_PIN, ADC_11db);

  Wire.begin(5, 6);   // XIAO ESP32S3 기본 I2C 핀: SDA=GPIO5(D4), SCL=GPIO6(D5)
  if (!ina219.begin()) {
    Serial.println("INA219을 찾지 못했다. 배선(SDA=D4, SCL=D5, VCC=3V3, 주소)을 확인하세요.");
    while (1) delay(1000);
  }
  ina219.setCalibration_32V_2A();     // 기본 보정값: 최대 32V / 2A 범위

  // 시작 SOC 초기화: 무부하 전압으로 추정(읽히면). 전압 0/비정상이면 만충 가정.
  gBatteryV = ina219.getBusVoltage_V();
  if (gBatteryV >= 10.0 && gBatteryV <= 15.0) {
    gSocPercent = socFromVoltage(gBatteryV);
    Serial.print("초기 SOC(전압 "); Serial.print(gBatteryV, 2);
    Serial.print("V 추정): "); Serial.print(gSocPercent, 0); Serial.println("%");
  } else {
    gSocPercent = 100.0;
    Serial.println("초기 SOC: 전압 미확보 → 만충(100%) 가정, 이후 쿨롱 카운팅");
  }
  lastSocMillis = millis();

  // Wi-Fi: 부팅 시 최대 8초만 대기 — 실패해도 판단 루프는 그대로 시작 (폐쇄망 단독 데모 보장)
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  // [저전력 슬립 전략] Modem Sleep 채택 (ESP32 기본값을 명시적으로 선언).
  //  - Deep/Light Sleep 배제: 이 노드는 CT를 상시 샘플링해 피크를 감지하고 릴레이
  //    상태를 유지해야 한다. CPU를 재우면 피크를 놓치고, 재부팅(Deep) 시 릴레이가
  //    NC로 리셋돼 부하3이 순단된다. XIAO는 USB CDC라 Deep Sleep 시 포트도 사라진다.
  //  - Modem Sleep: Wi-Fi 연결은 유지하되 비컨 사이 RF 모뎀만 꺼 절전한다. 통신 지연이
  //    생겨도 '판단은 로컬 우선' 원칙이라 절체·복귀 안전에 영향 없다.
  //  - 역할별 차등: 열 차단 신호원인 Sense 보드는 지연 방지로 setSleep(false)를 쓴다.
  WiFi.setSleep(true);
  for (int i = 0; i < 16 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[통신] Wi-Fi 연결: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[통신] Wi-Fi 미연결 — 판단은 단독 동작, 백그라운드 재시도");
  }
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(onConfig);
  mqtt.setSocketTimeout(3);   // 연결 실패 시 블로킹을 3초로 제한 (판단 루프 보호)
  mqtt.setKeepAlive(15);
  // PubSubClient 기본 버퍼 256B — SOC 필드 추가로 telemetry가 이를 넘어
  // publish가 조용히 실패했다. 여유 있게 512B로 확대.
  mqtt.setBufferSize(512);

  delay(500);
  lastSwitchMillis = millis() - STABILIZE_MS;   // 부팅 직후에는 유예 없이 바로 판단
  Serial.println("피크 셰이빙 시작 (CT: 절체 판단 / INA219: 복귀 판단 / MQTT 부가)");
}

// INA219는 순간값 1회 읽기라 인버터 리플(±300mA, 실측)이 그대로 보인다.
// 25회 * 8ms = 약 200ms 평균으로 리플을 눌러 복귀 판단을 안정화한다.
float readInaAveraged_mA() {
  float sum = 0;
  const int N = 25;
  for (int i = 0; i < N; i++) {
    sum += ina219.getCurrent_mA();
    delay(8);
  }
  return sum / N;
}

float readCTCurrent() {
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    samples[i] = analogRead(CT_PIN);
    delayMicroseconds(20);
  }
  long sum = 0;
  for (int i = 0; i < SAMPLE_COUNT; i++) sum += samples[i];
  float avg = (float)sum / SAMPLE_COUNT;

  double sumSq = 0;
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    double diff = samples[i] - avg;
    sumSq += diff * diff;
  }
  float rmsADC = sqrt(sumSq / SAMPLE_COUNT);
  float rmsVoltage = rmsADC * (3.3 / 4095.0);
  return rmsVoltage * CALIBRATION;
}

void goNO() {
  digitalWrite(RELAY_PIN, HIGH);
  isPeak = true;
  overCount = 0;
  underCount = 0;
  lastSwitchMillis = millis();
  Serial.println("   -> 절체! NC에서 NO(ESS)로");
}

void goNC() {
  digitalWrite(RELAY_PIN, LOW);
  isPeak = false;
  overCount = 0;
  underCount = 0;
  lastSwitchMillis = millis();
  Serial.println("   -> 복귀! NO에서 NC(한전)로");
}

void loop() {
  float ctCurrent = readCTCurrent();
  float inaCurrent_mA = readInaAveraged_mA();

  // ── 쿨롱 카운팅 SOC 갱신 ──────────────────────────
  // 방전(공급, +) → SOC 감소 / 충전(-) → SOC 증가. 인버터 대기전류도 배터리
  // 소비이므로 그대로 반영된다. dt는 실제 경과시간(ms)으로 적분.
  unsigned long nowMs = millis();
  float dtHours = (nowMs - lastSocMillis) / 3600000.0;
  lastSocMillis = nowMs;
  gSocPercent -= (inaCurrent_mA * dtHours) / BATTERY_CAPACITY_MAH * 100.0;
  if (gSocPercent > 100.0) gSocPercent = 100.0;
  if (gSocPercent < 0.0) gSocPercent = 0.0;
  gBatteryV = ina219.getBusVoltage_V();
  // 잔여 가동시간: 방전 중일 때만 의미 (남은 용량 / 현재 전류)
  float remainMah = gSocPercent / 100.0 * BATTERY_CAPACITY_MAH;
  gRemainHours = (inaCurrent_mA > 50.0) ? (remainMah / inaCurrent_mA) : 0.0;

  Serial.print("CT(A): ");
  Serial.print(ctCurrent, 4);
  Serial.print("   INA219(mA): ");
  Serial.print(inaCurrent_mA, 1);
  Serial.print("   SOC: ");
  Serial.print(gSocPercent, 1);
  Serial.print("%");
  if (gRemainHours > 0) {
    Serial.print(" (잔여 ");
    Serial.print(gRemainHours, 1);
    Serial.print("h)");
  }
  Serial.print("   상태: ");
  Serial.print(isPeak ? "NO(ESS)" : "NC(한전)");
  Serial.print(mqtt.connected() ? "   [MQTT O]" : "   [MQTT X]");

  // ── 열 차단 판정 (최우선 — 강제 방전·자동 판단·안정화 유예보다 먼저) ──────────
  // Sense 보드 온도로 히스테리시스 판정. 과열이면 인버터(ESS)를 멈추고 한전(NC) 고정.
  bool senseFresh = (gLastSenseMs != 0) && (millis() - gLastSenseMs < SENSE_STALE_MS);
  if (!isnan(gSenseTempC)) {
    Serial.print("   T:");
    Serial.print(gSenseTempC, 1);
    Serial.print("C");
    if (!senseFresh) Serial.print("(stale)");
  }
  // 신선한 온도가 있을 때만 상태 전이. stale이면 아래 분기를 건너뛰어 현 상태 유지.
  if (senseFresh && !isnan(gSenseTempC)) {
    if (!gThermalLock && gSenseTempC >= THERMAL_TRIP_C) {
      gThermalLock = true;
      gForceDischarge = false;   // 과열 시 강제 방전도 자동 해제(SOC 하한과 동일 안전 원칙)
      Serial.print("   [열 차단 발동! ");
      Serial.print(gSenseTempC, 1);
      Serial.print("C >= 트립 ");
      Serial.print(THERMAL_TRIP_C, 0);
      Serial.println("C]");
    } else if (gThermalLock && gSenseTempC <= THERMAL_RELEASE_C) {
      gThermalLock = false;
      Serial.print("   [열 차단 해제 ");
      Serial.print(gSenseTempC, 1);
      Serial.print("C <= 해제 ");
      Serial.print(THERMAL_RELEASE_C, 0);
      Serial.println("C]");
    }
  }
  // fail-safe: 잠금 중 온도 수신이 끊겨도(stale) 절대 자동 해제하지 않는다.
  // 온도를 다시 받아 해제온도 밑으로 확인될 때만 풀린다(안전측 고장).
  if (gThermalLock) {
    if (isPeak) goNC();   // 인버터(ESS) 정지, 한전으로 복귀
    else Serial.println("   [열 차단 유지 — 과열, 한전 고정]");
    publishTelemetry(ctCurrent, inaCurrent_mA);
    maintainNetwork();
    delay(1000);
    return;
  }

  // 절체/복귀 직후 안정화 유예 — 인버터 램프·과도 전류를 오판하지 않도록 판단 보류
  if (millis() - lastSwitchMillis < STABILIZE_MS) {
    Serial.print("   [안정화 대기 ");
    Serial.print((STABILIZE_MS - (millis() - lastSwitchMillis)) / 1000 + 1);
    Serial.println("s]");
    publishTelemetry(ctCurrent, inaCurrent_mA);   // 유예 중에도 텔레메트리는 발행
    maintainNetwork();
    delay(1000);
    return;
  }

  // 강제 방전 모드: 자동 판단을 건너뛰고 NO(ESS)를 유지한다.
  if (gForceDischarge) {
    if (gSocPercent <= FORCE_DISCHARGE_MIN_SOC) {
      // 배터리 보호 — SOC 하한 도달 시 강제 해제하고 한전으로 복귀
      Serial.println("   [강제 방전 자동 해제: SOC 하한 도달 → 복귀]");
      gForceDischarge = false;
      goNC();
    } else {
      if (!isPeak) goNO();   // 혹시 NC 상태면 다시 NO로
      Serial.println("   [강제 방전 유지 — 부하 무관]");
    }
    publishTelemetry(ctCurrent, inaCurrent_mA);
    maintainNetwork();
    delay(1000);
    return;
  }

  if (!isPeak) {
    if (ctCurrent > gThresholdHigh) {
      overCount++;
      Serial.print("   [절체 대기 ");
      Serial.print(overCount);
      Serial.print("/");
      Serial.print(CONSEC_REQUIRED);
      Serial.println("]");
      if (overCount >= CONSEC_REQUIRED) goNO();
    } else {
      overCount = 0;
      Serial.println("   [정상]");
    }
  } else {
    if (inaCurrent_mA < gInaLowMa) {
      underCount++;
      Serial.print("   [복귀 대기 ");
      Serial.print(underCount);
      Serial.print("/");
      Serial.print(CONSEC_REQUIRED);
      Serial.println("]");
      if (underCount >= CONSEC_REQUIRED) goNC();
    } else {
      underCount = 0;
      Serial.println("   [공급 중]");
    }
  }

  // 판단이 끝난 뒤에 통신 — 절체 직후의 상태 변화가 바로 다음 발행에 실린다
  publishTelemetry(ctCurrent, inaCurrent_mA);
  maintainNetwork();

  delay(1000);
}
