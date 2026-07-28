"""클라우드 브리지 검증 — 기존 백엔드 스키마를 그대로 흉내낸 스텁 서버로 확인.

실제 Railway 서버를 두드리지 않고도, 브리지가 보내는 페이로드가
`backend/app/schemas/api.py`의 `SensorReadingBatchCreate` 와 정확히 맞는지 검증한다.
(스텁은 그 스키마를 그대로 복사해 쓰므로, 여기서 통과하면 실서버에서도 422가 나지 않는다)

확인 항목:
  1. readings 배열 형식 + sensor_type Literal 준수
  2. 배터리 전압 → ess_soc 환산 (LiFePO4 4S: 12.8V=0%, 14.6V=100%)
  3. BRIDGE_SCALE 적용
  4. 절체 순간(relay_state 변화)은 최소 간격과 무관하게 항상 전송
  5. 브리지가 죽어도 로컬 저장은 계속된다 (실서버 장애 시나리오)

실행:
    python verify_bridge.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STUB_PORT = 8016
API_PORT = 8017
BASE = f"http://127.0.0.1:{API_PORT}"
STUB = f"http://127.0.0.1:{STUB_PORT}"

# 기존 백엔드 스키마를 그대로 옮긴 스텁 (Literal 제약 포함)
STUB_SCRIPT = '''
from typing import Literal
from fastapi import FastAPI
from pydantic import BaseModel
import json, os, threading

RECORD = os.environ["STUB_RECORD"]
_lock = threading.Lock()

class SensorReadingCreate(BaseModel):
    device_id: str
    sensor_type: Literal["grid_current", "ess_soc", "charger_current"]
    value: float
    unit: str = "A"
    building_id: str | None = None

class SensorReadingBatchCreate(BaseModel):
    readings: list[SensorReadingCreate] | None = None
    device_id: str | None = None
    sensor_type: Literal["grid_current", "ess_soc", "charger_current"] | None = None
    value: float | None = None
    unit: str = "A"
    building_id: str | None = None

app = FastAPI()

@app.post("/api/v1/sensors/readings")
def readings(body: SensorReadingBatchCreate):
    with _lock:
        with open(RECORD, "a", encoding="utf-8") as f:
            f.write(body.model_dump_json() + "\\n")
    return {"success": True, "data": {"status": "recorded", "peak_triggered": False, "forecast_next_hour": []}}
'''

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((ok, label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def post_telemetry(body: dict) -> int:
    req = urllib.request.Request(
        BASE + "/api/telemetry", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def telemetry(current: float, relay: str, voltage: float | None = None) -> dict:
    return {
        "device_id": "ess-demo-01",
        "timestamp": 0,
        "grid_current_a": current,
        "relay_state": relay,
        "threshold_high_a": 0.09,
        "threshold_low_a": 0.055,
        "hold_remaining_s": 0,
        "battery_voltage_v": voltage,
        "ina_current_ma": 700.0,
    }


def main() -> int:
    tmp = tempfile.mkdtemp()
    record = os.path.join(tmp, "record.jsonl")
    open(record, "w").close()
    stub_py = os.path.join(tmp, "stub.py")
    with open(stub_py, "w", encoding="utf-8") as f:
        f.write(STUB_SCRIPT)

    procs: list[subprocess.Popen] = []
    try:
        print("\n[1] 스텁 백엔드 + 브리지 활성 서버 기동")
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "stub:app", "--host", "127.0.0.1", "--port", str(STUB_PORT)],
                cwd=tmp, env=dict(os.environ, STUB_RECORD=record),
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
        )
        env = dict(
            os.environ,
            HARDWARE_DB_PATH=os.path.join(tmp, "bridge.db"),
            BRIDGE_URL=STUB,
            BRIDGE_SCALE="200",
            BRIDGE_MIN_INTERVAL_S="2.0",
        )
        env.pop("MQTT_BROKER", None)
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
                cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
        )
        for _ in range(40):
            try:
                urllib.request.urlopen(BASE + "/api/health", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        time.sleep(1)

        print("\n[2] 텔레메트리 → 브리지 릴레이")
        check(post_telemetry(telemetry(0.036, "NC", 13.4)) == 200, "텔레메트리 수신 200")
        time.sleep(1.5)
        # 최소 간격 안쪽 + 상태 변화 없음 → 솎아내야 함
        post_telemetry(telemetry(0.038, "NC", 13.4))
        time.sleep(0.5)
        # 상태 변화 → 간격과 무관하게 즉시 전송돼야 함
        post_telemetry(telemetry(0.108, "NO", 13.4))
        time.sleep(2.5)

        lines = [json.loads(l) for l in open(record, encoding="utf-8") if l.strip()]
        print(f"  (스텁이 수신한 요청 {len(lines)}건)")
        check(len(lines) >= 2, f"스텁 수신 {len(lines)}건 (스키마 검증 통과 = 실서버 422 없음)")

        first = lines[0]["readings"]
        types = {r["sensor_type"] for r in first}
        check(types == {"grid_current", "ess_soc"}, f"grid_current + ess_soc 동시 전송 {types}")

        grid = next(r for r in first if r["sensor_type"] == "grid_current")
        check(
            abs(grid["value"] - 0.036 * 200) < 0.01,
            f"BRIDGE_SCALE=200 적용 (0.036A → {grid['value']}A)",
        )
        check(grid["device_id"] == "GRID-01" and grid["building_id"] == "building-A",
              f"디바이스/건물 지정 {grid['device_id']} / {grid['building_id']}")

        soc = next(r for r in first if r["sensor_type"] == "ess_soc")
        # 13.4V / 4셀 = 3.35V → (3.35-3.20)/(3.65-3.20) = 33.3%
        check(abs(soc["value"] - 33.3) < 0.5, f"배터리 13.4V → SOC {soc['value']}% (기대 33.3%)")

        peaks = [l for l in lines if any(r["sensor_type"] == "grid_current" and r["value"] > 20 for r in l["readings"])]
        check(bool(peaks), "절체 샘플(0.108A→21.6A)이 최소 간격 무시하고 전송됨")

        print("\n[3] 실서버 장애 내성")
        procs[0].kill()  # 스텁 다운 = Railway 장애 상황
        time.sleep(0.5)
        codes = [post_telemetry(telemetry(0.05 + i * 0.01, "NC", 13.0)) for i in range(3)]
        check(all(c == 200 for c in codes), f"백엔드 다운 상태에서도 로컬 수신 정상 {codes}")

        with urllib.request.urlopen(BASE + "/api/history?minutes=10", timeout=5) as r:
            hist = json.loads(r.read().decode())
        check(len(hist) >= 6, f"로컬 DB 저장 계속됨 ({len(hist)}건) — 클라우드 장애가 시연을 죽이지 않음")

    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()

    failed = [label for ok, label in results if not ok]
    print("\n" + "=" * 60)
    print(f"결과: {len(results) - len(failed)}/{len(results)} 통과")
    for label in failed:
        print(f"  실패: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
