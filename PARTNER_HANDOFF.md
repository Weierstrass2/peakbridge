# PeakBridge 인수인계 (2026-07-28 기준)

## 현재 상태 — 완료된 것

### 아파트 관제 (frontend/)
전 페이지 실데이터 연결, ESS 1대 구성, 타입에러 0. 버그 수정 완료(아래 7차 세션) 및 git 반영 완료.
**단, 프론트엔드 자체 호스팅/배포는 아직 설정 전** — git엔 최신 코드 있으나 실제 사이트 배포는 별도 진행 필요 (백엔드처럼 Railway 자동배포 연결 안 돼있음).

### 백엔드 (backend/, Railway 자동배포)
- 기본: 센서 MQTT/API 파이프라인, 피크쉐이빙, JWT, WebSocket, 알림/리포트
- AI: XGBoost 수요예측(실학습), PPO 제어(numpy 서빙, /ai/recommend), 시나리오 5종
- 시뮬: pandapower 배전망(/grid), VPP(/vpp), OpenADR(/dr), StateCollector(/state)
- **시장(A1~A3 완료)**:
  - /market/session·bids·submit·clear — DAM 입찰→개찰(pay-as-clear)+CP 이중정산
  - 가격엔진: 10년 실데이터 재생 (services/market_data.py — 요금캘린더×KPX수요백분위)
  - 자원 물리 레지스트리: core/resources.py (모든 검증·이행·학습이 이것만 참조)
  - /dispatch — 급전 이행 워커 (RTU 4s 하트비트, 60× 가속, 이행률, 위약 1.2×)
  - **/market/ai-bids — 학습된 입찰 AI** (models/bid_policy.json, CEM 학습)
    검증(150일 홀드아웃 일평균): AI +₩1,993 vs 룰전략 -₩68,458 vs 90원고정 -₩62,948
    재학습: `python backend/scripts/train_bid_policy.py`

### VPP OS 콘솔 (frontend-vpp/, 독립 앱, 포트 5180)
P1 셸/디자인시스템 → P2 금융급 차트(lightweight-charts) → P3 자원그리드+단선계통도
→ P4 DR콘솔+원장 → P5 한국지도(TopoJSON) → P6 전체화면(F키) → P7 모듈 확대뷰
→ A1 입찰데스크(24구간 시트, 마감 카운트다운, AI입찰/룰채움/제출/개찰)
→ A1+ 입찰곡선 차트, 상태 스테퍼, 세션 이력, 가격출처 표기
→ A2 급전이행 뷰(시장시계, 이행률, 위약, SOC)

실행: `cd frontend-vpp && npm install && npm run dev` → localhost:5180

## 시연 하이라이트 각본
1. 입찰 데스크: [룰 채움]→제출→개찰→[급전 이행] 활성화 → 대량 위약, 순손실 (물리 제약)
2. 새 세션에서 [AI 입찰]→제출→개찰→이행 → 흑자. "AI가 에너지 제약을 학습해 손실을 수익으로"
3. DR 운영: SIMPLE 3 발령 → 차트 마커+유닛 20기 점멸+지도 적색+원장 정산 동시 반응

## 추가 완료 (2차 세션)
- B1 알람 센터: /ops/alarms (+ACK), 개찰·위약·리스크가 자동 발보 → 콘솔 '운영 센터' 뷰
- B2 이행 리스크: /ops/risk — 가용 에너지 vs 낙찰 의무 커버리지, 105%/70% 임계 알람
- B4 감사 로그: /ops/audit — 제출·개찰·ACK 등 조작 기록
- A4 정산 유형별 집계: 원장 요약에 by_type (DR정산/급전정산/CP정산/위약금/차익거래)
- C3 콘솔 배포: 백엔드 /console 경로에 정적 서빙 —
  푸시·배포 후 https://peakbridge-production.up.railway.app/console 접속 (실URL!)
  콘솔 재빌드 시: cd frontend-vpp && npx vite build --base=/console/
  → dist를 backend/static/console 로 복사 후 커밋

## 3차 세션 추가 완료
- 원클릭 데모: POST /simulation/demo-day + 콘솔 통합개요 [원클릭 데모] 버튼
  (AI입찰→제출→개찰→급전 활성화 자동 시퀀스, 로그에 단계별 표시)
