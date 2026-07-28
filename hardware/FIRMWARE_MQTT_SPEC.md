# 펌웨어 ↔ 서버 연동 스펙 (하드웨어 담당용)

`esp32_peak_shaving/README.md`의 TODO — "Wi-Fi 연결 및 MQTT 전송 계층 추가 (SW팀 브로커 정보 필요)"
에 대한 답변 문서다. 아래 내용만 지키면 서버·대시보드는 **수정 없이** 그대로 붙는다.

서버는 `peak_shaving_core.ino`의 판단 로직(CT 절체 / INA226 복귀)을 이미 스키마에 반영해 두었고,
자동 검증(`server/verify_ina.py`) 8/8을 통과한 상태다.

## 1. 접속 정보

| 항목 | 값 |
|---|---|
| 브로커 | 라즈베리파이 IP (합숙 1일차에 DHCP 예약으로 고정 후 공유) |
| 포트 | 1883 |
| 인증 | 없음 (익명 허용, 로컬 폐쇄망) |
| 발행 토픽 | `peakbridge/demo/telemetry` (QoS 0) |
| 구독 토픽 | `peakbridge/demo/config` (QoS 1, retained) |
| device_id | `ess-demo-01` (고정) |
| 발행 주기 | 1초 권장 (5초도 무방) |

**HTTP 폴백:** MQTT가 안 될 때는 `POST http://<서버IP>:8010/api/telemetry` 에 같은 JSON을 보내면 된다.
응답 body에 최신 config가 들어 있어 별도 구독 없이 설정을 받을 수 있다.

## 2. 발행 페이로드 (ESP32 → 서버)

```json
{
  "device_id": "ess-demo-01",
  "timestamp": 1785213363,
  "grid_current_a": 0.108,
  "relay_state": "NO",
  "threshold_high_a": 0.090,
  "threshold_low_a": 0.055,
  "hold_remaining_s": 0,
  "ina_current_ma": 798.4,
  "battery_voltage_v": 13.2,
  "ess_current_a": null,
  "ess_power_w": null
}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `device_id` | ✅ | `"ess-demo-01"` 고정 |
| `timestamp` | ✅ | epoch 초. **NTP 미동기면 0을 그대로 보낼 것** (서버가 수신 시각으로 정렬하므로 문제 없음. 억지로 값을 만들지 말 것) |
| `grid_current_a` | ✅ | CT(ZMCT103C) 측정 한전 인입 전류 (A) |
| `relay_state` | ✅ | `"NC"`(한전) 또는 `"NO"`(ESS). **ESP32가 판단한 현재 상태를 그대로** |
| `threshold_high_a` | ✅ | 지금 적용 중인 `I_HIGH` (보통 0.090) |
| `threshold_low_a` | ✅ | INA 방식이면 안 쓰지만 스키마상 필수 — `0.055`를 그대로 보내면 됨 |
| `hold_remaining_s` | ✅ | 최소 유지시간을 안 쓰면 **항상 0** |
| `ina_current_ma` | 권장 | INA226 배터리→인버터 전류 (mA). 복귀 판단 근거이자 "부하3이 ESS로 넘어갔다"는 물리 증거 |
| `battery_voltage_v` | 선택 | 저항 분배 회로로 읽은 배터리 전압 (V) |
| `ess_current_a` / `ess_power_w` | 선택 | 없으면 `null` 또는 필드 자체를 빼도 됨 |

서버는 `relay_state`가 직전 값과 달라지는 순간을 **자동으로 절체 이벤트로 기록**한다.
펌웨어가 별도 이벤트 메시지를 보낼 필요는 없다.

## 3. 구독 페이로드 (서버 → ESP32, retained)

```json
{
  "threshold_high_a": 0.09,
  "threshold_low_a": 0.055,
  "min_hold_s": 30,
  "ina_low_ma": 710.0,
  "updated_at": 1785213363.02
}
```

- **retained·QoS1**이라 ESP32가 재부팅·재접속하면 즉시 최신 값을 받는다. 폴링 불필요.
- 대시보드에서 임계값을 바꾸면 이 토픽으로 즉시 재발행된다.
- 펌웨어는 받은 값을 **자체 검증 후** 적용할 것 (아래 규칙). 불합격이면 기존 값 유지 + 로그.

검증 규칙 (서버·대시보드와 동일):

```
threshold_high_a > threshold_low_a > 0
5   <= min_hold_s  <= 300
50  <= ina_low_ma  <= 8200
```

`I_HIGH`와 `INA_LOW_mA`를 하드코딩 상수 대신 이 값으로 갱신하면, 현장에서 배선을 안 건드리고
대시보드에서 임계값 튜닝이 가능하다. (실측 확정값 0.090A / 710mA가 이미 서버 시드값이다)

## 4. PubSubClient 참고 코드

```cpp
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* MQTT_SERVER = "192.168.0.10";   // 합숙 때 확정될 파이 IP
const int   MQTT_PORT   = 1883;
const char* DEVICE_ID   = "ess-demo-01";
const char* TOPIC_PUB   = "peakbridge/demo/telemetry";
const char* TOPIC_SUB   = "peakbridge/demo/config";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

