# 로컬 폐쇄망 실증 데모 (server/ + dashboard/)

> 이 시스템은 **두 하드웨어 구성을 동시에 수용**한다.
>
> - **구성 A** — `HARDWARE_BUILD_PLAN.md`(v3 확정판): ESP32 1대(`ess-demo-01`)가 로컬 히스테리시스로
>   절체를 판단하고 완결 페이로드를 발행. 인터넷 불필요.
> - **구성 B** — 같은 폴더 `README.md`(팀원A): ESP32 3대(grid/ess/relay)가 건물 토픽으로 조각 데이터 발행.
>   `adapters.py`가 이를 흡수해 **동일한 저장 경로·동일한 대시보드**로 합류시킨다.
>
> 둘 다 켜둔 채로 시연할 수 있고, 대시보드에서 디바이스를 전환해 각각 볼 수 있다.
> 자세한 매핑은 아래 "구성 B 흡수" 참조.

로컬 폐쇄망 전용 독립 시스템. 기존 `backend/` `frontend/` `frontend-vpp/` 와 완전히 분리되어 있으며,
인터넷 없이 이 시스템 하나로 시연이 완결된다. (인터넷이 되면 클라우드 브리지가 보너스로 켜진다)

## 파이프라인

```
01 센서노드(ESP32)  →  02 RPi 게이트웨이(MQTT/HTTP)  →  03 서버(FastAPI :8010)
                                                        →  04 DB(SQLite)  →  05 웹(대시보드)
```

- 절체 판단은 **ESP32 로컬 히스테리시스**로 이루어진다. 서버는 판단하지 않고 기록·설정 배포만 한다.
- MQTT가 주 경로, HTTP가 폴백 경로. `MQTT_BROKER` 미설정 시 HTTP-only로 완전 동작한다.
- device_id는 `ess-demo-01` 고정.

## 빠른 실행

```bash
# 1) 서버 (HTTP-only 모드)
cd hardware/server
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8010

# 2) 모의 ESP32 (다른 터미널)
python mock_esp32.py                       # HTTP 모드
python mock_esp32.py --mqtt 192.168.0.10   # MQTT 모드

# 3) 대시보드 (개발 중에만 — 시연은 빌드본을 서버가 서빙)
cd hardware/dashboard
npm install
npm run dev        # http://localhost:5181
```

MQTT·클라우드 브리지를 켤 때:

```bash
MQTT_BROKER=192.168.0.10 \
BRIDGE_URL=https://peakbridge-production.up.railway.app \
python -m uvicorn main:app --host 0.0.0.0 --port 8010
```

## 아파트 관제 대시보드와 연결하기 (핵심 시연 포인트)

하드웨어 실측 전류를 **기존 아파트 관제 대시보드**로 그대로 흘려보낸다.
`bridge.py`가 `POST {BRIDGE_URL}/api/v1/sensors/readings` 로 릴레이하면:

- 아파트 대시보드 `grid_current` 카드가 **실물 CT 값**으로 바뀐다
- 백엔드 `peak_service.evaluate()`가 돌아 **피크 알림·차트가 실물 절체에 반응**한다
- WebSocket 브로드캐스트로 화면이 실시간 갱신되고, VPP OS 콘솔의 StateCollector도 같은 DB를 읽는다
- 배터리 전압이 있으면 `ess_soc`로 환산해 함께 보내므로 **ESS 카드도 살아난다**

기존 백엔드는 이 엔드포인트에 **인증을 요구하지 않으며**, 없는 device_id는
`building_id`와 함께 보내면 자동 등록된다. 별도 백엔드 수정이 전혀 필요 없다.

```bash
BRIDGE_URL=https://peakbridge-production.up.railway.app \
MQTT_BROKER=<파이IP> \
python -m uvicorn main:app --host 0.0.0.0 --port 8010
```

### ⚠️ 반드시 함께 할 것: 피크 임계치 조정

실물 데모 전류는 **0.036~0.108A**다. 기존 시연용 임계치가 `PEAK_THRESHOLD_A=0.5`로 잡혀 있으면
절체가 일어나도 대시보드는 피크로 인식하지 않는다.

**권장:** Railway 환경변수를 `PEAK_THRESHOLD_A=0.08` 로 낮춘다 (실측 I_HIGH 0.090A 바로 아래).
실측값을 그대로 올리므로 "왜 0.09A냐"는 질문에 **"축소모형 실증"**이라고 정직하게 답할 수 있다.

