"""열 차단(BME280 온도 + thermal_lock) 서버 경로 자동 검증 — 실기 없이.

서버 기동 → 온도·thermal_lock 포함 텔레메트리 POST → /api/latest 라운드트립 확인.
models.py(v5 필드) + db.py(마이그레이션·저장·조회)가 실제로 온도를 보존하는지 본다.

실행: PYTHONUTF8=1 py verify_thermal.py
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
PORT = int(os.environ.get("VERIFY_PORT", "8013"))
BASE = f"http://127.0.0.1:{PORT}"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((ok, label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def req(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def tele(**over) -> dict:
    base = {
        "device_id": "ess-demo-01", "timestamp": 0, "grid_current_a": 0.073,
        "relay_state": "NC", "threshold_high_a": 0.09, "threshold_low_a": 0.055,
        "hold_remaining_s": 0,
    }
    base.update(over)
    return base


def main() -> int:
    db_path = os.path.join(tempfile.mkdtemp(), "verify_thermal.db")
    env = dict(os.environ, HARDWARE_DB_PATH=db_path)
    env.pop("MQTT_BROKER", None)
    env.pop("BRIDGE_URL", None)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(40):
            try:
                if req("GET", "/api/health")[0] == 200:
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.25)
        else:
            print("서버 기동 실패")
            return 1

        print("\n[1] 온도 + 열 차단 ON 텔레메트리 저장·조회")
        st, _ = req("POST", "/api/telemetry", tele(
            battery_temp_c=51.2, inverter_temp_c=48.7, thermal_lock=True, relay_state="NC"))
        check(st == 200, f"POST /api/telemetry 200 (실제 {st})")
        st, latest = req("GET", "/api/latest?device_id=ess-demo-01")
        check(st == 200, f"GET /api/latest 200 (실제 {st})")
        check(abs((latest.get("battery_temp_c") or 0) - 51.2) < 0.01,
              f"battery_temp_c 보존 (={latest.get('battery_temp_c')})")
        check(abs((latest.get("inverter_temp_c") or 0) - 48.7) < 0.01,
              f"inverter_temp_c 보존 (={latest.get('inverter_temp_c')})")
        check(bool(latest.get("thermal_lock")) is True,
              f"thermal_lock=True 보존 (={latest.get('thermal_lock')})")

        print("\n[2] 온도 없는 텔레메트리 → null 보존 (Sense 미연결 상황)")
        req("POST", "/api/telemetry", tele(thermal_lock=False))
        st, latest2 = req("GET", "/api/latest?device_id=ess-demo-01")
        check(latest2.get("battery_temp_c") is None,
              f"battery_temp_c None 유지 (={latest2.get('battery_temp_c')})")
        check(bool(latest2.get("thermal_lock")) is False,
              f"thermal_lock=False 보존 (={latest2.get('thermal_lock')})")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    failed = [label for ok, label in results if not ok]
    print("\n" + "=" * 56)
    print(f"결과: {len(results) - len(failed)}/{len(results)} 통과")
    for label in failed:
        print(f"  실패: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