void onConfig(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, len)) return;

  float high = doc["threshold_high_a"] | I_HIGH;
  float inaLow = doc["ina_low_ma"] | INA_LOW_mA;

  // 펌웨어 자체 검증 — 불합격이면 기존 값 유지
  if (high <= 0 || inaLow < 50 || inaLow > 8200) {
    Serial.println("config 거부: 범위 위반");
    return;
  }
  gThresholdHigh = high;   // 상수 대신 전역 변수로 빼둘 것
  gInaLowMa = inaLow;
}

void reconnect() {
  while (!mqtt.connected()) {
    if (mqtt.connect(DEVICE_ID)) {
      mqtt.subscribe(TOPIC_SUB, 1);   // QoS1 — retained config 즉시 수신
    } else {
      delay(2000);
    }
  }
}

void publishTelemetry(float ct, float inaMa, float batV, bool isPeak) {
  StaticJsonDocument<320> doc;
  doc["device_id"]        = DEVICE_ID;
  doc["timestamp"]        = 0;              // NTP 미동기면 0 그대로
  doc["grid_current_a"]   = ct;
  doc["relay_state"]      = isPeak ? "NO" : "NC";
  doc["threshold_high_a"] = gThresholdHigh;
  doc["threshold_low_a"]  = 0.055;
  doc["hold_remaining_s"] = 0;
  doc["ina_current_ma"]   = inaMa;
  doc["battery_voltage_v"] = batV;

  char buf[320];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(TOPIC_PUB, (uint8_t*)buf, n, false);
}
```

`setup()`에서 `mqtt.setServer(MQTT_SERVER, MQTT_PORT); mqtt.setCallback(onConfig);`,
`loop()`에서 `if (!mqtt.connected()) reconnect(); mqtt.loop();` 를 호출하면 된다.

**중요:** MQTT 전송 실패가 절체·복귀 판단을 막아서는 안 된다. 통신은 어디까지나 부가 기능이고,
판단은 ESP32 로컬에서 독립적으로 계속 돌아가야 한다 (`mock_esp32.py`도 같은 원칙으로 동작한다).

## 5. 먼저 확인하는 방법 (실기 없이)

서버·대시보드가 실제로 이 스펙대로 동작하는지 지금 바로 볼 수 있다:

```bash
cd hardware/server
pip install -r requirements.txt
python -m uvicorn main:app --port 8010     # 터미널 1
python mock_esp32.py --return-mode ina     # 터미널 2 — 실기 펌웨어와 동일한 판단 방식
```

브라우저에서 `http://localhost:8010` — 절체 배너, 전류 그래프, INA226 값, 절체 이력이 보인다.
(대시보드 빌드본이 없으면 `cd hardware/dashboard && npm install && npm run build` 후 재기동)