- A1+d 실시간 시장(RT): GET /market/rt (15분 슬롯·RT가격·카운트다운),
  POST /market/rt/sell (시장가 즉시 체결, 슬리피지 3%, 원장 'RT판매' 기록)
  → 콘솔 입찰 데스크 우측 RT 위젯 (즉시 판매 버튼)

## 4차 세션 추가 완료
- A5 계약 관리: GET /vpp/contracts — 단지별 계약(수익배분형/고정임대형, 배분율,
  기간, 자원 명세) + 총정산의 단지/플랫폼 배분 분해 → 콘솔 정산 원장 상단 표시
  ("플랫폼 매출" 표기 = 투자자용 BM 증거)
- 배포 검증: /market/rt 실서버 응답 확인 (RT ₩104.7 / DAM ₩114.0)

## 5차 세션 추가 완료
- C1 시계열 서버 보관: /vpp/stream/history (600pt) — 콘솔 새로고침 시 차트 복원
- B3-lite 운영자 식별: 레일 OPERATOR 입력 → 알람 ACK 감사 로그에 실명 기록
- 데모 리셋: POST /simulation/demo-reset + 콘솔 [리셋] 버튼 —
  시장·이행·원장·알람 전체 초기화 (리허설 반복용, SOC도 초기값 복원)

## 6차 세션 추가 (엔터프라이즈 리뷰 반영)
- AI 예측 신뢰구간: 스트림 forecast_hi/lo (±3.5% CI) → 차트에 밴드 점선 + 레전드 표기
- 물리 텔레메트리: 포트폴리오에 SOH·PCS온도·변환효율·통신ms → 자원 그리드 컬럼
  (SOH<95% 앰버, PCS>45°C 적색 경고색)
- 누적 이행률·위약 방어: dispatch cumulative {rate%, defended_won} → 급전 이행 요약
- CRITICAL 고정 스트립: 미확인 CRIT 알람을 마켓바 아래 적색 띠로 고정 + 즉석 ACK
- 리뷰 항목 중 잔여: 지도 기상 오버레이(일사량·풍속·특보) — 기상청 격자 API
  폴링 설계 필요, 파트너 백로그

## 7차 세션 추가 완료 (오늘, 2026-07-14)
- **VPP 콘솔 예측선 실제 XGBoost 연결**: `/vpp/stream`의 forecast_kw가 임의 사인파였던 것을
  학습된 XGBoost 모델(`XGBoostForecaster("building-A")`) 추론으로 교체. 모델이 단일 건물
  스케일이라 포트폴리오 수요 스케일에 5분 구간 트렌드 비율로 반영 (원시값 직결 시 스케일 불일치).
  배포 후 5분 구간 경계에서 비율이 계단식으로 점프하는 패턴으로 라이브 동작 검증 완료.
  (모델 자체는 아직 합성 데이터 학습 — 실측 재학습은 하드웨어로 실데이터 축적 후 가능)
- **버그: 피크 임계치 표시 불일치** — `dashboard.py`가 컨트롤 탭에서 설정한 값 대신 고정
  env값(`PEAK_THRESHOLD_A`)을 반환해 슬라이더가 적용 후에도 원래 값으로 보이던 문제.
  `get_threshold(building_id)` 참조하도록 수정, 라이브 라운드트립 검증 완료.
- **버그: 알림 탭 "확인(Acknowledge)" 버튼 미동작** — `reportApi.ts`의 `acknowledgeAlert`가
  실서버 모드에서 `console.warn`만 찍고 끝나는 미완성 스텁이었음(백엔드 `/alerts/{id}/resolve`는
  이미 존재). 실제 엔드포인트에 연결, 라이브에서 `resolved_at` 세팅까지 확인.
- **UX: 컨트롤 탭 중복 명령 메시지** — 30초 내 동일 액션 재전송 시 409를 "실패"로 오인하지
  않도록 별도 안내 메시지로 분리.
