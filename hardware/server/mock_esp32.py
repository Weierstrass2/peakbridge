"""모의 ESP32 — 합숙 전 유일한 통합 검증 수단.

실기 테스트가 합숙 1일차에 처음 이루어지므로, 이 스크립트가 인터페이스 스펙과
1:1로 정확히 일치해야 한다. FastAPI에 의존하지 않는 독립 스크립트다.

실행:
    python mock_esp32.py                        # HTTP 모드 (기본 http://localhost:8010)
    python mock_esp32.py --url http://192.168.0.10:8010
    python mock_esp32.py --mqtt localhost       # MQTT 모드

절체 판단은 **로컬 히스테리시스**로 이루어진다 (서버 개입 없음 — 실기기와 동일 철학).
서버 연결이 끊겨도 마지막 config로 계속 동작하며 경고 로그만 남긴다.

── A-2 교정 시나리오 (하드웨어 담당이 물리적으로 교정한 시퀀스) ──────────────
 1. 부하1만 ON                     ~0.036A   NC
 2. 부하2 ON                       ~0.072A   NC
 3. 부하3 ON → I_high(0.09) 초과    0.108A → 절체 후 0.072A로 하락   NC→NO, hold 30s
 4. hold 만료 후에도 0.072 > I_low(0.055) → 복귀하지 않음 (히스테리시스 증명 구간)
 5. 부하1 OFF → 0.036 < I_low      복귀 후 0.072A로 상승 (부하3이 한전으로 복귀)  NO→NC
 6. 부하 초기화 후 1단계로 루프

주의: 구 시나리오("hold 만료 후 자동 복귀")는 물리적으로 틀렸음이 확인되어 폐기되었다.
      절대 되살리지 말 것.
"""

import argparse
import json
import logging
import random
import sys
import time
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [mock] %(message)s")
logger = logging.getLogger("mock_esp32")

DEVICE_ID = "ess-demo-01"  # 하드웨어 담당 확정 — 변경 금지

LOAD_CURRENT_A = 0.036  # 부하 1개당 전류
NOISE_A = 0.002  # ±0.002A 지터 (실측 느낌)

TOPIC_TELEMETRY = "peakbridge/demo/telemetry"
TOPIC_CONFIG = "peakbridge/demo/config"

# 펌웨어 기본값 (서버와 통신 전에도 단독 동작 가능해야 함)
DEFAULT_CONFIG = {"threshold_high_a": 0.09, "threshold_low_a": 0.055, "min_hold_s": 30, "ina_low_ma": 710.0}

# INA226 실측값 (peak_shaving_core.ino 주석 기준)
INA_STANDBY_MA = 626.0  # 부하3 꺼짐 = 인버터 대기 전류
INA_SUPPLY_MA = 800.0   # 부하3 켜짐 = ESS 공급 중
INA_NOISE_MA = 8.0

# 복귀 판단 방식
#   "ct"  = v3 계획서(CT 히스테리시스 + 최소 유지시간). INA226이 없을 때의 폴백.
#   "ina" = 실기 펌웨어 peak_shaving_core.ino와 동일. INA226 전류가 ina_low_ma 아래로
#           연속 2회 떨어지면 복귀. CT는 절체(NC→NO) 판단만 담당한다.
RETURN_MODE = "ct"
CONSEC_REQUIRED = 2

# 시나리오 타임라인 (사이클 내 경과초 → 켜져 있는 부하 집합)
CYCLE_S = 75
SCHEDULE = [
    (0, {1}),  # 1단계: 기준선
    (5, {1, 2}),  # 2단계
    (10, {1, 2, 3}),  # 3단계: I_high 초과 → 절체
    # 4단계: 10+30=40초에 hold 만료, 그러나 0.072 > I_low 라 복귀하지 않음 (~20초 유지)
    (60, {2, 3}),  # 5단계: 부하1 OFF → 복귀 → 전류 상승
    # 6단계: 사이클 끝(75초)에서 1단계로 초기화
]

# INA 모드용 타임라인.
# 실기 펌웨어는 INA226(배터리→인버터 전류)으로 복귀를 판단하므로, 복귀 트리거가
# "부하1 OFF"가 아니라 **부하3 OFF**(인버터가 대기 전류로 떨어짐)다.
SCHEDULE_INA = [
    (0, {1}),
    (5, {1, 2}),
    (10, {1, 2, 3}),   # CT 초과 → 절체 (부하3이 ESS로)
    (60, {1, 2}),      # 부하3 OFF → INA 대기 수준으로 하락 → 연속 2회 미달 시 복귀
]


