"""실기 펌웨어 방식(INA226 복귀 판단) 검증.

`esp32_peak_shaving/peak_shaving_core.ino`의 판단 로직과 서버 스키마가 맞는지 확인한다.

  절체: CT 전류 > I_HIGH(0.090A) 연속 2회      ← CT 담당
  복귀: INA226 전류 < INA_LOW_mA(710) 연속 2회  ← INA226 담당

CT만으로는 "부하3이 꺼진 것"과 "부하3이 ESS로 넘어간 것"을 구분할 수 없기 때문에
두 센서가 방향을 하나씩 전담한다. 이 검증은 그 구분이 실제로 되는지를 본다.

실행:
    python verify_ina.py
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
PORT = int(os.environ.get("VERIFY_INA_PORT", "8015"))
BASE = f"http://127.0.0.1:{PORT}"
RUN_SECONDS = 22

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
        return e.code, json.loads(e.read().decode())


def main() -> int:
    db_path = os.path.join(tempfile.mkdtemp(), "ina.db")
    env = dict(os.environ, HARDWARE_DB_PATH=db_path)
    env.pop("MQTT_BROKER", None)
    env.pop("BRIDGE_URL", None)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    mock = None
    try:
        for _ in range(40):
            try:
                req("GET", "/api/health")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)

        print("\n[1] config 스키마 (실기 확정값)")
        _, cfg = req("GET", "/api/config")
        check(cfg.get("ina_low_ma") == 710.0, f"ina_low_ma 시드 710mA (실제 {cfg.get('ina_low_ma')})")

        status, payload = req("PUT", "/api/config", {
            "threshold_high_a": 0.09, "threshold_low_a": 0.055, "min_hold_s": 5, "ina_low_ma": 30.0,
        })
        check(status == 422, f"ina_low_ma 범위 위반 → 422 «{str(payload.get('detail'))[:44]}»")

        status, payload = req("PUT", "/api/config", {
            "threshold_high_a": 0.09, "threshold_low_a": 0.055, "min_hold_s": 5, "ina_low_ma": 710.0,
        })
        check(status == 200 and payload["ina_low_ma"] == 710.0, "유효 ina_low_ma 저장 → 200")

        print(f"\n[2] mock --return-mode ina 실행 ({RUN_SECONDS}초)")
        mock = subprocess.Popen(
            [sys.executable, "mock_esp32.py", "--url", BASE, "--scale", "0.3",
             "--interval", "0.4", "--return-mode", "ina"],
            cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(RUN_SECONDS)
        mock.terminate()
        log = mock.communicate(timeout=5)[0] or ""

        _, hist = req("GET", "/api/history?minutes=10")
        _, events = req("GET", "/api/events")
        events = sorted(events, key=lambda e: e["received_at"])
        print(f"  (텔레메트리 {len(hist)}건, 이벤트 {len(events)}건)")

        print("\n[3] 두 센서의 역할 분담 확인")
        check(
            all(t.get("ina_current_ma") is not None for t in hist),
            "모든 샘플에 ina_current_ma 기록됨",
        )

        trips = [e for e in events if e["to_state"] == "NO"]
        check(bool(trips) and trips[0]["grid_current_a"] > 0.09, "CT가 절체 판단 (NC→NO, 0.09A 초과)")

        # 복귀 직전 샘플의 INA 전류가 대기 수준(<710mA)이어야 한다
        returns = [e for e in events if e["to_state"] == "NC"]
        if returns:
            at = returns[0]["received_at"]
            near = [t for t in hist if abs(t["received_at"] - at) < 1.0 and t.get("ina_current_ma")]
            ina_vals = [t["ina_current_ma"] for t in near]
            check(bool(ina_vals) and min(ina_vals) < 710.0, f"INA226이 복귀 판단 (복귀 시점 INA {ina_vals})")
        else:
            check(False, "INA226 복귀 이벤트 없음")

        # 절체 유지 구간에서는 공급 수준(>710mA)이 관측돼야 한다 — "부하3이 ESS로 넘어감"의 증거
        supplying = [t for t in hist if t["relay_state"] == "NO" and (t.get("ina_current_ma") or 0) > 710.0]
        check(
            len(supplying) >= 3,
            f"ESS 공급 구간 INA 800mA 수준 관측 {len(supplying)}건 (부하3 이관의 물리 증거)",
        )
        check("복귀 NO→NC (INA" in log, "mock 로그에 INA 기준 복귀 기록")

    finally:
        if mock and mock.poll() is None:
            mock.kill()
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    failed = [label for ok, label in results if not ok]
    print("\n" + "=" * 60)
    print(f"결과: {len(results) - len(failed)}/{len(results)} 통과")
    for label in failed:
        print(f"  실패: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