- **한글화**: 알림 탭에 남아있던 영어 UI 텍스트("Alerts", "Acknowledge" 등) 전체 한글로 교체.
- **전체 탭 실서버 검증**: 아파트 관제 프론트 전 탭(대시보드/충전기/컨트롤/리포트/알림/
  에너지거래/VPP/관제실)이 쓰는 API 27개(읽기 21 + 쓰기 6)를 프로덕션에 관리자 로그인 후
  직접 호출해 검증. 위 3건 수정 사항 전부 라이브 반영 확인, 그 외 신규 버그 없음.
  (리포트 절감량이 현재 0인 건 EnergySaving 데이터 미축적 때문 — 코드는 정상이며
  실데이터 5일 미만 시 예시 프로파일로 자동 폴백하게 이미 설계됨)
- **환경 확인**: 프로덕션 `MQTT_HOST`가 기본값(localhost)이라 브로커 미연결 상태
  (`mqtt_sent: false`) — 하드웨어 미제작 단계라 예상된 정상 상태. 제어 API는 MQTT
  성공 여부와 무관하게 DB 로그·알림 기록은 정상 동작하도록 설계돼 있어 문제없음.
  하드웨어 연결 시 실브로커 `MQTT_HOST`/`MQTT_PORT` env 설정 필요.

## 8차 세션 추가 완료 (2026-07-14 ~ 07-21)
- **콘솔 예측선 CI 밴드 → XGBoost MAE 기반으로 교체** (`52fc1ce3`): 기존 ±3.5% 고정
  퍼센트 밴드 대신 학습된 XGBoost 모델의 MAE를 신뢰구간 폭으로 사용 (`vpp.py`).
- **전국 지도 기상 오버레이 완료** (`52fc1ce3`, 6차 세션 잔여 백로그 해소): 기상청 실황
  API를 `weather_service.py`에서 폴링(10분 캐시)해 `/weather/map-overlay`로 서빙,
  콘솔 `MapPanel`에 오버레이 렌더 → **백로그 '지도 기상 오버레이' 완료.**
  ※ 이후 `349fe79e`에서 누락됐던 `/weather/map-overlay` 라우트 복구, `59cc6c27`에서
    콘솔 정적 번들 base 경로(`/console/`) 복구(검은 화면 수정).
  ※ 이 커밋에 포함됐던 `HARDWARE_BUILD_PLAN.md`는 `c4c79646`에서 제거(합숙 현장 재계획).
- **아파트 관제 대시보드 배포 완료** (`fcbb4f19`, 7차 세션 잔여 백로그 해소): 백엔드 `/app`
  경로에 정적 서빙 + SPA 폴백(`main.py`의 `SPAStaticFiles`), 실API 연동.
  → https://peakbridge-production.up.railway.app/app 접속. 재빌드 시 `frontend/`를
    `--base=/app/` 빌드 후 `backend/static/app`로 복사·커밋 (콘솔의 `/console`과 동일 패턴).
  → **백로그 '아파트 관제 프론트엔드 실제 호스팅/배포' 완료.**

## 9차 세션 추가 완료 (2026-07-28) — 하드웨어 병합분 검수·수정
- **HTML 엔티티 오염 복구**: 파트너가 푸시한 `esp32_grid/ess/relay.ino` + `setup.sh`에
  `&lt;` `&gt;` `&amp;`가 문자 그대로 들어가 컴파일·실행 불가였던 것 전부 복구.
- **릴레이 MQTT 토픽 불일치 수정**: 백엔드 `publisher.py`가 `peakbridge/control/relay`로
  발행하던 것을 하드웨어·README 기준인 `peakbridge/{building_id}/control/relay`로 통일.
- **ESP32 임계치 동기화 경로 구축**:
  - `GET /control/{id}/settings` 신설 (ESP32가 부팅 시 폴링하던 미존재 주소 → 실제 구현)
  - `PUT /control/{id}/threshold` 시 `peakbridge/{id}/config` 토픽으로 자동 전파
    (`publisher.publish_config` 신설) — 응답에 `mqtt_sent` 필드 추가
  - `esp32_grid.ino`: HTTPS(`WiFiClientSecure.setInsecure`) 적용, 응답 봉투
    (`data.threshold`) 파싱, `delay(5000)` 블로킹 제거(millis 타이머 — 피크 LED 점멸 정상화)
- **`peak_shaving_core.ino` → `esp32_peak_shaving.ino` 개명**: 아두이노 폴더=파일명 규칙
  위반으로 컴파일 자체가 안 열리던 문제.