def validate_config(cfg: dict) -> str | None:
    """펌웨어 내장 검증 — 서버 models.validate_config와 동일 규칙.

    실기 ESP32도 자체 검증을 갖고 있으므로, 여기서도 독립적으로 구현한다.
    (서버 코드를 import하지 않는 것이 실기기와 동일한 구조)
    """
    try:
        high = float(cfg["threshold_high_a"])
        low = float(cfg["threshold_low_a"])
        hold = int(cfg["min_hold_s"])
    except (KeyError, TypeError, ValueError):
        return "config 필드 누락 또는 형식 오류"
    if low <= 0:
        return f"I_low는 0보다 커야 함 (입력 {low})"
    if high <= low:
        return f"I_high > I_low 위반 (입력 high={high}, low={low})"
    if hold < 5 or hold > 300:
        return f"min_hold_s는 5~300초 (입력 {hold})"
    ina = cfg.get("ina_low_ma")
    if ina is not None:
        try:
            ina = float(ina)
        except (TypeError, ValueError):
            return "ina_low_ma 형식 오류"
        if not (50.0 <= ina <= 8200.0):
            return f"ina_low_ma는 50~8200mA (입력 {ina})"
    return None


# 시나리오 시간축 배속 (1.0 = 실제 속도). 자동 검증에서만 <1.0로 줄여 쓴다.
# 시연에서는 항상 1.0을 사용할 것.
SCALE = 1.0
SAMPLE_INTERVAL_S = 1.0  # 샘플 주기 (1Hz)


def loads_at(elapsed: float) -> set:
    """사이클 경과초에 해당하는 부하 집합."""
    schedule = SCHEDULE_INA if RETURN_MODE == "ina" else SCHEDULE
    current = schedule[0][1]
    for at, loads in schedule:
        if elapsed >= at * SCALE:
            current = loads
    return current


class MockDevice:
    def __init__(self) -> None:
        self.relay_state = "NC"
        self.hold_until_ts = 0.0
        self.config = dict(DEFAULT_CONFIG)
        self.started = time.time()
        self.over_count = 0   # CT 연속 초과 횟수 (절체용)
        self.under_count = 0  # INA 연속 미달 횟수 (복귀용)

    def grid_current(self, loads: set) -> float:
        """한전 계통으로 흐르는 전류.

        relay가 NO(피크)면 부하3은 ESS가 공급하므로 계통 전류에서 빠진다.
        """
        on_grid = set(loads)
        if self.relay_state == "NO":
            on_grid.discard(3)
        base = len(on_grid) * LOAD_CURRENT_A
        return max(0.0, base + random.uniform(-NOISE_A, NOISE_A))

    def ina_current(self, loads: set) -> float:
        """INA226이 보는 배터리→인버터 전류(mA).

        릴레이가 NO이고 부하3이 켜져 있을 때만 '공급' 수준(~800mA),
        그 외에는 인버터 '대기' 수준(~626mA). 이 구분이 복귀 판단의 근거다.
        """
        supplying = self.relay_state == "NO" and 3 in loads
        base = INA_SUPPLY_MA if supplying else INA_STANDBY_MA
        return max(0.0, base + random.uniform(-INA_NOISE_MA, INA_NOISE_MA))

    def step(self) -> dict:
        """1Hz 샘플 1회: 전류 측정 → 로컬 히스테리시스 판정 → 페이로드 생성."""
        now = time.time()
        elapsed = (now - self.started) % (CYCLE_S * SCALE)
        loads = loads_at(elapsed)

        current = self.grid_current(loads)
        high = self.config["threshold_high_a"]
        low = self.config["threshold_low_a"]
        hold_s = self.config["min_hold_s"]

        ina_ma = self.ina_current(loads)
        ina_low = float(self.config.get("ina_low_ma", 710.0))

        if self.relay_state == "NC":
            # 절체 판단은 두 방식 모두 CT가 담당한다 (연속 2회 초과 — 노이즈 방지)
            if current > high:
                self.over_count += 1
                if self.over_count >= CONSEC_REQUIRED or RETURN_MODE == "ct":
                    self.relay_state = "NO"
                    self.hold_until_ts = now + hold_s
                    self.over_count = 0
                    self.under_count = 0
                    logger.info("절체 NC→NO (CT %.4fA > I_high %.4fA)", current, high)
            else:
                self.over_count = 0
        else:  # NO
            if RETURN_MODE == "ina":
                # 실기 펌웨어와 동일: INA226 전류가 대기 수준으로 연속 2회 떨어지면 복귀
                if ina_ma < ina_low:
                    self.under_count += 1
                    if self.under_count >= CONSEC_REQUIRED:
                        self.relay_state = "NC"
                        self.hold_until_ts = 0.0
                        self.under_count = 0
                        logger.info("복귀 NO→NC (INA %.1fmA < %.1fmA)", ina_ma, ina_low)
                else:
                    self.under_count = 0
            else:
                # v3 계획서: CT 히스테리시스 + 최소 유지시간
                if now >= self.hold_until_ts and current < low:
                    self.relay_state = "NC"
                    self.hold_until_ts = 0.0
                    logger.info("복귀 NO→NC (CT %.4fA < I_low %.4fA)", current, low)

        hold_remaining = max(0, int(round(self.hold_until_ts - now))) if self.hold_until_ts else 0

        # timestamp: 실기기는 NTP 미동기 시 0으로 보낸다. 여기서는 동기된 상황을 가정.
        return {
            "device_id": DEVICE_ID,
            "timestamp": int(now),
            "grid_current_a": round(current, 4),
            "relay_state": self.relay_state,
            "threshold_high_a": high,
            "threshold_low_a": low,
            "hold_remaining_s": hold_remaining,
            "battery_voltage_v": None,
            "ess_current_a": None,
            "ess_power_w": None,
            "ina_current_ma": round(ina_ma, 1),
        }

    def apply_config(self, cfg: dict, source: str) -> None:
        reason = validate_config(cfg)
        if reason:
            logger.warning("서버 config 거부 (%s): %s", source, reason)
            return
        new = {
            "threshold_high_a": float(cfg["threshold_high_a"]),
            "threshold_low_a": float(cfg["threshold_low_a"]),
            "min_hold_s": int(cfg["min_hold_s"]),
            "ina_low_ma": float(cfg.get("ina_low_ma", self.config.get("ina_low_ma", 710.0))),
        }
        if new != self.config:
            logger.info("config 갱신 (%s): %s → %s", source, self.config, new)
            self.config = new


