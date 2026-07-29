"""PeakBridge 하드웨어 데모 서버 (로컬 폐쇄망 전용, 포트 8010).

기존 backend/ frontend/ frontend-vpp/ 와 완전히 분리된 독립 시스템이다.
인증·Postgres·WebSocket·Railway 배포 없음. 시연은 이 서버 하나로 완결된다.

기동:
    cd hardware/server && python -m uvicorn main:app --host 0.0.0.0 --port 8010
    (MQTT 사용 시) MQTT_BROKER=192.168.0.10 python -m uvicorn main:app --host 0.0.0.0 --port 8010
    (클라우드 브리지 사용 시) BRIDGE_URL=https://... 추가
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import autopilot
import bridge
import db
import mqtt_gateway
import smp_relay
from models import (
    ConfigModel,
    ConfigUpdate,
    EventRecord,
    TelemetryIn,
    TelemetryRecord,
    TelemetryResponse,
    config_payload,
    validate_config,
)

DASHBOARD_DIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "dist"
)


def ingest(payload: dict) -> dict:
    """HTTP·MQTT 공용 수신 처리: 저장 → 이벤트 감지 → 클라우드 브리지 릴레이.

    브리지는 fire-and-forget이라 로컬 저장·응답을 절대 지연시키지 않는다.
    """
    result = db.save_telemetry(payload)
    bridge.relay(payload)
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    bridge.init()
    # MQTT_BROKER가 설정된 경우에만 접속 시도. 미설정이면 HTTP-only 모드로 완전 동작.
    mqtt_gateway.start(ingest, db.get_config)
    # AUTOPILOT=1 + BRIDGE_URL 설정 시에만: Railway AI 예측 → 선제 임계치 조정
    autopilot.init()
    # BRIDGE_URL 설정 시: KPX 웹 당일 SMP → 클라우드 주입 (한국 IP 우회 중계)
    smp_relay.init()
    yield
    mqtt_gateway.stop()


app = FastAPI(title="PeakBridge 하드웨어 데모 서버", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mqtt": mqtt_gateway.status(),
        "bridge": bridge.status(),
        "autopilot": autopilot.status(),
        "smp_relay": smp_relay.status(),
        "legacy_adapter": mqtt_gateway.LEGACY_ENABLED,
    }


@app.get("/api/devices")
def get_devices():
    """수신 이력이 있는 디바이스 목록 — 대시보드 디바이스 선택기용."""
    return db.list_devices()


@app.post("/api/telemetry", response_model=TelemetryResponse)
def post_telemetry(payload: TelemetryIn):
    """텔레메트리 수신. 응답에 현재 config를 동봉해 ESP32가 즉시 최신값을 반영한다."""
    ingest(payload.model_dump())
    return TelemetryResponse(ok=True, config=ConfigModel(**db.get_config()))


@app.get("/api/latest", response_model=TelemetryRecord)
def get_latest(device_id: str | None = None):
    row = db.get_latest(device_id)
    if row is None:
        # 프론트는 404를 "연결 대기" 상태로 표시한다.
        raise HTTPException(status_code=404, detail="수신된 텔레메트리가 아직 없습니다.")
    return TelemetryRecord(**row)


@app.get("/api/history", response_model=list[TelemetryRecord])
def get_history(minutes: int = 10, device_id: str | None = None):
    if minutes < 1 or minutes > 1440:
        raise HTTPException(status_code=422, detail="minutes는 1~1440 범위여야 합니다.")
    return [TelemetryRecord(**r) for r in db.get_history(minutes, device_id)]


@app.get("/api/events", response_model=list[EventRecord])
def get_events(limit: int = 100, device_id: str | None = None):
    return [EventRecord(**r) for r in db.get_events(limit, device_id)]


@app.get("/api/config", response_model=ConfigModel)
def get_config():
    return ConfigModel(**db.get_config())


@app.put("/api/config", response_model=ConfigModel)
def put_config(payload: ConfigUpdate):
    """설정 변경. 펌웨어와 동일 규칙으로 검증하고, 위반 시 422 + 한국어 사유."""
    # ina_low_ma 미지정 시 기존 저장값 유지 (구버전 클라이언트 호환)
    ina_low_ma = payload.ina_low_ma if payload.ina_low_ma is not None else db.get_config()["ina_low_ma"]

    reason = validate_config(
        payload.threshold_high_a, payload.threshold_low_a, payload.min_hold_s, ina_low_ma
    )
    if reason:
        raise HTTPException(status_code=422, detail=reason)

    cfg = db.update_config(
        payload.threshold_high_a, payload.threshold_low_a, payload.min_hold_s, ina_low_ma
    )
    # MQTT 활성 시 config 토픽으로 retained·QoS1 재발행 (ESP32 재부팅 시에도 최신값 보장)
    mqtt_gateway.publish_config(config_payload(cfg))
    return ConfigModel(**cfg)


# 대시보드 정적 서빙 — 빌드 결과가 있을 때만 마운트.
# 시연 시 라즈베리파이에는 Python만 있으면 된다 (node 불필요).
if os.path.isdir(DASHBOARD_DIST):
    app.mount("/", StaticFiles(directory=DASHBOARD_DIST, html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