- **검증**: 4개 스케치 전부 arduino-cli 컴파일 통과 (esp32:esp32:esp32, 코어 3.3.11).
  백엔드 수정 파일 py_compile 통과. 프론트는 threshold PUT 응답을 파싱하지 않아 무영향.
  프로덕션 MQTT 미연결 상태에선 `mqtt_sent: false`로만 응답 (기존 동작 보존).

## 10차 세션 추가 완료 (2026-07-28) — 하드웨어 실기기 연동 대비 견고화
- **Wi-Fi 유실 복구 (grid/ess/relay 3종, `5495ebfa`)**: 운영 중 Wi-Fi가 끊기면
  MQTT `reconnect()` 무한 루프에 갇혀 영영 복구 불가였던 구조 수정 —
  `loop()`에서 Wi-Fi 상태 확인 후 재수립, `reconnect()`는 Wi-Fi 유실 시 즉시 반환.
  ess/relay의 `setupWiFi`도 grid와 동일하게 10회 시도 후 `ESP.restart()`로 통일.
- **esp32_ess 견고성**: `ina219.begin()` 실패 시 정지(센서 미연결 상태로 SOC 0%
  계속 발행하던 것 차단) + `Serial.begin` 추가 (relay에도) — 현장 디버깅 가능.
- **grid 폴백 임계치**: 서버(/settings) 폴링 실패 시 15.0A → 0.1A(실측 CT 스케일).
  정상 경로에선 부팅 시 서버값으로 덮어써지므로 동작 변화 없음.
- **peak_shaving 주석 정정**: INA_LOW_mA "500mA 임시" 낡은 문구 → 실측 710mA 반영.
- **검증**: 4개 스케치 전부 arduino-cli 컴파일 통과 (esp32:esp32:esp32).
  백엔드·프론트 무변경 — 시연 각본 영향 없음.
- **하드웨어 리뷰 참고사항**: relay의 `control/relay/ack` 발행은 백엔드가 구독하지
  않음(의도적 방치 — 시연 시 `mosquitto_sub`로 육안 확인 용도로 충분).
  실측 스케일 ~0.08A는 백엔드 이상치 필터 물리 범위(0~200A) 안이라 통과 확인.
- **환경**: `shain1912/esp32-skills` 스킬 저장소 최신화 —
  `xiao-esp32s3-mqtt-dashboard`(멀티보드 MQTT 대시보드) 신규 설치, 기존 4종은 동일.

### 10차 세션 후반 — 파트너 실증 데모 병합분 전체 검수 (`e950ef21`~)
- **파트너 작업 검수 완료**: `hardware/server`(FastAPI :8010 + SQLite + MQTT 게이트웨이
  + 구성B 어댑터 + 클라우드 브리지) + `hardware/dashboard`(React :5181) + 문서 3종
  (README_LOCAL_DEMO / FIRMWARE_MQTT_SPEC / HARDWARE_BUILD_PLAN). 코드 품질 양호,
  기존 backend/frontend 무수정 원칙 준수 확인.
- **자동 검증 5종 재현 통과 (42/42)**: verify_local 13 / verify_mqtt 4 / verify_legacy 8
  / verify_ina 8 / verify_bridge 9. 대시보드 tsc+vite 빌드, 서버 py 컴파일,
  frontend 디자인 변경분 tsc 전부 통과.
- **⚠️ Windows 개발환경 주의**: 이 노트북에서 `python` 명령은 MS Store 스텁(무동작) —
  반드시 `py` 런처 사용. verify 스크립트는 한글 출력 때문에 `PYTHONUTF8=1` 필요:
  `PYTHONUTF8=1 py verify_local.py`
- **프로덕션 임계치 참고**: `/control/building-A/settings`가 10.0을 반환 중이었음 —
  과거 슬라이더 설정의 in-memory 잔존값. 재배포 시 env(`PEAK_THRESHOLD_A=0.08`)로
  초기화되므로 정상. **시연 직전 이 값이 0.08인지 반드시 확인할 것.**
- 대시보드 `package-lock.json` 커밋(재현 빌드), `*.tsbuildinfo` ignore 추가,
  `AI_BENCHMARK_REPORT.md`(모델 3종 벤치마크) 저장소에 편입.

