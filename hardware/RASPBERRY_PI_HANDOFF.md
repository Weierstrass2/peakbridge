# 라즈베리파이 4 연동 인수인계 (시연 전 정리)

> **목적**: 지금까지 노트북(Windows)에서 검증 완료한 하드웨어 실증 구성을,
> 시연용으로 **라즈베리파이 4 Model B**로 이관하기 위한 계획서.
> 핫스팟(폰 2.4GHz) 환경에서 시연 예정.
>
> **핵심 원칙**: 파이는 지금 노트북이 하던 **① mosquitto 브로커 + ② hardware/server**
> 역할을 대신할 뿐이다. **코드 변경 없음, IP 재설정 위주** 작업.

---

## 1. 지금까지 완료된 것 (실기 검증 끝)

### 하드웨어 리그 (XIAO ESP32S3, 11~16차 세션 검증)
- **구성**: XIAO ESP32S3 + INA219(전류) + CT센서(계통) + SPDT 릴레이 + BME280 x2(온도)
- **메인 보드** `hardware/xiao_peak_shaving/xiao_peak_shaving.ino`
  - CT로 계통 전류 측정 → 임계 초과 시 **로컬 판단으로 절체**(한전 NC ↔ 인버터 NO)
  - INA219로 ESS 방전 전류/SOC 측정
  - 열 차단(과열 50°C 트립 / 43°C 해제), 강제 방전 모드, SOC 리셋 command 지원
  - **판단은 항상 로컬** — 서버가 릴레이를 직접 흔들지 않음(통신 끊겨도 안전)
- **온도 보드** `hardware/xiao_sense_bme280/xiao_sense_bme280.ino`
  - BME280 2개(배터리 옆·인버터 옆) 온·습도 → MQTT 발행
  - 두 보드 사이 전선 없음 — **오직 MQTT로만 연동**
- **핀맵**: CT=D0(GPIO1), 릴레이=D1(GPIO2), I2C SDA=D4(GPIO5)/SCL=D5(GPIO6)
- **결선(중요)**: COM=부하3, NC=한전, NO=인버터 (SPDT라 역류 불가)

### 실측 확정값 (INA219 리그)
| 항목 | 값 |
|---|---|
| 노이즈 플로어 CT | 0.008A |
| 부하1·2 | 0.073A |
| 인버터 대기(무부하) | ~690mA |
| ESS 공급 | ~1320mA |
| **절체 임계 I_HIGH** | **0.090A** |
| **복귀 임계 INA_LOW** | **850mA** |

### 소프트웨어 파이프라인 (엔드투엔드 개통 검증)
```
XIAO ESP32S3 ─MQTT─> mosquitto ─> hardware/server(FastAPI :8010)
                                    ├─ SQLite (로컬 보존)
                                    ├─ dashboard/dist (로컬 대시보드 :8010)
                                    └─ bridge.py ─HTTP─> Railway 클라우드 /app
                                                          + SMP 당일가 자동 주입
```
- `hardware/server`: 텔레메트리 수신 → SQLite 저장 → 이벤트 감지 → 클라우드 브리지
- **AUTOPILOT**: Railway AI 예측(next_peak) 폴링 → 하드웨어 임계 선제 하향 → MQTT config
  → XIAO 자율 절체 (릴레이 직접 제어 아님, config만 조정)
- **SMP 중계**: KPX 웹 당일 확정가를 6시간 주기로 긁어 클라우드에 주입(한국 IP 우회)

### 검증 현황
- 절체·복귀·강제방전·열차단 전 시나리오 실기 통과
- MQTT 엔드투엔드(센서→ESP32→브로커→서버→SQLite→클라우드) 개통
- config 라운드트립(서버 PUT → ESP32 즉시 적용) 증명
- 자동 검증 스크립트 5종 통과 (verify_local/mqtt/legacy/ina/bridge/thermal)

---

## 2. 파이가 해야 할 일 (노트북 → 파이 이관)

지금 **노트북에서 돌던 이 두 개를 파이로 옮긴다**:

| 옮길 대상 | 현재(노트북) | 파이에서 |
|---|---|---|
| ① mosquitto 브로커 | Windows 서비스 | `apt install mosquitto` → 1883 포트 |
| ② hardware/server | uvicorn :8010 | 동일하게 uvicorn :8010 |

**바뀌는 것은 IP 하나뿐**: XIAO 펌웨어의 브로커 IP를 `노트북 IP` → `파이 IP`로.

시연 화면은 **클라우드 `/app` 위주**이므로, 파이에서 로컬 대시보드 dist 빌드는 생략 가능
(원하면 노트북에서 빌드해 복사 — 5절 참고).

---

## 3. 파이 세팅 단계 (시연 하루 전 체크리스트)

### 단계 0 — OS·네트워크
1. SD카드에 **Raspberry Pi OS (64-bit)** 굽기 (Raspberry Pi Imager).
   - Imager 고급설정에서 **호스트명 / SSH 활성화 / WiFi(핫스팟 SSID·PW, 2.4GHz)** 미리 입력하면 헤드리스 가능
2. **⚠️ 핫스팟은 반드시 2.4GHz** — ESP32는 5GHz 미지원 (지금까지 Wi-Fi 미연결 원인 대부분이 이것)
3. 파이를 핫스팟에 연결 → 파이 IP 확인: `hostname -I`
   - **핫스팟은 IP가 유동적**이므로, 파이 IP를 확인한 그 값을 XIAO 펌웨어에 넣는다
   - 가능하면 폰 핫스팟 설정에서 파이를 고정(기기별 IP 예약 지원 시)

