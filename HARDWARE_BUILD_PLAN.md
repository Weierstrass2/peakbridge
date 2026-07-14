# ESS 피크쉐이빙 하드웨어 데모 — 최종 구축 계획서 (v3 확정판)

> 이 문서는 Claude Code에게 그대로 전달하는 구현 지시서다.
> 하드웨어 담당의 최종 회신(A-2 시나리오 교정, MQTT 조건 3종, config 검증 규칙)과
> 대회 필수 파이프라인(01 센서노드 → 02 RPi 게이트웨이 MQTT → 03 클라우드 서버 → 04 DB → 05 웹)을 모두 반영했다.
> **Q9=NO 확정: 합숙 전 하드웨어 원격 테스트 없음.** 실기 통합은 합숙 1일차에 처음 이루어진다.
> 따라서 mock_esp32.py가 합숙 전 유일한 통합 검증 수단이며, 인터페이스 스펙과 1:1로 정확히 일치해야 한다.

---

## 0. 전제 (절대 준수)

- 기존 `backend/`, `frontend/`, `frontend-vpp/` **무변경**. 이 시스템은 완전 분리된 별도 시스템.
- 기존 빈 `hardware/` 디렉토리(README만 있음)를 사용.
- 클라우드 의존 금지: 시연은 로컬 폐쇄망(공유기/핫스팟)에서 완결. 인터넷은 보너스(브리지)용.
- 모든 코드 주석·문서·커밋 메시지는 한국어.
- device_id는 `"ess-demo-01"` 고정 (하드웨어 담당 확정).
- 합숙 전 실기 테스트가 없으므로: **모든 엔드포인트·MQTT 토픽·페이로드는 아래 스펙에서 한 글자도 벗어나면 안 됨.** 현장에서 스펙 불일치를 고칠 시간이 없다.

---

## 1. 디렉토리 구조

```
hardware/
  README.md                  # 기존 파일에 실행법/합숙 체크리스트 섹션 추가
  .gitignore                 # 신규: *.db, node_modules/, dist/, wifi_secrets*
  server/
    main.py                  # FastAPI 앱: 라우트, CORS, startup, 정적 서빙
    models.py                # Pydantic 모델
    db.py                    # sqlite3 stdlib 연결/스키마/쿼리 헬퍼
    mqtt_gateway.py          # mosquitto 구독/발행 (paho-mqtt), 선택 기동
    bridge.py                # 클라우드 릴레이 (BRIDGE_URL 설정 시에만 동작)
    mock_esp32.py            # 모의 ESP32 (FastAPI 비의존, HTTP/--mqtt 양쪽 지원)
    requirements.txt
    peakbridge_hardware.db   # (gitignore) 런타임 생성
  dashboard/
    index.html               # CDN 절대 금지, 시스템 폰트 스택 (맑은 고딕 포함)
    vite.config.ts           # frontend-vpp 패턴, dev 포트 5181
    tsconfig.json            # frontend-vpp 것 복사
    package.json
    src/
      main.tsx
      App.tsx                # 레이아웃 + 폴링 오케스트레이션
      styles.css             # frontend-vpp 디자인 토큰 축약판
      lib/api.ts             # 타입드 fetch 클라이언트
      components/
        CurrentChart.tsx     # recharts + ReferenceLine 2개 + 절체 이벤트 세로 마커
        RelayStateBanner.tsx # NC(파랑)/NO(주황) 대형 배너 + hold 카운트다운
        EventLog.tsx         # 전환 이력
        ConfigForm.tsx       # 임계값 설정 (검증 포함)
        EssPanel.tsx         # v2 필드 (null → "—")
```

포트: 서버 **8010** (기존 backend 로컬 8000과 충돌 방지), 대시보드 dev **5181** (5173/5180과 구분).

**정적 서빙 (중요):** `npm run build` 결과 `dashboard/dist/`를 main.py가 `/`에 StaticFiles로 마운트.
→ 시연 시 라즈베리파이에는 **Python만 있으면 됨** (node 불필요). dev 서버는 개발 중에만 사용.

---

## 2. SQLite 스키마 (db.py)

sqlite3 stdlib만 사용 (SQLAlchemy 금지 — 라즈베리파이 이식성). `PRAGMA journal_mode=WAL`.

