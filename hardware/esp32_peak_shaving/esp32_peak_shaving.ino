// esp32_peak_shaving.ino
// 목적: CT 센서(한전 인입 전류) + INA226(배터리->인버터 전류)을 함께 이용해
//       릴레이를 자동으로 절체하는 최종 로직.
//
// 판단 원칙:
//   NC -> NO 전환: CT 값이 임계값을 넘으면 (한전 쪽에서 피크를 감지)
//   NO -> NC 전환: INA226 값이 대기 전류 수준으로 떨어지면
//                  (부하 3이 꺼진 것을 배터리 쪽에서 직접 확인하므로,
//                   더 이상 15초 시험 절체가 필요 없다)
//
// 배선:
//   ZMCT103C  VCC -> ESP32 3V3  / GND -> GND  / OUT -> GPIO34
//   릴레이모듈 VCC(DC+) -> ESP32 5V(VIN) / GND(DC-) -> GND / IN1,IN2(묶어서) -> GPIO26
//   INA226    VCC -> ESP32 3V3 / GND -> ESP32 GND(배터리 -와 공유)
//             SDA -> GPIO21 / SCL -> GPIO22
//             큰 구멍 IN+ -> 배터리쪽 (+) / 큰 구멍 IN- -> 인버터쪽 (+)
//
// 릴레이 결선: NC=한전, NO=인버터, COM=부하3
//
// 중요: INA_LOW_mA는 실측(부하3 꺼짐=대기 / 부하3 켜짐=공급) 값의 중간으로
//       조정할 것. 현재 값(850mA)은 실측(대기 600~700mA / 공급 1000mA+)의 중간값이다.
//       하드웨어 구성이 바뀌면 재실측 후 갱신 필요.

#include <Wire.h>
#include <INA226_WE.h>

// ---------- CT 센서 ----------
const int CT_PIN = 34;
const int SAMPLE_COUNT = 1000;
int samples[SAMPLE_COUNT];
const float CALIBRATION = 0.727;
const float I_HIGH = 0.090;           // 절체 임계값(A)
const int CONSEC_REQUIRED = 2;        // 노이즈 방지: 연속 이 횟수 넘어야 절체

// ---------- 릴레이 ----------
const int RELAY_PIN = 26;

// ---------- 충전 알림 LED ----------
const int CHARGE_LED_PIN = 27;
const float CHARGE_THRESHOLD_V = 12.0;   // 이 전압 밑으로 내려가면 LED 켜짐 (충전 필요)

// ---------- 배터리 전압 (저항 분배 회로, INA226 Bus Voltage 대신 사용) ----------
// 배선: 배터리(+) -> R1(큰 저항) -> [분기점] -> R2(작은 저항) -> GND
//       분기점 -> ESP32 GPIO35
// DIVIDER_RATIO = (R1+R2)/R2 로 계산. 실제 사용하는 저항값에 맞게 반드시 수정할 것.
const int BATTERY_PIN = 35;
const float DIVIDER_RATIO = 11.0;   // 실사용: R1=1000Ω, R2=100Ω → (1000+100)/100 = 11.0

// ---------- INA226 ----------
#define I2C_ADDRESS 0x40
INA226_WE ina226(I2C_ADDRESS);
const float INA_LOW_mA = 850.0;        // 복귀 기준(mA). 실측: 대기 600~700mA, 공급 1000mA+의 중간값
const int RETURN_CONSEC_REQUIRED = 3;  // 노이즈 방지: 연속 이 횟수 미달이어야 복귀
// 절체/복귀 직후 판단 유예(ms). 실측: 절체 직후 인버터 전류가 1000mA대에 도달하기까지
// 2~3초 램프가 있어, 유예 없이는 램프 구간을 "부하3 꺼짐"으로 오판해 즉시 복귀한다.
const unsigned long STABILIZE_MS = 10000;

