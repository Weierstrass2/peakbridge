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
import time

# Railway 저사양 보호: 클라우드 전송 간 최소 간격(초). record_batch가 건별
# 예측을 돌아 무겁고, 매초 연속 전송 시 밀려 타임아웃난다. 이 간격만큼 쉬어
# 과부하를 막는다(큐 드레인이 있어 이 사이 쌓인 텔레메트리는 최신만 전송).
_MIN_POST_INTERVAL = 2.5
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
    # 클라우드 → 하드웨어 역방향: SOC 리셋 요청 폴러 (버튼 → 펌웨어 쿨롱카운터 리셋)
    threading.Thread(target=_poll_soc_reset, daemon=True).start()
    # 강제 방전 모드 폴러 (버튼 → 펌웨어 NO 유지/자동 복귀)
    threading.Thread(target=_poll_force_discharge, daemon=True).start()
    # 하드웨어 임계 설정 폴러 (탭 입력 → 게이트웨이 config → MQTT config → XIAO)
    threading.Thread(target=_poll_hw_threshold, daemon=True).start()
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

    # SOC: 펌웨어의 쿨롱 카운팅 값(battery_soc)을 최우선으로 쓴다.
    # LiFePO4는 전압 곡선이 평평해 전압 환산(soc_from_voltage)은 부정확하므로,
    # 펌웨어가 전류 적분으로 계산해 보낸 SOC가 있으면 그것을 그대로 전달한다.
    soc = payload.get("battery_soc")
    if soc is None:
        soc = soc_from_voltage(payload.get("battery_voltage_v"))
    if soc is not None:
        readings.append(
            {
                "device_id": _ess_device_id,
                "sensor_type": "ess_soc",
                "value": round(float(soc), 1),
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


def _poll_soc_reset() -> None:
    """클라우드의 SOC 리셋 요청을 3초 주기로 폴링해 MQTT command로 1회 전파.

    아파트 대시보드의 [100% 리셋] 버튼 → Railway in-memory 요청(120초 유효) →
    여기서 id 신규 여부로 중복 실행을 막고 펌웨어에 soc_set 명령을 보낸다.
    오토파일럿과 달리 임계치엔 손대지 않는다 — SOC 표시 기준값 보정 전용.
    """
    import time

    import requests

    import mqtt_gateway

    session = requests.Session()
    endpoint = f"{_url}/api/v1/control/{_building_id}/soc-reset"
    last_id: int | None = None
    while True:
        try:
            resp = session.get(endpoint, timeout=3)
            pending = resp.json().get("data", {}).get("pending")
            if pending and pending.get("id") != last_id:
                last_id = pending.get("id")
                sent = mqtt_gateway.publish_command(
                    {
                        "action": "soc_set",
                        "percent": float(pending.get("percent", 100.0)),
                        "request_id": last_id,
                    }
                )
                logger.info(
                    "SOC 리셋 요청 수신(id=%s) → MQTT command %s",
                    last_id, "발행" if sent else "미발행(MQTT 비활성)",
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("SOC 리셋 폴링 예외: %s", exc)
        time.sleep(3)


def _poll_force_discharge() -> None:
    """클라우드의 강제 방전 모드 상태를 3초 주기로 폴링해 MQTT command로 전파.

    [강제 방전] 버튼 → Railway in-memory 토글 → 여기서 id(변경 시각)로 상태 변화를
    감지해 force_discharge/auto 명령을 보낸다. on인 동안은 15초마다 재발행해,
    XIAO가 중간에 재부팅(기본값=해제)해도 곧 강제 모드가 복원되게 한다.
    오토파일럿·SOC리셋과 같은 원칙: 릴레이를 직접 흔들지 않고 모드만 바꾼다.
    """
    import time

    import requests

    import mqtt_gateway

    session = requests.Session()
    endpoint = f"{_url}/api/v1/control/{_building_id}/force-discharge"
    last_id: int | None = None
    last_republish = 0.0
    while True:
        try:
            resp = session.get(endpoint, timeout=3)
            state = resp.json().get("data", {}).get("state")
            if state is not None:
                on = bool(state.get("on"))
                changed = state.get("id") != last_id
                # 상태가 바뀌었거나, on 유지 중 15초 경과 시 재발행(재부팅 복원용)
                if changed or (on and time.time() - last_republish >= 15):
                    action = "force_discharge" if on else "auto"
                    sent = mqtt_gateway.publish_command({"action": action})
                    last_id = state.get("id")
                    last_republish = time.time()
                    if changed:
                        logger.info(
                            "강제 방전 %s → MQTT command %s",
                            "ON" if on else "OFF",
                            "발행" if sent else "미발행(MQTT 비활성)",
                        )
        except Exception as exc:  # noqa: BLE001
            logger.debug("강제 방전 폴링 예외: %s", exc)
        time.sleep(3)


def _poll_hw_threshold() -> None:
    """클라우드 '하드웨어 실측' 탭의 임계 설정 요청을 3초 주기로 폴링해 게이트웨이
    config 갱신 + MQTT config(retained)로 XIAO에 전파. Railway in-memory 요청을 id로
    감지. config는 retained라 1회 발행으로 재부팅에도 복원된다. 오토파일럿·강제방전과
    같은 원칙: 릴레이 직접 제어가 아니라 임계(config)만 조정한다."""
    import time

    import requests

    import db
    import mqtt_gateway
    from models import config_payload, validate_config

    session = requests.Session()
    endpoint = f"{_url}/api/v1/control/{_building_id}/hw-threshold-request"
    last_id: int | None = None
    while True:
        try:
            resp = session.get(endpoint, timeout=3)
            state = resp.json().get("data", {}).get("state")
            if state is not None and state.get("id") != last_id:
                high = float(state.get("high"))
                cfg = db.get_config()
                reason = validate_config(
                    high, cfg["threshold_low_a"], cfg["min_hold_s"], cfg["ina_low_ma"]
                )
                last_id = state.get("id")  # 유효/무효 무관 재처리 방지
                if reason:
                    logger.warning("클라우드 임계 거부: %s", reason)
                else:
                    newcfg = db.update_config(
                        high, cfg["threshold_low_a"], cfg["min_hold_s"], cfg["ina_low_ma"]
                    )
                    sent = mqtt_gateway.publish_config(config_payload(newcfg))
                    logger.info(
                        "클라우드 임계 %.4fA → config 전파 %s",
                        high,
                        "발행" if sent else "미발행(MQTT 비활성)",
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("임계 폴링 예외: %s", exc)
        time.sleep(3)


def _run() -> None:
    global _sent, _failed
    import requests

    session = requests.Session()
    endpoint = f"{_url}/api/v1/sensors/readings"
    runtime_endpoint = f"{_url}/api/v1/control/{_building_id}/ess-runtime"

    while True:
        payload = _queue.get()
        # 전송이 밀렸다면 큐에 쌓인 과거분을 버리고 최신값만 올린다.
        # 클라우드는 실시간 최신 상태만 표시하므로, 느린 POST로 지연이
        # 누적되지 않도록 항상 가장 최근 텔레메트리로 건너뛴다.
        try:
            while True:
                payload = _queue.get_nowait()
                _queue.task_done()
        except queue.Empty:
            pass
        try:
            body = {"readings": build_readings(payload)}
            resp = session.post(endpoint, json=body, timeout=15)
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
            # ESS 잔여 가동시간 + 열 차단(BME280 온도) — 별도 경량 경로.
            # 실패해도 메인 릴레이엔 영향 없음. 방전 중이 아니어도(remain=0) 온도가
            # 있으면 함께 올려 클라우드가 상시 온도·열 차단 상태를 표시하게 한다.
            remain = payload.get("remain_hours") or 0.0
            bt = payload.get("battery_temp_c")
            it = payload.get("inverter_temp_c")
            tl = payload.get("thermal_lock")
            # 실시간 릴레이/계측 상태 — 클라우드 '하드웨어 실측' 탭이 표시한다.
            rs = payload.get("relay_state")
            ina = payload.get("ina_current_ma")
            thr = payload.get("threshold_high_a")
            hold = payload.get("hold_remaining_s")
            # 온도·릴레이 등 표시할 값이 하나라도 있으면 사이드채널로 올린다(방전 중이 아니어도).
            if (
                (remain and float(remain) > 0)
                or bt is not None
                or it is not None
                or tl is not None
                or rs is not None
            ):
                try:
                    session.post(
                        runtime_endpoint,
                        json={
                            "remain_hours": float(remain or 0.0),
                            "soc": payload.get("battery_soc"),
                            "battery_temp_c": bt,
                            "inverter_temp_c": it,
                            "thermal_lock": tl,
                            "relay_state": rs,
                            "ina_current_ma": ina,
                            "threshold_high_a": thr,
                            "hold_remaining_s": hold,
                        },
                        timeout=15,
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            _failed += 1
            logger.warning("브리지 릴레이 예외: %s", exc)
        finally:
            _queue.task_done()
        # 전송 간 최소 간격 — Railway 과부하 방지(위 드레인이 최신값을 보장).
        time.sleep(_MIN_POST_INTERVAL)
