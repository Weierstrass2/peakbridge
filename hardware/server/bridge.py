"""클라우드 브리지 — 하드웨어 실측값을 기존 아파트 관제 시스템에 흘려보낸다.

`BRIDGE_URL`이 설정된 경우에만 동작한다. 수신한 텔레메트리를 기존 백엔드
`POST {BRIDGE_URL}/api/v1/sensors/readings` 로 릴레이하면:

  - 아파트 대시보드의 `grid_current` 카드가 **실물 CT 측정값**으로 바뀐다
  - 백엔드 `peak_service.evaluate()`가 돌아 피크 알림·차트가 실물에 반응한다
  - WebSocket 브로드캐스트로 화면이 실시간 갱신된다
  - VPP OS 콘솔의 StateCollector도 같은 DB를 읽으므로 함께 살아난다

기존 백엔드는 이 엔드포인트에 **인증을 요구하지 않는다** (app/api/v1/sensors.py 확인).
없는 device_id는 building_id와 함께 보내면 `get_or_create`로 자동 등록된다.

원칙: 릴레이 실패가 로컬 저장·응답을 절대 지연하거나 차단하지 않는다.
      (별도 워커 스레드 + 유한 큐 fire-and-forget, 실패 시 경고 로그만)

환경변수:
  BRIDGE_URL          예: https://peakbridge-production.up.railway.app  (미설정 시 비활성)
  BRIDGE_BUILDING_ID  기본 building-A
  BRIDGE_DEVICE_ID    기본 GRID-01
  BRIDGE_ESS_DEVICE_ID 기본 ESS-01
  BRIDGE_SCALE        전류 환산 계수. 기본 1.0 = 실측값 그대로 전송
  BRIDGE_MIN_INTERVAL_S 전송 최소 간격(초). 기본 2.0 — 1Hz 텔레메트리를 그대로 다 쏘면
                        클라우드 DB에 과부하이므로 솎아낸다. 절체 순간은 항상 즉시 전송.

⚠️ 스케일 주의: 실물 데모 전류는 0.036~0.108A다. 기존 시연용 피크 임계치가
   PEAK_THRESHOLD_A=0.5로 잡혀 있으면 절체가 일어나도 대시보드는 피크로 인식하지 않는다.
   Railway 환경변수를 **PEAK_THRESHOLD_A=0.08** 로 낮추는 것이 가장 정직한 방법이다.
   (심사에서 "왜 0.09A냐"는 질문에 "축소모형 실증"이라고 그대로 답할 수 있다)
   화면상 아파트 규모로 보이길 원하면 BRIDGE_SCALE=200 처럼 환산할 수 있으나,
   이 경우 원측정값이 로그·로컬 DB에 그대로 남으므로 설명 근거는 유지된다.
"""

import logging
import os
import queue
import threading
from typing import Any

logger = logging.getLogger("bridge")

# LiFePO4 4S 팩 전압 → SOC 환산 (팀원A ESP32 #2 명세와 동일 기준)
CELL_FULL_V = 3.65
CELL_EMPTY_V = 3.20
PACK_CELLS = 4

_url = ""
_building_id = os.environ.get("BRIDGE_BUILDING_ID", "building-A")
_device_id = os.environ.get("BRIDGE_DEVICE_ID", "GRID-01")
_ess_device_id = os.environ.get("BRIDGE_ESS_DEVICE_ID", "ESS-01")
_scale = float(os.environ.get("BRIDGE_SCALE", "1.0"))
_min_interval = float(os.environ.get("BRIDGE_MIN_INTERVAL_S", "2.0"))

_enabled = False
_queue: "queue.Queue[dict]" = queue.Queue(maxsize=200)
_worker: threading.Thread | None = None
_sent = 0
_failed = 0
_last_sent_at = 0.0
_last_relay_state: str | None = None


def status() -> dict[str, Any]:
    return {
        "enabled": _enabled,
        "url": _url,
        "building_id": _building_id,
        "device_id": _device_id,
        "scale": _scale,
        "sent": _sent,
        "failed": _failed,
    }


