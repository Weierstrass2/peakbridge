"""3-노드 구성(팀원A 명세) → 로컬 데모 스키마 어댑터.

두 구성을 동시에 살리기 위한 흡수 계층이다.

  구성 A (v3 계획서):  ESP32 1대가 peakbridge/demo/telemetry 로 완결 페이로드 발행
  구성 B (팀원A):      ESP32 3대가 각각 다른 토픽으로 조각난 데이터 발행

구성 B의 토픽 (hardware/README.md 기준):
  peakbridge/building-A/grid/current      {"value":18.4,"unit":"A","device_id":..,"building_id":..}
  peakbridge/building-A/ess/soc           {"value":72.0,"unit":"%","voltage":3.45,"current":-2.3,...}
  peakbridge/building-A/control/relay/ack {"status":"ok","action":"discharge","device_id":..}

세 조각을 건물 단위 섀도우 상태로 합쳐 canonical 텔레메트리 1행으로 만든다.
저장은 HTTP·demo MQTT와 **동일한 save_telemetry 경로**를 그대로 쓴다.

릴레이 상태 매핑 (구성 B는 백엔드가 명령하고 relay 노드가 ack로 회신):
  discharge → NO (ESS 공급)
  charge / standby → NC (한전 공급)

주의: 구성 B는 전류 스케일이 실부하(수십 A)라 데모(0.09A)와 임계값이 다르다.
      LEGACY_THRESHOLD_HIGH_A / LEGACY_THRESHOLD_LOW_A 환경변수로 조정한다.
      (해당 값은 기록·차트 표시용이며, 구성 B의 절체 판단은 백엔드가 한다)
"""

import os
import threading
import time
from typing import Any, Callable

TOPIC_LEGACY_WILDCARD = "peakbridge/+/#"

# 기록·차트 표시용 임계값 (구성 B는 서버가 판단하지 않음)
LEGACY_THRESHOLD_HIGH_A = float(os.environ.get("LEGACY_THRESHOLD_HIGH_A", "20.0"))
LEGACY_THRESHOLD_LOW_A = float(os.environ.get("LEGACY_THRESHOLD_LOW_A", "15.0"))

_lock = threading.Lock()
# building_id → 섀도우 상태
_shadow: dict[str, dict[str, Any]] = {}

ACTION_TO_RELAY = {
    "discharge": "NO",
    "charge": "NC",
    "standby": "NC",
}


def parse_topic(topic: str) -> tuple[str, str] | None:
    """peakbridge/<building>/<나머지> → (building_id, kind). demo 네임스페이스는 제외."""
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != "peakbridge":
        return None
    building = parts[1]
    if building == "demo":
        return None  # 구성 A 전용 토픽 — 여기서 처리하지 않는다
    return building, "/".join(parts[2:])


def _shadow_for(building_id: str) -> dict[str, Any]:
    return _shadow.setdefault(
        building_id,
        {
            "grid_current_a": None,
            "relay_state": "NC",  # 릴레이 ack를 받기 전 기본값 = 한전 공급
            "battery_voltage_v": None,
            "ess_current_a": None,
            "ess_power_w": None,
            "soc_pct": None,
        },
    )


def handle(topic: str, payload: dict[str, Any], save: Callable[[dict], Any]) -> dict | None:
    """구성 B 메시지 1건 처리. canonical 행을 저장했으면 그 payload를 반환.

    - grid/current: 주기 데이터 → 즉시 1행 기록 (5초 간격 발행 가정)
    - ess/soc: 섀도우만 갱신 (다음 grid 샘플에 실려 나감)
    - control/relay/ack: 릴레이 상태 변화 → 즉시 1행 기록 (이벤트를 놓치지 않기 위해)
    """
    parsed = parse_topic(topic)
    if parsed is None:
        return None
    building_id, kind = parsed

    with _lock:
        shadow = _shadow_for(building_id)
        emit = False

        if kind == "grid/current":
            value = payload.get("value")
            if not isinstance(value, (int, float)):
                return None
            shadow["grid_current_a"] = float(value)
            emit = True

        elif kind == "ess/soc":
            voltage = payload.get("voltage")
            current = payload.get("current")
            shadow["soc_pct"] = payload.get("value")
            shadow["battery_voltage_v"] = float(voltage) if isinstance(voltage, (int, float)) else None
            shadow["ess_current_a"] = float(current) if isinstance(current, (int, float)) else None
            if shadow["battery_voltage_v"] is not None and shadow["ess_current_a"] is not None:
                shadow["ess_power_w"] = round(shadow["battery_voltage_v"] * shadow["ess_current_a"], 3)
            else:
                shadow["ess_power_w"] = None

        elif kind in ("control/relay/ack", "control/relay"):
            action = str(payload.get("action", "")).lower()
            mapped = ACTION_TO_RELAY.get(action)
            if mapped is None:
                return None
            # ack가 아닌 명령 토픽은 아직 이행 전이므로 기록하지 않는다
            if kind == "control/relay/ack" and payload.get("status") not in (None, "ok", "OK"):
                return None
            if kind == "control/relay":
                shadow["relay_state"] = mapped
                return None
            shadow["relay_state"] = mapped
            emit = shadow["grid_current_a"] is not None

        else:
            return None

        if not emit or shadow["grid_current_a"] is None:
            return None

        canonical = {
            # 구성 A의 ess-demo-01과 섞이지 않도록 건물 id를 그대로 device_id로 쓴다
            "device_id": building_id,
            "timestamp": int(time.time()),
            "grid_current_a": shadow["grid_current_a"],
            "relay_state": shadow["relay_state"],
            "threshold_high_a": LEGACY_THRESHOLD_HIGH_A,
            "threshold_low_a": LEGACY_THRESHOLD_LOW_A,
            "hold_remaining_s": 0,  # 구성 B는 서버/백엔드가 판단 — 로컬 hold 개념 없음
            "battery_voltage_v": shadow["battery_voltage_v"],
            "ess_current_a": shadow["ess_current_a"],
            "ess_power_w": shadow["ess_power_w"],
        }

    save(canonical)
    return canonical


def reset() -> None:
    """테스트용 섀도우 초기화."""
    with _lock:
        _shadow.clear()