### 단계 1 — mosquitto 브로커
```bash
sudo apt-get update
sudo apt-get install -y mosquitto mosquitto-clients
sudo tee /etc/mosquitto/conf.d/peakbridge.conf > /dev/null << 'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
sudo systemctl enable --now mosquitto
mosquitto_sub -h localhost -t 'peakbridge/#' -v   # 수신 확인용
```
> 기존 `hardware/raspberry_pi/setup.sh`도 있으나, 위 conf.d 방식이 최신 mosquitto에서 더 안전.

### 단계 2 — hardware/server (파이엔 Python만 필요)
```bash
# 코드 가져오기 (git clone 또는 hardware/ 폴더만 복사)
cd hardware/server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # fastapi, uvicorn, pydantic, paho-mqtt, requests
```

### 단계 3 — 서버 기동 (브로커·브리지·오토파일럿 함께)
```bash
cd hardware/server
MQTT_BROKER=localhost \
BRIDGE_URL=https://peakbridge-production.up.railway.app \
AUTOPILOT=1 \
python -m uvicorn main:app --host 0.0.0.0 --port 8010
```
- 브로커가 같은 파이에 있으므로 `MQTT_BROKER=localhost`
- `BRIDGE_URL` → 실물 전류가 클라우드 `/app`으로 흐르고 SMP 당일가 자동 주입
- `AUTOPILOT=1` → AI 예측→선제 임계 하향 폐루프 동작
- 로컬 대시보드(옵션): `http://<파이IP>:8010`

### 단계 4 — XIAO 펌웨어 IP만 교체 후 재플래시
- `xiao_peak_shaving.ino` + `xiao_sense_bme280.ino` 상단의
  **브로커 IP를 파이 IP로**, SSID/PW를 현장 2.4GHz 핫스팟 값으로 기입 후 재플래시
- **실값은 git 커밋 금지** (플레이스홀더 원칙 유지)

### 단계 5 — 스모크 테스트 → 실기 연결
```bash
# 모의 노드로 파이 단독 검증
python mock_esp32.py --mqtt localhost
mosquitto_sub -h localhost -t peakbridge/demo/config -v   # retained config 즉시 수신 확인
```
통과하면 실기 XIAO 전원 인가 → 서버 `/api/latest`에 실데이터 확인 → 부하3 ON으로 절체 시연.

---

## 4. 시연 직전 필수 확인 (문서 기록된 함정)

- [ ] **핫스팟 2.4GHz** 켜져 있는지 (5GHz면 XIAO Wi-Fi 미연결)
- [ ] Railway 환경변수 **`PEAK_THRESHOLD_A=0.08`** — 0.5면 피크 미인식
- [ ] `/control/building-A/settings`가 0.08 반환하는지 확인 (in-memory 잔존값 주의)
- [ ] 파이 **전원**: 파이4는 5V/3A 필요 — 약한 보조배터리는 ⚡저전압→시연 중 재부팅 위험
- [ ] **시연 중 XIAO/파이 리셋 금지** — 재부팅 시 릴레이 NC 순단으로 부하3 깜빡임
- [ ] 서버 config `ina_low_ma` = **850** (실측값, DB 초기화 시 시드 710로 돌아가니 주의)
- [ ] **노트북을 확실한 백업으로 살려둘 것** — 파이 안 되면 노트북 구성으로 즉시 대체

---

## 5. (옵션) 로컬 대시보드도 띄우려면
파이에서 npm 금지(느리고 실패 위험). **노트북에서 빌드 후 파이로 복사**:
```powershell
# 노트북(PowerShell)에서
cd hardware/dashboard; npm run build   # → dashboard/dist
```
`hardware/dashboard/dist`를 파이의 같은 경로로 복사하면, 서버가 `/`에 자동 마운트 →
`http://<파이IP>:8010`에서 로컬 대시보드 표시.

---

## 6. 🎬 시연 흐름 (12차 확정 각본, 파이 구성)

**사전 세팅**: 파이 mosquitto+server(BRIDGE_URL+AUTOPILOT) 기동, 핫스팟 2.4GHz,
XIAO에 파이 IP 기입·플래시, `PEAK_THRESHOLD_A=0.08` 확인, 부하1·2 ON(부하3 OFF)

1. **평상시**: CT 0.073A가 클라우드 `/app` 대시보드에 실시간 표시, 임계 0.09
2. **AI 예측 발동**: "AI 피크 예측" 패널 시각 슬라이더 → **19시** → 예측선 0.09A 상승 →
   "⚠️ N분 뒤 피크 예상" 배지 점등
3. **선제 대응**: 오토파일럿이 하드웨어 임계 **0.09→0.067 자동 하향**
4. **실제 절체**: 부하3 ON → CT 0.108A → 낮아진 임계로 즉각 절체 → 클라우드 전류 반응,
   INA 1320mA 공급 → 안정 유지
5. **마무리 멘트**: *"AI가 저녁 피크를 예측 → 하드웨어 안전 임계를 선제 강화 →
   실제 부하 증가 시 하드웨어가 자율 절체. 릴레이를 원격에서 흔드는 게 아니라
   예측으로 임계를 조정하는 산업적으로 올바른 방식."*

**정직 포인트**: XGBoost는 합성 학습이라 지금은 시간대 배율로 예측 구성 —
이 하드웨어로 실데이터가 쌓이면 실측 재학습이 다음 단계. 과장 없이 이렇게 답하면 방어력 높음.

---

## 7. 참고 문서
- `hardware/README_LOCAL_DEMO.md` — 로컬 폐쇄망 데모 상세(API·토픽·검증 규칙)
- `hardware/FIRMWARE_MQTT_SPEC.md` — 펌웨어 MQTT 스펙
- `hardware/raspberry_pi/setup.sh` — 브로커 설치 스크립트(기존)
- `PARTNER_HANDOFF.md` 11~16차 세션 — 실기 검증 전체 기록