## 11차 세션 추가 완료 (2026-07-29) — 실기 하드웨어 벤치 검증 (XIAO ESP32S3 리그)
- **리그 전환**: ESP32 DevKitC+INA226 → **XIAO ESP32S3 + INA219** 구성으로 실기 조립.
  신규 스케치 `hardware/xiao_peak_shaving/xiao_peak_shaving.ino` (기존 esp32_peak_shaving은
  DevKitC용으로 보존). 핀: CT=D0(GPIO1), 릴레이=D1(GPIO2), I2C SDA=D4(GPIO5)/SCL=D5(GPIO6).
- **전체 시나리오 실기 검증 통과**: 부하1·2(CT 0.073A, NC 유지) → 부하3 ON(0.108A →
  절체 NC→NO, 절체 후 CT 0.073A로 하락 = 물리 이관 증거) → 공급 안정(오판 복귀 0회)
  → 부하3 OFF(INA 1302→667mA → 복귀 NO→NC) → NC 안정 유지(재절체 왕복 없음).
  CT 노이즈 스파이크 1회를 연속 2회 조건이 정확히 걸러내는 것까지 확인.
- **실측 확정값 (INA219 리그)**: 노이즈 플로어 CT 0.008A / 부하1·2 0.073A /
  인버터 대기 ~690mA(650~733) / ESS 공급 ~1320mA(1260~1384).
  임계값 확정: I_HIGH=0.090A(절체), **INA_LOW=850mA(복귀)** — 양쪽 여유 117/410mA.
- **해결한 하드웨어 이슈 4건**:
  1. INA219 리플 ±300mA → 읽기당 25회×8ms 평균으로 안정화 (INA226의 하드웨어 평균 대체)
  2. 절체 직후 인버터 램프(2~3초 저전류)를 "부하3 꺼짐"으로 오판 → 절체/복귀 후
     10초 안정화 유예(STABILIZE_MS) 도입
  3. **릴레이 역결선으로 인버터→한전 역류** (부하 전부 OFF인데 CT 0.1A대·INA 요동
     — COM/NC/NO 재결선으로 해결. 결선: COM=부하3, NC=한전, NO=인버터)
  4. XIAO 시리얼 읽기 후 보드가 리셋에 갇히는 문제 — 포트 열 때 DTR만 assert(RTS 금지),
     닫기 전 esptool식 리셋 시퀀스 필요 (스크립트로 해결, 증상: ROM 배너만 출력)
- **XIAO 개발 참고**: FQBN `esp32:esp32:XIAO_ESP32S3`, 포트 COM11(ESP32 Family Device로
  표시), 네이티브 USB CDC라 `Serial.begin` 후 3초 대기 없으면 초기 출력 유실.
- **MQTT 전송 계층 완료 + 실기 엔드투엔드 개통** (같은 날 후반):
  - `xiao_peak_shaving`에 FIRMWARE_MQTT_SPEC.md 스펙 그대로 구현 — telemetry 발행(1초,
    QoS0), retained config 구독(QoS1)·검증·적용, 판단 우선 원칙(통신 전멸해도 절체·복귀
    단독 동작, 실기 확인). 시리얼에 `[MQTT O/X]` 상태 표시.
  - **전 구간 실증**: 센서 → ESP32 → Wi-Fi(폰 핫스팟) → mosquitto → `hardware/server`
    게이트웨이 → SQLite → `/api/latest` 실데이터 확인. config 라운드트립도 증명
    (서버 PUT ina_low=900 → ESP32 "config 적용" 즉시 출력 → 850 복원).
  - 서버 config의 `ina_low_ma` 시드 710은 구 리그 값 — **실측 850으로 PUT 갱신함**
    (in-memory 아닌 SQLite라 유지되지만, DB 초기화 시 시드 710로 돌아가니 주의).
  - **현장 함정 3건 기록**:
    1. **폰 핫스팟은 반드시 2.4GHz 대역으로** — ESP32는 5GHz 미지원, 기본값이 5GHz인
       폰이 많음 (이번에 Wi-Fi 미연결 원인이 정확히 이것)
    2. **Windows mosquitto는 설치 시 서비스로 자동 기동** (127.0.0.1 전용) — 수동 브로커와
       이중 기동되면 ESP32와 서버가 서로 다른 브로커에 붙는 분단 발생. 서비스 중지
       (`Stop-Service mosquitto`) 후 0.0.0.0 리스너 설정으로 단일 기동할 것
    3. **S3 CDC 블로킹**: PC가 시리얼을 안 읽으면 Serial.print가 막혀 MQTT 킵얼라이브를
       놓치고 재접속 반복 → `Serial.setTxTimeoutMs(0)` 필수
  - Wi-Fi SSID/PW·브로커 IP는 저장소에 플레이스홀더로만 커밋 (실값은 현장에서 기입,
    git 커밋 금지 — 기존 원칙 유지)
