"""시연 시나리오 트리거 API — 실제 엔진(MQTT/OpenADR/배전망 시뮬레이터) 연결."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.v1.realtime import ws_manager
from app.core.constants import DeviceType, SensorType
from app.core.deps import DbSession
from app.ml.energy_optimizer import EnergyOptimizer
from app.ml.grid_simulator import grid_simulator
from app.mqtt.publisher import mqtt_publisher
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository
from app.schemas.response import success_response
from app.services.openadr_service import openadr_service

logger = structlog.get_logger(__name__)

router = APIRouter()

optimizer = EnergyOptimizer()

SCENARIOS = ["peak_discharge", "midnight_charge", "demand_response", "normal"]


class TriggerRequest(BaseModel):
    scenario: str = Field(default="normal")
    building_id: str = Field(default="building-A")


async def _live_inputs(session, building_id: str) -> dict:
    """DB 최신 센서값 (실패해도 기본값)."""
    out = {"grid_current": 0.0, "ess_soc": 0.0, "ess_available": False, "ev_count": 0}
    try:
        sensor_repo = SensorRepository(session)
        device_repo = DeviceRepository(session)
        g = await sensor_repo.get_latest_by_building(
            building_id, SensorType.GRID_CURRENT.value, DeviceType.GRID_METER.value
        )
        if g:
            out["grid_current"] = g.value
        e = await sensor_repo.get_latest_by_building(
            building_id, SensorType.ESS_SOC.value, DeviceType.ESS.value
        )
        if e:
            out["ess_soc"] = e.value
            out["ess_available"] = True
        out["ev_count"] = len(
            await device_repo.list_by_building(building_id, DeviceType.CHARGER.value)
        )
    except Exception as exc:
        logger.warning("simulation_live_inputs_failed", error=str(exc))
    return out


@router.post("/trigger")
async def trigger_simulation(session: DbSession, body: TriggerRequest) -> dict:
    """
    POST /api/v1/simulation/trigger — 발표 시연용 시나리오 실행.

    peak_discharge: 피크 연출 → ESS 방전 명령 + 배전망 전/후 시뮬레이션
    midnight_charge: 심야 충전 명령 + 현재 요금 근거
    demand_response: OpenADR SIMPLE 3 긴급 이벤트 발령
    normal: 대기 복귀
    """
    scenario = body.scenario if body.scenario in SCENARIOS else "normal"
    building_id = body.building_id
    live = await _live_inputs(session, building_id)
    result: dict = {"scenario": scenario, "building_id": building_id, "inputs": live}

    try:
        if scenario == "peak_discharge":
            # 발표 스토리 수치: 실측이 작으면 시연 프로파일로 보정
            gc = live["grid_current"] if live["grid_current"] >= 20 else 25.0
            ev = live["ev_count"] if live["ev_count"] >= 8 else 30
            sim = grid_simulator.simulate(
                grid_current=gc, ess_discharge_kw=100.0, ev_count=ev
            )
            sent = await mqtt_publisher.publish_relay_control(
                building_id, "discharge", "simulation"
            )
            await ws_manager.send_control_executed(building_id, "discharge", "ESS-01")
            result.update(
                {
                    "action": "discharge",
                    "mqtt_sent": bool(sent),
                    "simulation": sim,
                    "message": (
                        f"변압기 {sim['transformer_load_percent']}% "
                        f"({sim['status_before']}) → ESS 방전 → "
                        f"{sim['after_peakbridge_percent']}% ({sim['status']})"
                    ),
                }
            )

        elif scenario == "midnight_charge":
            rate = optimizer.get_current_rate()
            sent = await mqtt_publisher.publish_relay_control(
                building_id, "charge", "simulation"
            )
            await ws_manager.send_control_executed(building_id, "charge", "ESS-01")
            result.update(
                {
                    "action": "charge",
                    "mqtt_sent": bool(sent),
                    "tariff": rate,
                    "message": f"{rate['period']} {rate['rate']}원/kWh — 저가 충전 시작",
                }
            )

        elif scenario == "demand_response":
            event = await openadr_service.handle_event(
                "SIMPLE", 3, building_id=building_id
            )
            result.update(
                {
                    "action": event["action"],
                    "dr_event": event,
                    "message": f"OpenADR {event['label']} (이벤트 {event['event_id']})",
                }
            )

        else:  # normal
            sent = await mqtt_publisher.publish_relay_control(
                building_id, "standby", "simulation"
            )
            await ws_manager.send_control_executed(building_id, "standby", "ESS-01")
            result.update(
                {"action": "standby", "mqtt_sent": bool(sent), "message": "대기 상태 복귀"}
            )

        result["status"] = "executed"
    except Exception as exc:
        logger.error("simulation_trigger_failed", scenario=scenario, error=str(exc))
        result.update({"status": "error", "message": "시나리오 실행 일시 불가"})

    return success_response(result)


@router.get("/scenarios")
async def list_scenarios() -> dict:
    """사용 가능한 시연 시나리오 목록."""
    return success_response(
        {
            "scenarios": [
                {"id": "peak_discharge", "name": "피크 방전 시연", "description": "과부하 → ESS 방전 → 정상화"},
                {"id": "midnight_charge", "name": "심야 충전 시연", "description": "경부하 저가 충전"},
                {"id": "demand_response", "name": "수요반응 시연", "description": "OpenADR SIMPLE 3 긴급 발령"},
                {"id": "normal", "name": "정상 복귀", "description": "대기 상태"},
            ]
        }
    )
