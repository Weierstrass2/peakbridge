# PeakBridge 인수인계 (2026-07-12 기준)

## 현재 상태 — 완료된 것

### 아파트 관제 (frontend/) — 완성, 배포됨
전 페이지 실데이터 연결, ESS 1대 구성, 타입에러 0.

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

## 남은 백로그 (우선순위순)
1. A1+d 실시간 시장(15분 세션) + A4 월 정산서
2. B1 알람 센터(ACK 큐) + B2 이행 리스크 모니터(SOC vs 낙찰의무 사전경고) + B4 감사로그
3. D1 하루 타임랩스 플레이어 (시연 필살기)
4. C3 콘솔 실배포(Railway static/Vercel) + B3 운영자 로그인
5. A5 계약 관리 + C1 시계열 서버 저장 + C2 WebSocket 전환

## 주의사항
- 시장/이행/원장은 in-memory — 서버 재배포 시 초기화됨 (시연 직전 재현 필요)
- ppo_service의 이전 SB3 코드는 numpy 로더로 교체됨 — SB3/torch 설치 금지 (배포 무거워짐)
- 시연용 부하 임계치: Railway env PEAK_THRESHOLD_A=0.5
- frontend-vpp는 npm install 필요 (topojson-client 등)
- git push 후 Railway 자동배포 2~3분, /docs에서 market·dispatch 태그 확인
