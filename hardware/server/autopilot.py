"""AI 예측 기반 선제 임계치 오토파일럿 (D 폐루프).

BRIDGE_URL이 설정되고 AUTOPILOT=1일 때만 동작. Railway 아파트 관제의 AI 예측
(next_peak)을 폴링해, 피크가 예상되면 하드웨어 임계치를 선제적으로 낮춰
ESP32가 미리 ESS로 절체하게 한다. 피크 예상이 사라지면 원래 임계치로 복원.

핵심 안전 원칙: 서버가 릴레이를 직접 흔들지 않는다. 임계치(config)만 조정하고
절체 판단은 여전히 ESP32 로컬 히스테리시스가 한다 — 통신이 끊겨도 마지막
config로 계속 안전하게 돈다. "AI 예측 → 임계치 선제 조정 → 하드웨어 자율 절체".
"""

import logging
import os
import threading
import time

import db
import mqtt_gateway
from models import config_payload, validate_config

logger = logging.getLogger("autopilot")

_url = ""
_building = os.environ.get("BRIDGE_BUILDING_ID", "building-A")
_enabled = False
_baseline_high: float | None = None
_active = False
_last_reason = ""


def status() -> dict:
    return {
        "enabled": _enabled,
        "active": _active,
        "baseline_high": _baseline_high,
        "last": _last_reason,
    }


def init() -> None:
    """AUTOPILOT=1 + BRIDGE_URL 설정 시에만 백그라운드 폴링 시작."""
    global _url, _enabled
    if os.environ.get("AUTOPILOT", "0") != "1":
        return
    _url = os.environ.get("BRIDGE_URL", "").strip().rstrip("/")
    if not _url:
        logger.info("AUTOPILOT=1이지만 BRIDGE_URL 미설정 — 오토파일럿 비활성")
        return
    try:
        import requests  # noqa: F401
    except ImportError:
        logger.warning("requests 미설치 — 오토파일럿 비활성")
        return
    _enabled = True
    threading.Thread(target=_run, daemon=True).start()
    logger.info("AI 오토파일럿 활성: %s/api/v1/dashboard/%s 예측 폴링", _url, _building)


def _run() -> None:
    global _baseline_high, _active, _last_reason
    import requests

    session = requests.Session()
    endpoint = f"{_url}/api/v1/dashboard/{_building}"
    while True:
        try:
            resp = session.get(endpoint, timeout=4)
            d = resp.json().get("data", {})
            next_peak = d.get("next_peak")
            grid = float(d.get("grid_current") or 0.0)
            cfg = db.get_config()

            if next_peak and not _active:
                # 현재 실측 살짝 아래로 임계치 하향 → ESP32가 선제 절체
                _baseline_high = cfg["threshold_high_a"]
                low = cfg["threshold_low_a"]
                target = max(round(low + 0.005, 4), round(grid * 0.9, 4)) if grid > 0 else _baseline_high
                if target < _baseline_high:
                    if _apply(target, cfg):
                        _active = True
                        _last_reason = (
                            f"피크 {next_peak.get('minutes_ahead')}분 뒤 예상 → "
                            f"임계치 {_baseline_high:.4f}→{target:.4f} 선제 하향"
                        )
                        logger.warning("AI 선제 대응: %s", _last_reason)
            elif not next_peak and _active:
                if _baseline_high is not None and _apply(_baseline_high, cfg):
                    _last_reason = f"피크 예상 해소 → 임계치 {_baseline_high:.4f} 복원"
                    logger.info(_last_reason)
                _active = False
        except Exception as exc:  # noqa: BLE001
            logger.debug("오토파일럿 폴링 예외: %s", exc)
        time.sleep(3)


def _apply(new_high: float, cfg: dict) -> bool:
    """임계치 변경 + 검증 + MQTT retained 발행. 성공 시 True."""
    reason = validate_config(
        new_high, cfg["threshold_low_a"], cfg["min_hold_s"], cfg["ina_low_ma"]
    )
    if reason:
        logger.warning("오토파일럿 config 거부: %s", reason)
        return False
    newcfg = db.update_config(
        new_high, cfg["threshold_low_a"], cfg["min_hold_s"], cfg["ina_low_ma"]
    )
    mqtt_gateway.publish_config(config_payload(newcfg))
    return True