- **telemetry** (append-only): `id, device_id, timestamp, received_at, grid_current_a, relay_state, threshold_high_a, threshold_low_a, hold_remaining_s, battery_voltage_v(NULL), ess_current_a(NULL), ess_power_w(NULL)`
  - 인덱스: `(device_id, received_at)`
- **events** (파생): `id, device_id, from_state, to_state, timestamp, received_at, grid_current_a`
  - 텔레메트리 수신 핸들러에서: 직전 행 조회 → 신규 INSERT → relay_state 변화 시 events 1행 기록
  - HTTP 경로와 MQTT 경로가 **동일한 저장 함수를 공유**할 것 (이벤트 감지 로직 중복 금지)
- **config** (싱글턴, `id=1 CHECK`): `id, threshold_high_a, threshold_low_a, min_hold_s, updated_at`
  - 시드값: **0.09 / 0.055 / 30** (`INSERT OR IGNORE`로 항상 존재 보장)

**시간 규칙 (하드웨어 회신 반영):**
- ESP32의 `timestamp`는 epoch 초. NTP 미동기 시 **0으로 무기한 올 수 있음** (백그라운드 재시도 중) — 0을 그대로 저장하고, 절대 서버 시각으로 바꿔치기하지 말 것.
- 정렬·이력 조회·이벤트 시각 표시는 전부 **received_at(서버 UTC)** 기준. 화면 표시는 로컬 시각 변환.
- 이벤트 시각 1~2초 오차는 허용 (재전송 없음, seq 필드 없음 — 하드웨어와 합의됨).

---

## 3. HTTP API (main.py, models.py)

Pydantic 모델: `TelemetryIn` (v1 필수 + v2 옵셔널 `float | None`), `ConfigModel`, `TelemetryResponse{ok, config}`, `TelemetryRecord`, `EventRecord`, `ConfigUpdate`.

| Method | Path | 동작 |
|---|---|---|
| POST | `/api/telemetry` | 저장 → 이벤트 감지 → **응답 body에 현재 config 포함** (ESP32가 별도 폴링 없이 최신 임계값 수신 — HTTP 폴백 경로의 핵심) |
| GET | `/api/latest` | 최신 1건. 없으면 404 (프론트 "연결 대기" 처리) |
| GET | `/api/history?minutes=10` | received_at 기준 구간 시계열 |
| GET | `/api/events` | 전환 이력 |
| GET/PUT | `/api/config` | 조회·변경. PUT 성공 시 저장값 반환 + MQTT 활성 시 config 토픽으로 **retained·QoS1 재발행** |

**config 검증 (펌웨어와 동일 규칙 — 하드웨어 확정, 서버가 거울처럼 검증):**
- `threshold_high_a > threshold_low_a > 0`
- `5 ≤ min_hold_s ≤ 300`
- 위반 시 **422** + 한국어 사유 메시지. (펌웨어도 같은 규칙으로 거부하므로, 서버가 먼저 막으면 불일치 상태가 생길 수 없음)

CORS `allow_origins=["*"]`, `host="0.0.0.0"`, `port=8010`.
requirements.txt: `fastapi, uvicorn[standard], pydantic, paho-mqtt, requests`. (SQLAlchemy/asyncpg 금지)

---

## 4. MQTT 게이트웨이 (mqtt_gateway.py) — 대회 파이프라인 02 충족

브로커: mosquitto (합숙 때 라즈베리파이에 설치, 개발 중엔 로컬 설치 또는 미기동).

- 토픽: `peakbridge/demo/telemetry` (ESP32→서버, QoS0, 페이로드 = HTTP와 동일 JSON)
- 토픽: `peakbridge/demo/config` (서버→ESP32, **retained=True, QoS1** — 하드웨어 조건 ①. ESP32 재부팅/재접속 시 즉시 최신 config 수신 보장)
- 게이트웨이는 telemetry 구독 → **HTTP 핸들러와 동일한 저장 함수** 호출.
- config PUT 시마다 + 서버 기동 시 1회, config를 retained로 발행.
- 기동 방식: `MQTT_BROKER` 환경변수(예: `192.168.0.10`)가 **설정된 경우에만** main.py startup에서 백그라운드 스레드로 접속. 미설정이면 HTTP-only 모드로 완전 동작 (합숙 전 개발·리허설은 HTTP 모드로 충분, MQTT는 현장 리스크 헤지용 폴백 구조 — 하드웨어 조건 ③ "HTTP 폴백 명문화" 충족).
- 브로커 접속 실패 시 경고 로그만 남기고 서버는 정상 동작 (크래시 금지, 무한 재접속은 백오프).