def run_http(device: MockDevice, url: str) -> None:
    endpoint = f"{url.rstrip('/')}/api/telemetry"
    logger.info("HTTP 모드 시작 → %s", endpoint)
    while True:
        payload = device.step()
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            # 응답 body의 config로 매 루프 갱신 — 별도 폴링 없는 HTTP 폴백 경로
            if isinstance(body, dict) and body.get("config"):
                device.apply_config(body["config"], "HTTP 응답")
        except urllib.error.HTTPError as exc:
            logger.warning("서버 응답 오류 %s — 마지막 config로 계속", exc.code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("서버 전송 실패 (%s) — 마지막 config로 계속", exc)
        time.sleep(SAMPLE_INTERVAL_S)


def run_mqtt(device: MockDevice, broker: str, port: int) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.error("paho-mqtt가 필요합니다: pip install paho-mqtt")
        sys.exit(1)

    def on_connect(client, userdata, flags, rc, *args):
        logger.info("브로커 접속 (rc=%s) — config 구독", rc)
        client.subscribe(TOPIC_CONFIG, qos=1)

    def on_message(client, userdata, msg):
        try:
            cfg = json.loads(msg.payload.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("config 파싱 실패: %s", exc)
            return
        device.apply_config(cfg, "MQTT retained")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(broker, port, keepalive=60)
    client.loop_start()
    logger.info("MQTT 모드 시작 → %s:%s", broker, port)

    while True:
        payload = device.step()
        try:
            client.publish(TOPIC_TELEMETRY, json.dumps(payload), qos=0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("발행 실패 (%s) — 계속", exc)
        time.sleep(SAMPLE_INTERVAL_S)


def main() -> None:
    parser = argparse.ArgumentParser(description="모의 ESP32 (A-2 교정 시나리오)")
    parser.add_argument("--url", default="http://localhost:8010", help="HTTP 서버 주소")
    parser.add_argument("--mqtt", default=None, help="MQTT 브로커 주소 (지정 시 MQTT 모드)")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="시나리오 시간축 배속 (검증 자동화 전용, 시연에서는 1.0)",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="샘플 주기(초), 기본 1Hz")
    parser.add_argument(
        "--return-mode",
        choices=["ct", "ina"],
        default="ct",
        help="복귀 판단: ct=v3 계획서(히스테리시스+hold), ina=실기 펌웨어(INA226 연속 2회 미달)",
    )
    args = parser.parse_args()

    global SCALE, SAMPLE_INTERVAL_S, RETURN_MODE
    SCALE = args.scale
    SAMPLE_INTERVAL_S = args.interval
    RETURN_MODE = args.return_mode
    logger.info("복귀 판단 방식: %s", RETURN_MODE)

    device = MockDevice()
    if args.mqtt:
        run_mqtt(device, args.mqtt, args.mqtt_port)
    else:
        run_http(device, args.url)


if __name__ == "__main__":
    main()