- **남은 것**: 배터리 전압 분배회로(1000Ω+100Ω, 배율 11.0)와 충전 LED는
  DevKitC판(esp32_peak_shaving)에 구현돼 있음 — XIAO판에 필요 시 이식.
  합숙 때는 브로커·서버를 라즈베리파이로 옮기고 IP만 바꾸면 됨 (이미 검증된 구성).

## 12차 세션 (2026-07-29) — 아파트 관제 실측 스케일 정렬 + AI 시연 폐루프 (실기 검증)

**목표**: 기존 배포 아파트 관제 시스템(`/app`)을 실증 하드웨어와 연동하고, "AI가
하드웨어를 제어한다"를 과장 없이 사실로 만드는 예측→선제대응 폐루프 구현.

### 실측 스케일 정렬 (`7ec2d8c6`)
- 대시보드 전류 표시·임계치 슬라이더·예측을 실측 스케일(0.0x A)로 정렬.
  컨트롤 임계치 슬라이더 10~30A → **0.02~0.20A**(step 0.005), 소수 3자리 표기.
- 예측 카드 필드명 버그 수정: `predicted`→`predicted_current` (항상 0으로 보이던 것 해소).
- ⚠️ **프론트 빌드는 반드시 PowerShell로** (`90216773` 흰화면 수정): Git Bash가
  `--base=/app/`을 `/Program Files/Git/app/`로 경로 변환(MSYS mangling)해 asset 링크가
  깨져 흰 화면. PowerShell에서 `npx vite build --base=/app/` 하면 정상.

### AI 시연 폐루프 A/B/C/D (`83db1024`, `5efdfe45`) — 전부 실기 검증 통과
- **A. 실측 반응 예측**: dashboard.py가 예측을 **명시적 시간대 배율**로 구성.
  XGBoost는 합성 학습이라 lag가 더미 고정(10)이라 시간대 반응이 거의 없음 → 재학습
  전까지 `기저부하(실측/현재시각배율) × 예측시각배율`로 예측. 부하 상승·시각 이동 둘 다 반응.
  시간대 배율: 18~21시 1.6 / 11~13·17시 1.3 / 23~6시 0.6 / 그 외 1.0.
- **B. 다음 피크 예상**: 응답에 `next_peak{time, predicted_current, minutes_ahead}` 추가.
  대시보드 상단 `AiForecastPanel`에 배지.
- **C. 데모 가상 시각**: `POST /control/{id}/demo-time {hour}` (관리자 인증). 예측만 영향,
  실제 판정·제어는 실시간 유지. **주의: in-memory라 Railway 재배포 시 실시간으로 리셋됨.**
- **D. 하드웨어 오토파일럿** (`hardware/server/autopilot.py`, `AUTOPILOT=1`+`BRIDGE_URL`):
  Railway AI 예측(next_peak) 폴링 → 하드웨어 임계치를 실측×0.9로 선제 하향 → MQTT config →
  XIAO 자율 절체. **릴레이 직접 제어 아님, config만 조정** (통신 끊겨도 안전). 노이즈
  채터링 방지 디바운스(연속 2회 발동 / 3회 복원).
- **실기 검증 (실측 로그)**: 데모19시 → AI 예측 0.089~0.096A → 오토파일럿 발동 →
  HW임계 **0.09→0.0668 자동 하향** → 부하3 ON → 절체 → INA 1300~1450mA 공급 →
  **NO 안정 55초 채터링 0회**.

### ⚠️ 확인된 물리 특성 (시연 각본 핵심)
- **"부하3 없이 AI만으로 선제 절체"는 이 하드웨어에선 불가능**. 임계만 낮춰 절체해도
  부하3이 꺼져 있으면 인버터 무부하(INA ~690<850) → 즉시 복귀 → 채터링. 릴레이는
  부하3만 ESS로 넘길 수 있고, 부하3이 실제 켜져야 INA가 공급을 감지해 절체가 유지됨.
