// peak_shaving_core.ino
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
//       반드시 조정할 것. 지금 값(500mA)은 임시 기본값이다.

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
const float DIVIDER_RATIO = 11.0;   // 예: R1=10kΩ, R2=1kΩ일 때

// ---------- INA226 ----------
#define I2C_ADDRESS 0x40
INA226_WE ina226(I2C_ADDRESS);
const float INA_LOW_mA = 710.0;        // 복귀 기준(mA). 실측: 대기 ~626mA, 공급 ~800mA의 중간값
const int RETURN_CONSEC_REQUIRED = 2;  // 노이즈 방지: 연속 이 횟수 미달이어야 복귀

// ---------- 상태 ----------
bool isPeak = false;   // false = NC(한전), true = NO(ESS)
int overCount = 0;
int underCount = 0;

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
  ina226.setResistorRange(0.1, 1.5);    // R100(0.1옴) 기준, 상한을 1.5A로 올려 800mA대에서 안 잘리게
  ina226.setAverage(INA226_AVERAGE_64);
  ina226.setConversionTime(INA226_CONV_TIME_1100);
  ina226.setMeasureMode(INA226_CONTINUOUS);

  delay(500);
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
  int raw = analogRead(BATTERY_PIN);
  float pinVoltage = raw * (3.3 / 4095.0);
  return pinVoltage * DIVIDER_RATIO;
}

void goNO() {
  digitalWrite(RELAY_PIN, HIGH);
  isPeak = true;
  overCount = 0;
  underCount = 0;
  Serial.println("   -> 절체! NC에서 NO(ESS)로");
}

void goNC() {
  digitalWrite(RELAY_PIN, LOW);
  isPeak = false;
  overCount = 0;
  underCount = 0;
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
