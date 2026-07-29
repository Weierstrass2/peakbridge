// xiao_peak_shaving.ino
// 목적: CT 센서(한전 인입 전류) + INA219(배터리->인버터 전류)을 함께 이용해
//       릴레이를 자동으로 절체하는 핵심 로직.
//       배터리 전압 측정, 충전 LED는 제외한 단순화 버전 (XIAO ESP32S3용).
//
// 판단 원칙:
//   NC -> NO 전환: CT 값이 임계값을 넘으면 (한전 쪽에서 피크를 감지)
//   NO -> NC 전환: INA219 값이 대기 전류 수준으로 떨어지면
//
// 배선 (XIAO ESP32S3 기준):
//   ZMCT103C  VCC -> 3V3  / GND -> GND  / OUT -> D0 (GPIO1)
//   릴레이모듈 VCC(DC+) -> 5V / GND(DC-) -> GND / IN1,IN2(묶어서) -> D1 (GPIO2)
//   INA219    VCC -> 3V3 / GND -> GND(배터리 -와 공유)
//             SDA -> D4 (GPIO5) / SCL -> D5 (GPIO6)
//             VIN+ -> 배터리쪽 (+) / VIN- -> 인버터쪽 (+)
//
// 필요한 라이브러리: 아두이노 라이브러리 매니저에서 "Adafruit INA219" 검색 후 설치
//
// 릴레이 결선: NC=한전, NO=인버터, COM=부하3
//
// 중요: INA_LOW_mA는 INA219로 재측정한 실측값(대기/공급)의 중간값으로 다시 확정할 것.

#include <Wire.h>
#include <Adafruit_INA219.h>

// ---------- CT 센서 ----------
const int CT_PIN = 1;                 // XIAO ESP32S3: D0 (GPIO1)
const int SAMPLE_COUNT = 1000;
int samples[SAMPLE_COUNT];
const float CALIBRATION = 0.727;
const float I_HIGH = 0.090;           // 절체 임계값(A)
const int CONSEC_REQUIRED = 2;        // 노이즈 방지: 연속 이 횟수 넘어야 절체

// ---------- 릴레이 ----------
const int RELAY_PIN = 2;              // XIAO ESP32S3: D1 (GPIO2)

// ---------- INA219 ----------
Adafruit_INA219 ina219;               // 기본 주소 0x40
// 실측(구형 리그): 대기 600~700mA / 공급 1000mA+ → 중간값 850.
// 650은 대기 대역(600~700) 안이라 부하3을 꺼도 복귀가 안 될 수 있음.
// INA219 리그에서 대기/공급 재측정 후 중간값으로 다시 확정할 것.
const float INA_LOW_mA = 850.0;

// ---------- 상태 ----------
bool isPeak = false;
int overCount = 0;
int underCount = 0;
// 절체/복귀 직후 판단 유예: 인버터 전류가 정격에 도달하기까지 2~3초 램프가 있어
// (실측 확인) 유예 없이는 램프 구간을 "부하3 꺼짐"으로 오판해 즉시 복귀한다.
const unsigned long STABILIZE_MS = 10000;
unsigned long lastSwitchMillis = 0;

void setup() {
  Serial.begin(115200);
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

  delay(500);
  lastSwitchMillis = millis() - STABILIZE_MS;   // 부팅 직후에는 유예 없이 바로 판단
  Serial.println("피크 셰이빙 시작 (CT: 절체 판단 / INA219: 복귀 판단)");
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

  Serial.print("CT(A): ");
  Serial.print(ctCurrent, 4);
  Serial.print("   INA219(mA): ");
  Serial.print(inaCurrent_mA, 1);
  Serial.print("   상태: ");
  Serial.print(isPeak ? "NO(ESS)" : "NC(한전)");

  // 절체/복귀 직후 안정화 유예 — 인버터 램프·과도 전류를 오판하지 않도록 판단 보류
  if (millis() - lastSwitchMillis < STABILIZE_MS) {
    Serial.print("   [안정화 대기 ");
    Serial.print((STABILIZE_MS - (millis() - lastSwitchMillis)) / 1000 + 1);
    Serial.println("s]");
    delay(1000);
    return;
  }

  if (!isPeak) {
    if (ctCurrent > I_HIGH) {
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
    if (inaCurrent_mA < INA_LOW_mA) {
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

  delay(1000);
}