def init() -> None:
    global _url, _enabled, _worker

    _url = os.environ.get("BRIDGE_URL", "").strip().rstrip("/")
    if not _url:
        logger.info("BRIDGE_URL 미설정 — 클라우드 브리지 비활성 (로컬 시연에는 불필요).")
        return

    try:
        import requests  # noqa: F401
    except ImportError:
        logger.warning("requests 미설치 — 브리지 비활성.")
        return

    _enabled = True
    _worker = threading.Thread(target=_run, daemon=True)
    _worker.start()
    logger.info(
        "클라우드 브리지 활성: %s (건물 %s, 디바이스 %s, 스케일 ×%s)",
        _url, _building_id, _device_id, _scale,
    )


def soc_from_voltage(pack_voltage_v: float | None) -> float | None:
    """배터리 전압 → SOC(%) 선형 보간.

    셀 전압(3.2~3.65V)으로 들어와도, 팩 전압(12.8~14.6V)으로 들어와도 처리한다.
    """
    if pack_voltage_v is None:
        return None
    v = float(pack_voltage_v)
    if v <= 0:
        return None
    # 5V를 넘으면 팩 전압으로 간주하고 셀 전압으로 환산
    cell_v = v / PACK_CELLS if v > 5.0 else v
    ratio = (cell_v - CELL_EMPTY_V) / (CELL_FULL_V - CELL_EMPTY_V)
    return round(max(0.0, min(1.0, ratio)) * 100.0, 1)


def build_readings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """텔레메트리 1건 → 기존 백엔드 SensorReadingCreate 배열.

    sensor_type은 백엔드 Literal["grid_current","ess_soc","charger_current"]만 허용한다.
    """
    readings: list[dict[str, Any]] = [
        {
            "device_id": _device_id,
            "sensor_type": "grid_current",
            "value": round(float(payload["grid_current_a"]) * _scale, 4),
            "unit": "A",
            "building_id": _building_id,
        }
    ]

    soc = soc_from_voltage(payload.get("battery_voltage_v"))
    if soc is not None:
        readings.append(
            {
                "device_id": _ess_device_id,
                "sensor_type": "ess_soc",
                "value": soc,
                "unit": "%",
                "building_id": _building_id,
            }
        )
    return readings


def relay(payload: dict[str, Any]) -> None:
    """비차단 큐 적재.

    - 최소 간격으로 솎아내되, **릴레이 상태가 바뀐 샘플은 항상 통과시킨다**
      (절체 순간이 클라우드 대시보드에서 누락되면 안 된다)
    - 큐가 가득 차면 그냥 버린다 (로컬 시연이 우선)
    """
    global _last_sent_at, _last_relay_state
    if not _enabled:
        return

    import time

    now = time.time()
    relay_state = payload.get("relay_state")
    changed = relay_state != _last_relay_state
    if not changed and (now - _last_sent_at) < _min_interval:
        return

    _last_relay_state = relay_state
    _last_sent_at = now

    try:
        _queue.put_nowait(payload)
    except queue.Full:
        logger.debug("브리지 큐 가득참 — 1건 폐기")


def _run() -> None:
    global _sent, _failed
    import requests

    session = requests.Session()
    endpoint = f"{_url}/api/v1/sensors/readings"

    while True:
        payload = _queue.get()
        try:
            body = {"readings": build_readings(payload)}
            resp = session.post(endpoint, json=body, timeout=3)
            if resp.status_code >= 400:
                _failed += 1
                logger.warning("브리지 릴레이 실패 %s: %s", resp.status_code, resp.text[:200])
            else:
                _sent += 1
                if _sent == 1 or _sent % 20 == 0:
                    logger.info(
                        "브리지 릴레이 %d건 (원측정 %.4fA → 전송 %.4fA)",
                        _sent, payload["grid_current_a"], body["readings"][0]["value"],
                    )
        except Exception as exc:  # noqa: BLE001
            _failed += 1
            logger.warning("브리지 릴레이 예외: %s", exc)
        finally:
            _queue.task_done()