화면상 아파트 규모(수십 A)로 보이길 원하면 `BRIDGE_SCALE=200` 처럼 환산할 수 있다.
이 경우에도 **원측정값은 로컬 DB와 로그에 그대로 남으므로** 설명 근거는 유지된다.
다만 심사에서 물으면 환산값임을 밝힐 것.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `BRIDGE_URL` | (없음) | 미설정 시 브리지 비활성 |
| `BRIDGE_BUILDING_ID` | `building-A` | 릴레이 대상 건물 |
| `BRIDGE_DEVICE_ID` | `GRID-01` | 계통 전류 디바이스 |
| `BRIDGE_ESS_DEVICE_ID` | `ESS-01` | SOC 디바이스 |
| `BRIDGE_SCALE` | `1.0` | 전류 환산 계수 (1.0 = 실측 그대로) |
| `BRIDGE_MIN_INTERVAL_S` | `2.0` | 전송 최소 간격. **절체 순간은 간격 무시하고 항상 전송** |

브리지 실패는 로컬 저장·응답을 절대 막지 않는다 (fire-and-forget). 인터넷이 끊겨도
로컬 대시보드는 그대로 살아 있다 — `verify_bridge.py`가 이 내성까지 검증한다.

## 대시보드 빌드 → 서버 정적 서빙 (시연 구성)

```bash
cd hardware/dashboard && npm run build      # → dashboard/dist
```

`dist/`가 존재하면 서버가 `/`에 자동 마운트한다. **시연 시 라즈베리파이에는 Python만 있으면 된다.**

> `dist/`는 `.gitignore` 대상이다. 노트북에서 빌드한 `dist/` 폴더를 파이로 직접 복사할 것
> (파이에서 `npm install`을 돌리지 말 것 — 느리고 실패 위험이 크다).