---

## 5. 클라우드 브리지 (bridge.py) — 선택 실행

- `BRIDGE_URL` 환경변수 설정 시에만 동작: 수신 텔레메트리를 기존 Railway 백엔드 `/api/v1/sensors/readings`에 `GRID-01` 디바이스로 릴레이 → 기존 아파트 대시보드·VPP OS가 실물 데이터로 살아 움직임 (시연 보너스).
- **Q9=NO이므로 클라우드 테스트 주소 사전 개설 작업은 하지 않는다.** 브리지는 코드만 만들어두고 기본 OFF. 합숙 현장에서 인터넷이 되면 환경변수 한 줄로 켠다.
- 릴레이 실패가 로컬 저장·응답을 **절대 지연/차단하지 않을 것** (비동기 fire-and-forget + 실패 시 경고 로그만).

---

## 6. 모의 ESP32 (mock_esp32.py) — A-2 교정 시나리오 (물리적으로 정확한 버전)

FastAPI 비의존 독립 스크립트, 1Hz 루프. `--url`(기본 `http://localhost:8010`) / `--mqtt <broker>` 모드 지원.
로컬 상태: relay_state, hold_until_ts, 로컬 config (HTTP 모드: POST 응답으로 매 루프 갱신 / MQTT 모드: retained config 토픽 구독).

**시나리오 (하드웨어 담당이 교정한 물리 정확 시퀀스 — 반드시 이대로):**

| 단계 | 상황 | 전류 | 릴레이 |
|---|---|---|---|
| 1 | 부하1만 ON (기준선) | ~0.036A | NC |
| 2 | 부하2 ON | ~0.072A | NC |
| 3 | 부하3 ON → **I_high(0.09) 초과** | 0.108A → 절체 후 **0.072A로 하락** (부하3이 ESS로) | **NC→NO** + hold 30s 시작 |
| 4 | hold 만료 후에도 0.072 > I_low(0.055) → **복귀하지 않음** (약 20초 유지 — 히스테리시스 증명 구간) | 0.072A | NO 유지 |
| 5 | **부하1 OFF 이벤트** → 0.036 < I_low | 0.036A → 복귀 후 **0.072A로 상승** (부하3이 한전으로 돌아옴: 부하2+부하3) | **NO→NC** |
| 6 | 부하 초기화 후 1단계로 루프 | | |

- 매 샘플에 ±0.002A 노이즈 지터 추가 (실측 느낌).
- 절체 판단은 **로컬 히스테리시스** (서버 개입 없음 — 실기기와 동일 철학).
- 서버 연결 실패 시 마지막 config로 계속 동작, 경고 로그만 (크래시 금지).
- config 수신 시 펌웨어와 동일 규칙으로 검증, 불합격 값은 거부 로그.

**주의:** 구 시나리오("hold 만료 후 자동 복귀")는 물리적으로 틀렸음이 확인되어 폐기됨. 절대 되살리지 말 것.

---

## 7. 대시보드 (dashboard/)

- `lib/api.ts`: frontend-vpp 패턴 — 타입 인터페이스 + get/put 헬퍼 + `hardwareApi` 객체. `VITE_API_URL` (기본 `http://localhost:8010`).
- `App.tsx` 폴링: `/api/latest` 1초 (배너·hold 카운트다운), `/api/history?minutes=10` 2초 (그래프), `/api/events` 5초. Config 폼은 마운트 1회 + 저장 성공 후에만 재조회 (입력 중 덮어쓰기 방지).
- `CurrentChart.tsx`: recharts LineChart + `ReferenceLine y={I_high}`(주황 점선) / `y={I_low}`(파랑 점선) + **이벤트 시각 세로 마커** (절체 순간이 그래프에서 보이게).
- `RelayStateBanner.tsx`: "평상시 — 한전 공급 (NC)" 파랑 / "피크 — ESS 공급 (NO)" 주황 + hold 남은 초 카운트다운. 최신 텔레메트리가 10초 이상 끊기면 "연결 대기" 회색 상태.
- `EventLog.tsx`: NC→NO / NO→NC 이력, received_at 로컬 시각 표시.
- `ConfigForm.tsx`: 3개 입력 + 저장. **클라이언트 검증 = 서버와 동일 규칙** (I_high > I_low > 0, hold 5~300). 422 응답 사유 표시.
- `EssPanel.tsx`: v2 필드 3개 (battery_voltage_v / ess_current_a / ess_power_w), null → "—" (INA226 확장 자리).
- index.html에 외부 CDN·웹폰트 링크 **금지**. 시스템 폰트 스택.
- 완성 후 `npm run build` → dist가 서버 `/`에서 서빙되는 것까지 확인.