- 따라서 올바른 각본 = "AI 예측 → 임계 **선제 강화**(하향) → 실제 부하3 발생 시 낮아진
  임계로 즉각 대응". 임계 하향(숫자 변화)이 AI 제어 증거, 부하3으로 실제 절체 시연.

## 🎬 하드웨어 실증 시연 각본 (12차 확정 — AI 폐루프)

**사전 세팅** (합숙/시연 현장):
1. 노트북(또는 파이): mosquitto 단일 기동(0.0.0.0:1883), `hardware/server`를
   `MQTT_BROKER=localhost BRIDGE_URL=https://peakbridge-production.up.railway.app AUTOPILOT=1`로 기동
2. 폰/공유기 핫스팟 **2.4GHz**, XIAO 펌웨어에 SSID/PW/브로커IP 기입 후 플래시
3. Railway 프로덕션 임계치 `PEAK_THRESHOLD_A=0.08` 확인 (재배포 시 초기화)
4. 배터리·인버터 ON → 부하1·2 ON (부하3은 아직 OFF)

**시연 흐름** (아파트 관제 `/app` + 로컬 대시보드 `:8010` 두 화면):
1. 평상시: 실물 CT 0.073A가 클라우드 대시보드에 실시간 표시, 예측선 평온, 임계 0.09
2. **AI 예측 발동**: 대시보드 "AI 피크 예측" 패널의 시각 슬라이더를 **19시**로 →
   예측선 0.09A로 상승 → **"⚠️ N분 뒤 피크 예상" 배지** 점등
3. **선제 대응**: 오토파일럿이 하드웨어 임계를 **0.09→0.067로 자동 하향**
   (로컬 대시보드/헬스에서 임계 변화 확인)
4. **실제 절체**: 부하3 ON → CT 0.108A → 낮아진 임계로 즉각 절체 → 로컬 배너 파랑→주황,
   클라우드 전류 반응, INA 1320mA 공급 → 안정 유지
5. 마무리 멘트: *"AI가 저녁 피크를 예측 → 하드웨어 안전 임계를 선제 강화 → 실제 부하
   증가 시 하드웨어가 자율 절체. 릴레이를 원격에서 흔드는 게 아니라 예측으로 임계를
   조정하는 산업적으로 올바른 방식."*

**리허설 반복**: 슬라이더 "실시간 복원" → 임계 자동 원복 → 부하3 OFF → 1번으로.
**정직 포인트**: XGBoost는 합성 학습이라 지금은 시간대 배율로 예측 구성 — 이 하드웨어로
실데이터가 쌓이면 실측 재학습이 다음 단계 (과장 없이 이렇게 답하면 방어력이 높음).

## 남은 백로그 (의도적 미구현 — 필요성 낮음)
- C2 WebSocket 전환 (3초 폴링으로 시연 충분)
- 정식 JWT 콘솔 로그인 (시연 마찰 증가)
- D1 타임랩스 연출 (60× 가속으로 대체됨)

## 리허설 루틴 (권장)
[리셋] → [원클릭 데모] → 급전 이행 관찰 → 운영 센터(알람 ACK) →
정산 원장(플랫폼 매출) → 입찰 데스크 RT 즉시판매 → 다시 [리셋]

## 주의사항
- 시장/이행/원장은 in-memory — 서버 재배포 시 초기화됨 (시연 직전 재현 필요)
- ppo_service의 이전 SB3 코드는 numpy 로더로 교체됨 — SB3/torch 설치 금지 (배포 무거워짐)
- 시연용 부하 임계치: Railway env PEAK_THRESHOLD_A=0.08 (의도된 값 — 실제 하드웨어 CT에
  ~0.08A 수준이 흐르므로 실측 스케일로 잡고, 아파트 대시보드에서는 배수 환산으로 실증)
- frontend-vpp는 npm install 필요 (topojson-client 등)
- git push 후 Railway 자동배포 2~3분, /docs에서 market·dispatch 태그 확인
- 하드웨어 미제작 상태 — MQTT 브로커 미연결, ESP32 등 실기기 연동은 추후 작업
- 저장소 루트의 `railway-deploy`는 깨진 git submodule 참조(빈 디렉토리) — 정리 대상,
  실제 배포와 무관