## API

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/telemetry` | 텔레메트리 수신. **응답 body에 현재 config 동봉** (ESP32가 폴링 없이 최신 임계값 수신) |
| GET | `/api/latest` | 최신 1건. 없으면 404 (프론트 "연결 대기") |
| GET | `/api/history?minutes=10` | received_at 기준 시계열 |
| GET | `/api/events` | NC↔NO 전환 이력 |
| GET/PUT | `/api/config` | 임계값 조회·변경. 위반 시 **422 + 한국어 사유** |
| GET | `/api/devices` | 수신 이력이 있는 디바이스 목록 (대시보드 선택기용) |
| GET | `/api/health` | 서버·MQTT·브리지·레거시 어댑터 상태 |

`/api/latest` `/api/history` `/api/events` 는 모두 `device_id` 쿼리 파라미터로 필터할 수 있다.

MQTT 토픽:

- `peakbridge/demo/telemetry` — ESP32 → 서버 (QoS0, 페이로드는 HTTP와 동일 JSON)
- `peakbridge/demo/config` — 서버 → ESP32 (**retained=True, QoS1**. 재부팅 시 즉시 최신 config 수신)

## 설정 검증 규칙 (서버·펌웨어·프론트 3중 동일)

- `threshold_high_a > threshold_low_a > 0`
- `5 ≤ min_hold_s ≤ 300`

세 곳이 같은 규칙을 쓰므로 설정이 서로 갈라진 상태가 구조적으로 발생하지 않는다.
시드값은 **0.09A / 0.055A / 30초**.

## 시간 규칙

- ESP32의 `timestamp`(epoch 초)는 NTP 미동기 시 **0으로 무기한 올 수 있다**. 0을 그대로 저장하고
  **절대 서버 시각으로 바꿔치기하지 않는다.**
- 정렬·이력 조회·이벤트 표시는 전부 `received_at`(서버 UTC) 기준. 화면에서만 로컬 시각으로 변환.
- 이벤트 시각 1~2초 오차는 허용 (재전송·seq 없음 — 하드웨어와 합의됨).

## 자동 검증

```bash
cd hardware/server
python verify_local.py    # HTTP 경로 + A-2 시나리오 3대 증거 + config 422 (13항목)
python verify_mqtt.py     # MQTT 경로 + retained config (4항목, amqtt 필요)
python verify_legacy.py   # 구성 B 흡수 + 두 구성 동시 공존 (8항목, amqtt 필요)
python verify_ina.py      # 실기 펌웨어 방식(CT 절체 / INA226 복귀) (8항목)
python verify_bridge.py   # 아파트 관제 연결: 페이로드·SOC 환산·장애 내성 (9항목)
```

`verify_mqtt.py`는 mosquitto가 없는 환경을 위해 순수 파이썬 브로커(amqtt)를 임시로 띄운다:
`pip install amqtt`. **합숙 현장에서는 실제 mosquitto로 동일 검증을 다시 수행할 것.**

두 스크립트는 시간축을 압축해 돌린다(`--scale`). **시연은 항상 실속도(1.0)**.

### 최근 검증 결과 (2026-07-28, 소프트웨어 단독)

- `verify_local.py` 13/13 통과 — 절체 트리거 0.106A, hold 만료 후 NO 유지 샘플 24건,
  복귀 0.0372A → 직후 0.0736A로 상승
- `verify_mqtt.py` 4/4 통과 — 서버 브로커 접속, MQTT/HTTP 저장 경로 공유, retained config
  신규 구독자 즉시 수신
- `verify_legacy.py` 8/8 통과 — 3-노드 메시지 흡수(21.7A, 3.45V/-2.3A/-7.935W), relay ack
  절체·복귀 이벤트, 두 구성 동시 수신(ess-demo-01 / building-A) 및 임계값 비혼입
- `verify_ina.py` 8/8 통과 — CT 절체 / INA226 복귀 역할 분담, ESS 공급 구간 800mA 관측 32건,
  ina_low_ma 범위 검증 422
- `verify_bridge.py` 9/9 통과 — 기존 백엔드 스키마 그대로 복사한 스텁으로 검증(실서버 422 없음),
  13.4V→SOC 33.3% 환산, 스케일 적용, 절체 샘플 즉시 전송, 백엔드 다운 시에도 로컬 저장 지속

## 실기 펌웨어 대응 (esp32_peak_shaving)

`peak_shaving_core.ino`는 **CT가 절체, INA226이 복귀**를 각각 전담한다 (CT만으로는 '부하3 꺼짐'과
'부하3 ESS 이관'을 구분할 수 없기 때문). 서버는 이 방식을 이미 수용한다:

- 텔레메트리 v3 필드 `ina_current_ma` 추가 (옵셔널)
- config에 `ina_low_ma` 추가 (시드 710mA — 실측 대기 626 / 공급 800의 중간값)
- `min_hold_s`·`threshold_low_a`를 쓰지 않는 펌웨어는 `hold_remaining_s: 0`으로 보내면 된다
- `mock_esp32.py --return-mode ina` 로 실기와 동일한 판단 방식을 재현 가능

펌웨어 팀이 필요한 접속 정보·페이로드·PubSubClient 예제는 [`FIRMWARE_MQTT_SPEC.md`](./FIRMWARE_MQTT_SPEC.md) 참조.

## A-2 시나리오 (모의 ESP32)

| 단계 | 상황 | 전류 | 릴레이 |
|---|---|---|---|
| 1 | 부하1만 ON | ~0.036A | NC |
| 2 | 부하2 ON | ~0.072A | NC |
| 3 | 부하3 ON → I_high 초과 | 0.108A → 절체 후 **0.072A로 하락** | NC→NO, hold 30s |
| 4 | hold 만료돼도 0.072 > I_low → **복귀 안 함** | 0.072A | NO 유지 |
| 5 | 부하1 OFF → 0.036 < I_low | 복귀 후 **0.072A로 상승** | NO→NC |
| 6 | 부하 초기화 후 1단계로 루프 | | |

> 구 시나리오("hold 만료 후 자동 복귀")는 물리적으로 틀렸음이 확인되어 폐기됐다. 되살리지 말 것.

**시연 설명 포인트:** 4단계가 히스테리시스의 증거다. 단일 임계값이었다면 여기서 릴레이가
계속 떨렸을 것(채터링). 5단계에서 전류가 오히려 **올라가는 것**이 절체가 실제로 물리적으로
일어났다는 증거다 (부하3이 ESS에서 한전으로 되돌아옴).

## 구성 B 흡수 (`adapters.py`)

팀원A의 3-노드 구성을 **펌웨어 수정 없이** 그대로 받는다. `README.md`에 적힌 토픽·페이로드
형식을 한 글자도 바꾸지 않아도 된다.

| 구성 B 토픽 | 어댑터 동작 |
|---|---|
| `peakbridge/<building>/grid/current` | 즉시 canonical 1행 기록 (device_id = `<building>`) |
| `peakbridge/<building>/ess/soc` | 섀도우 갱신 → 다음 grid 샘플에 전압·전류·전력으로 합류 |
| `peakbridge/<building>/control/relay/ack` | `discharge`→NO / `charge`·`standby`→NC, 즉시 1행 기록해 절체 이벤트 생성 |

- 세 조각을 건물 단위 섀도우 상태로 합쳐 **구성 A와 완전히 동일한 `save_telemetry` 경로**로 저장한다.
  이벤트 감지 로직이 한 벌뿐이므로 두 구성의 동작이 갈라지지 않는다.
- device_id가 `building-A` / `ess-demo-01`로 분리되어 데이터가 섞이지 않는다.
  대시보드 상단 칩으로 전환한다 (`GET /api/devices`).
- 구성 B는 전류 스케일이 실부하(수십 A)라 데모(0.09A)와 임계값이 다르다.
  기록·차트 표시용 값은 `LEGACY_THRESHOLD_HIGH_A` / `LEGACY_THRESHOLD_LOW_A` 환경변수로 조정
  (기본 20.0 / 15.0A). 구성 B의 **절체 판단 주체는 여전히 백엔드**이며 서버는 판단하지 않는다.
- 끄려면 `LEGACY_ADAPTER=0` (기본 ON).

```bash
python verify_legacy.py    # 구성 B 흡수 + 두 구성 동시 공존 (8항목)
```

**여전히 정해야 할 것:** 실기 ESP32가 어느 구성으로 구워질지. 서버는 양쪽을 다 받지만,
릴레이를 **누가 판단하느냐**(ESP32 로컬 vs 백엔드 명령)는 물리 배선과 펌웨어가 정해야 한다.
합숙 1일차에 이것만 확정하면 서버·대시보드는 손댈 필요가 없다.

## 합숙 1일차 체크리스트

1. **릴레이 판단 주체 확정** (ESP32 로컬 히스테리시스 vs 백엔드 명령). 펌웨어 굽기 전에 끝낼 것.
   서버는 어느 쪽이든 이미 수용한다.
2. **배선 상호 검수 → 통전** (30분, 하드웨어 담당과 함께). 검수 전 통전 금지.
3. **네트워크 구성**
   - 공유기 설치 → 파이에 **DHCP 예약으로 고정 IP** 부여
   - SSID/PW를 하드웨어 담당에게 전달 (카톡 등). **git에 절대 커밋 금지** — `wifi_secrets*`는 gitignore 처리됨
4. **파이 세팅**
   - `sudo apt install mosquitto mosquitto-clients`
   - `MQTT_BROKER=<파이IP>` 로 서버 기동 → `python mock_esp32.py --mqtt <파이IP>` 로 파이 단독 스모크 테스트
   - `mosquitto_sub -t peakbridge/demo/config -v` 로 retained config 즉시 수신 확인
   - 통과 후 실기 ESP32 연결
5. **방화벽**: 노트북에서 서버를 돌릴 경우 인바운드 **8010, 1883** 허용 (Windows Defender 방화벽)
6. **리허설 수칙**
   - **시연 중 ESP32 리셋 금지** — 재부팅 시 릴레이가 NC로 순단되어 부하3이 깜빡인다
   - 2일차 오후는 버퍼로 비워둘 것
7. **시연 화면 구성**
   - 프라이머리 = **파이가 서빙하는 로컬 대시보드** (`http://<파이IP>:8010`)
   - **하이라이트 = `BRIDGE_URL` 을 켜고 아파트 관제 대시보드를 함께 띄운다.**
     실물 부하3을 켜는 순간 → 로컬 배너 절체 → 같은 초에 클라우드 대시보드 전류 상승 + 피크 알림.
     "하드웨어 → 클라우드 → 관제 화면"이 한 화면에서 이어지는 것이 이 시연의 핵심이다.
   - 켜기 전 **Railway 환경변수 `PEAK_THRESHOLD_A=0.08` 확인** (0.5로 두면 피크가 안 잡힌다)

## 범위 밖 (의도적으로 하지 않은 것)

- 기존 `backend/` `frontend/` `frontend-vpp/` 수정 — **절대 금지**
- 인증, Postgres, WebSocket, Railway 배포 (이 시스템은 로컬 전용)
- 실제 ESP32 펌웨어 — 하드웨어 담당 영역. 위 스키마·토픽·검증 규칙만 지키면 서버/프론트 무변경 연동
