# PeakBridge 인수인계 (2026-07-21 기준)

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
