# PeakBridge Hardware

PeakBridge 프로젝트의 하드웨어 컴포넌트입니다.

## 폴더 구조

```
peakbridge/
├── backend/      ← 백엔드 (건드리지 마)
├── frontend/     ← 프론트 (건드리지 마)
└── hardware/     ← 여기가 내 작업 폴더
    ├── esp32_grid/       ← ESP32 #1 (그리드 전류)
    ├── esp32_ess/        ← ESP32 #2 (ESS SOC)
    ├── esp32_relay/      ← ESP32 #3 (릴레이 제어)
    ├── raspberry_pi/     ← 라즈베리파이 설정
    └── README.md
```

## ESP32 #1 — 그리드 전류 측정

파일 위치: `hardware/esp32_grid/esp32_grid.ino`

부품:
- ESP32 개발보드
- CT전류센서 SCT-013 (클램프형)
- 부하저항 220Ω (SCT-013 출력단)
- 커패시터 10uF

핵심 기능:
- SCT-013으로 AC 전류 측정
- RMS 전류값 계산 (A 단위)
- 5초마다 MQTT publish
- Wi-Fi 끊기면 자동 재연결

MQTT 설정:
- 브로커: 라즈베리파이 IP
- 포트: 1883
- 토픽: peakbridge/building-A/grid/current
- 형식: `{"value": 18.4, "unit": "A", "device_id": "esp32-grid-01", "building_id": "building-A"}`

필요한 라이브러리:
- PubSubClient (MQTT)
- ArduinoJson
- EmonLib (전류 측정)

## ESP32 #2 — ESS SOC 측정

파일 위치: `hardware/esp32_ess/esp32_ess.ino`

부품:
- ESP32 개발보드
- INA219 전류센서 모듈 (I2C)

핵심 기능:
- INA219로 배터리 전압/전류 측정
- SOC 계산
  LiFePO4 기준:
  3.65V 이상 → 100%
  3.20V 이하 → 0%
  선형 보간
- 5초마다 MQTT publish

MQTT 설정:
- 토픽: peakbridge/building-A/ess/soc
- 형식: `{"value": 72.0, "unit": "%", "voltage": 3.45, "current": -2.3, "device_id": "esp32-ess-01", "building_id": "building-A"}`

필요한 라이브러리:
- PubSubClient
- ArduinoJson
- Adafruit_INA219

## ESP32 #3 — 릴레이 제어

파일 위치: `hardware/esp32_relay/esp32_relay.ino`

부품:
- ESP32 개발보드
- SSR 솔리드스테이트 릴레이
- LED 3개 (빨강/파랑/초록)

핵심 기능:
- MQTT subscribe로 명령 수신
- 명령에 따라 SSR 릴레이 제어
  "discharge" → 방전 모드 (빨강 LED)
  "charge"    → 충전 모드 (파랑 LED)
  "standby"   → 대기 모드 (초록 LED)
- 명령 수신 후 백엔드에 확인 메시지 전송

MQTT 설정:
- 구독 토픽: peakbridge/building-A/control/relay
- 응답 토픽: peakbridge/building-A/control/relay/ack
- 수신 형식: `{"action": "discharge"}`
- 응답 형식: `{"status": "ok", "action": "discharge", "device_id": "esp32-relay-01"}`

필요한 라이브러리:
- PubSubClient
- ArduinoJson

## 라즈베리파이 설정

파일 위치: `hardware/raspberry_pi/setup.sh`

실행 방법:
```bash
cd hardware/raspberry_pi
chmod +x setup.sh
./setup.sh
```

## Wi-Fi 설정 (모든 ESP32 공통)

각 ESP32 코드 상단에:

```cpp
const char* WIFI_SSID = "여기에_와이파이_이름";
const char* WIFI_PASSWORD = "여기에_와이파이_비밀번호";
const char* MQTT_SERVER = "여기에_라즈베리파이_IP";
const int MQTT_PORT = 1883;
const char* BUILDING_ID = "building-A";
```

## 테스트 방법

라즈베리파이에서 모니터링:
```bash
mosquitto_sub -h localhost -t "peakbridge/#" -v
```

백엔드 서버 확인:
`https://peakbridge-production.up.railway.app/health`

Postman으로 수동 데이터 전송 테스트:
POST `https://peakbridge-production.up.railway.app/api/v1/sensors/readings`

Headers:
`Authorization: Bearer [토큰]`

Body:
```json
{
  "device_id": "esp32-grid-01",
  "sensor_type": "grid_current",
  "value": 18.4,
  "unit": "A",
  "building_id": "building-A"
}
```