---

## 8. 검증 계획 (합숙 전 — 소프트웨어 단독, mock이 유일한 통합 증거)

실기 테스트가 없으므로 여기서의 검증이 곧 최종 검증이다. 전 단계 자동화(curl) + 대시보드만 수동.

1. `pip install -r hardware/server/requirements.txt` (새 venv), `npm install` (dashboard)
2. 서버 기동(HTTP-only 모드) → `curl :8010/api/config` 시드값 0.09/0.055/30 확인 → `curl :8010/api/latest` 404 확인
3. `mock_esp32.py` 실행 → latest 채워짐 → history 누적 → 시나리오 1바퀴 관찰: **NC→NO 이벤트, hold 만료 후에도 NO 유지(4단계), 부하1 OFF 후 NO→NC + 전류 상승** 이 3가지가 events/telemetry에 정확히 기록되는지 확인
4. `curl -X PUT :8010/api/config` 로 (a) 유효값 → mock 로그에 다음 루프 반영 확인 (라운드트립 증명), (b) **위반값 3종** (`I_high ≤ I_low`, 음수, hold 4/301) → 422 확인
5. (mosquitto 로컬 설치 가능 시) `MQTT_BROKER=localhost`로 재기동 + `mock_esp32.py --mqtt localhost` → 동일 시나리오 통과 + `mosquitto_sub -t peakbridge/demo/config -v`로 **retained config 즉시 수신** 확인. 설치 불가 시 이 단계는 합숙 1일차로 이월하고 README에 명시.
6. `npm run dev`(5181) → 그래프/배너/이벤트로그/설정폼(검증 포함)/ESS패널 수동 확인 → `npm run build` → 서버 `:8010/`에서 dist 서빙 확인
7. 노트북 LAN IP로 폰 브라우저 접속 교차 확인 (Windows 방화벽 인바운드 **8010, 1883** 허용 필요 — README에 기록)

## 9. README에 추가할 합숙 1일차 체크리스트 (문서 작업)

1. 배선 상호 검수 → 통전 (30분, 하드웨어와 함께)
2. 공유기 설치 → 파이 **DHCP 예약 고정 IP** 설정 → SSID/PW 확정해 하드웨어에게 전달 (카톡, **git에 절대 커밋 금지** — wifi_secrets는 gitignore)
3. 파이에 mosquitto 설치 + `MQTT_BROKER` 설정 → mock으로 파이 단독 스모크 테스트 → 실기 ESP32 연결
4. 리허설 수칙: **시연 중 ESP32 리셋 금지** (재부팅 시 릴레이 NC 순단 → 부하3 깜빡임), 2일차 오후는 버퍼로 비워둠
5. 시연 프라이머리 화면 = **파이가 서빙하는 로컬 대시보드(8010)**. 클라우드(기존 Railway 콘솔·아파트 대시보드)는 인터넷 되면 보너스로 띄움 (BRIDGE_URL ON)

## 10. 범위 밖 (하지 않는 것)

- 기존 backend/, frontend/, frontend-vpp/ 수정 — 절대 금지
- 클라우드 테스트 주소 사전 개설 (Q9=NO로 제외됨)
- 인증, Postgres, WebSocket, Railway 배포 (이 시스템은 로컬 전용)
- 실제 ESP32 펌웨어 (하드웨어 담당 영역 — 위 스키마·토픽·검증 규칙만 지키면 서버/프론트 무변경 연동)

## 11. 구현 순서 (Claude Code 권장 진행)

db.py → models.py/main.py (HTTP) → mock HTTP 모드로 8단계 검증 2~4 → mqtt_gateway.py + mock `--mqtt` → bridge.py → dashboard 컴포넌트 → build/정적 서빙 → README/체크리스트 → 최종 스모크 테스트 전체 재실행.
각 단계 완료 시마다 커밋 (한국어 커밋 메시지).