// ---------- 상태 ----------
bool isPeak = false;   // false = NC(한전), true = NO(ESS)
int overCount = 0;
int underCount = 0;
unsigned long lastSwitchMillis = 0;   // 마지막 절체/복귀 시각 (안정화 유예 계산용)

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);   // 시작은 항상 NC(한전)

  pinMode(CHARGE_LED_PIN, OUTPUT);
  digitalWrite(CHARGE_LED_PIN, LOW);

  analogReadResolution(12);
  analogSetPinAttenuation(CT_PIN, ADC_11db);
  analogSetPinAttenuation(BATTERY_PIN, ADC_11db);

  Wire.begin();   // ESP32 기본 SDA=21, SCL=22
  if (!ina226.init()) {
    Serial.println("INA226을 찾지 못했다. 배선(SDA/SCL, 주소)을 확인하세요.");
    while (1) delay(1000);
  }
  // R010(0.01옴) 션트 기준. R100 설정(0.1, 1.5)으로 두면 실전류의 ~1/10로 읽히고
  // 200mA 부근에서 클리핑됨 (실측으로 확인). 상한 8.2A — 공급 1A+ 여유.
  ina226.setResistorRange(0.01, 8.2);
  ina226.setAverage(INA226_AVERAGE_64);
  ina226.setConversionTime(INA226_CONV_TIME_1100);
  ina226.setMeasureMode(INA226_CONTINUOUS);

  delay(500);
  // 부팅 직후에는 유예 없이 바로 판단 시작 (unsigned 뺄셈이라 랩어라운드 안전)
  lastSwitchMillis = millis() - STABILIZE_MS;
  Serial.println("피크 셰이빙 시작 (CT: 절체 판단 / INA226: 복귀 판단)");
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

float readBatteryVoltage() {
  // analogReadMilliVolts: ESP32 공장 보정값이 적용된 mV 읽기 —
  // raw*(3.3/4095) 방식보다 ADC 비선형 구간에서 훨씬 정확하다
  float pinVoltage = analogReadMilliVolts(BATTERY_PIN) / 1000.0;
  return pinVoltage * DIVIDER_RATIO;
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
  float inaCurrent_mA = ina226.getCurrent_mA();
  float batteryVoltage = readBatteryVoltage();

  Serial.print("CT(A): ");
  Serial.print(ctCurrent, 4);
  Serial.print("   INA226(mA): ");
  Serial.print(inaCurrent_mA, 1);
  Serial.print("   배터리(V): ");
  Serial.print(batteryVoltage, 2);
  Serial.print("   상태: ");
  Serial.print(isPeak ? "NO(ESS)" : "NC(한전)");

  // 충전 필요 LED 판단
  // batteryVoltage가 0에 가까운 값(비정상 읽기)일 때는 판단하지 않고 LED를 꺼둔다.
  // 그렇지 않으면 읽기 오류를 "충전 필요"로 오해해서 LED가 항상 켜진 채로 고정될 수 있다.
  if (batteryVoltage > 5.0 && batteryVoltage < CHARGE_THRESHOLD_V) {
    digitalWrite(CHARGE_LED_PIN, HIGH);
    Serial.print("   [충전 필요! LED ON]");
  } else {
    digitalWrite(CHARGE_LED_PIN, LOW);
  }

  // 절체/복귀 직후 안정화 유예 — 인버터 램프·과도 전류를 오판하지 않도록 판단 보류
  if (millis() - lastSwitchMillis < STABILIZE_MS) {
    Serial.print("   [안정화 대기 ");
    Serial.print((STABILIZE_MS - (millis() - lastSwitchMillis)) / 1000 + 1);
    Serial.println("s]");
    delay(1000);
    return;
  }

  if (!isPeak) {
    // 평상시: CT 값으로 피크 여부 판단
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
    // ESS 상태: INA226 값으로 복귀 여부 판단
    if (inaCurrent_mA < INA_LOW_mA) {
      underCount++;
      Serial.print("   [복귀 대기 ");
      Serial.print(underCount);
      Serial.print("/");
      Serial.print(RETURN_CONSEC_REQUIRED);
      Serial.println("]");
      if (underCount >= RETURN_CONSEC_REQUIRED) goNC();
    } else {
      underCount = 0;
      Serial.println("   [공급 중]");
    }
  }

  delay(1000);
}
