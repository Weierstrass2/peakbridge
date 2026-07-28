"""구성 B(팀원A 3-노드) 흡수 검증.

두 구성이 **하나의 브로커·하나의 서버·하나의 DB**에서 동시에 살아 있는지 확인한다:

  1. peakbridge/building-A/grid/current  → building-A 디바이스로 저장
  2. peakbridge/building-A/ess/soc        → 다음 grid 샘플에 v2 필드(전압/전류/전력)로 합류
  3. control/relay/ack {"action":"discharge"} → NO 절체 이벤트 기록
     control/relay/ack {"action":"standby"}   → NC 복귀 이벤트 기록
  4. 동시에 구성 A(ess-demo-01)도 들어와 두 디바이스가 /api/devices 에 함께 보인다

실행:
    pip install amqtt --break-system-packages
    python verify_legacy.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BROKER_PORT = 1885
API_PORT = 8014
BASE = f"http://127.0.0.1:{API_PORT}"

BROKER_SCRIPT = """
import asyncio, logging
from amqtt.broker import Broker
logging.basicConfig(level=logging.WARNING)
config = {
    "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:%d", "max_connections": 50}},
    "sys_interval": 0,
    "auth": {"allow-anonymous": True},
}
async def main():
    broker = Broker(config)
    await broker.start()
    await asyncio.Event().wait()
asyncio.run(main())
""" % BROKER_PORT

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((ok, label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def api(path: str):
    with urllib.request.urlopen(BASE + path, timeout=5) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    import paho.mqtt.client as mqtt

    db_path = os.path.join(tempfile.mkdtemp(), "legacy.db")
    broker_py = os.path.join(tempfile.mkdtemp(), "broker.py")
    with open(broker_py, "w", encoding="utf-8") as f:
        f.write(BROKER_SCRIPT)

    procs: list[subprocess.Popen] = []
    try:
        print("\n[1] 브로커·서버 기동 (레거시 어댑터 ON)")
        procs.append(subprocess.Popen([sys.executable, broker_py], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(2.5)

        env = dict(
            os.environ,
            HARDWARE_DB_PATH=db_path,
            MQTT_BROKER="127.0.0.1",
            MQTT_PORT=str(BROKER_PORT),
            LEGACY_THRESHOLD_HIGH_A="20.0",
            LEGACY_THRESHOLD_LOW_A="15.0",
        )
        env.pop("BRIDGE_URL", None)
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
                cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
        )
        for _ in range(40):
            try:
                api("/api/health")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        time.sleep(2)
        health = api("/api/health")
        check(health["mqtt"]["connected"] and health["legacy_adapter"], "MQTT 접속 + 레거시 어댑터 활성")

        try:
            pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            pub = mqtt.Client()
        pub.connect("127.0.0.1", BROKER_PORT, 60)
        pub.loop_start()

        def send(topic: str, body: dict) -> None:
            pub.publish(topic, json.dumps(body), qos=0)
            time.sleep(0.6)

        print("\n[2] 3-노드 메시지 발행 (팀원A README 형식 그대로)")
        send("peakbridge/building-A/grid/current",
             {"value": 18.4, "unit": "A", "device_id": "esp32-grid-01", "building_id": "building-A"})
        send("peakbridge/building-A/ess/soc",
             {"value": 72.0, "unit": "%", "voltage": 3.45, "current": -2.3,
              "device_id": "esp32-ess-01", "building_id": "building-A"})
        send("peakbridge/building-A/grid/current",
             {"value": 21.7, "unit": "A", "device_id": "esp32-grid-01", "building_id": "building-A"})

        latest = api("/api/latest?device_id=building-A")
        check(latest["grid_current_a"] == 21.7, f"grid/current 저장 (전류 {latest['grid_current_a']}A)")
        check(
            latest["battery_voltage_v"] == 3.45 and latest["ess_current_a"] == -2.3,
            f"ess/soc 합류 — 전압 {latest['battery_voltage_v']}V / 전류 {latest['ess_current_a']}A / 전력 {latest['ess_power_w']}W",
        )
        check(latest["threshold_high_a"] == 20.0, "레거시 임계값 환경변수 반영 (20.0A)")

        print("\n[3] 릴레이 ack → 절체/복귀 이벤트")
        send("peakbridge/building-A/control/relay/ack",
             {"status": "ok", "action": "discharge", "device_id": "esp32-relay-01"})
        send("peakbridge/building-A/grid/current",
             {"value": 12.1, "unit": "A", "device_id": "esp32-grid-01", "building_id": "building-A"})
        send("peakbridge/building-A/control/relay/ack",
             {"status": "ok", "action": "standby", "device_id": "esp32-relay-01"})

        events = api("/api/events?device_id=building-A")
        events = sorted(events, key=lambda e: e["received_at"])
        pairs = [(e["from_state"], e["to_state"]) for e in events]
        check(("NC", "NO") in pairs, f"discharge ack → NC→NO 절체 기록 (이벤트 {pairs})")
        check(("NO", "NC") in pairs, f"standby ack → NO→NC 복귀 기록 (이벤트 {pairs})")

        print("\n[4] 구성 A와 동시 공존")
        procs.append(
            subprocess.Popen(
                [sys.executable, "mock_esp32.py", "--mqtt", "127.0.0.1", "--mqtt-port", str(BROKER_PORT),
                 "--scale", "0.2", "--interval", "0.4"],
                cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
        )
        time.sleep(5)
        devices = {d["device_id"]: d["samples"] for d in api("/api/devices")}
        check(
            "building-A" in devices and "ess-demo-01" in devices,
            f"두 구성 동시 수신: {devices}",
        )

        demo_latest = api("/api/latest?device_id=ess-demo-01")
        check(
            demo_latest["threshold_high_a"] == 0.09 and latest["threshold_high_a"] == 20.0,
            "디바이스별 임계값이 서로 섞이지 않음 (demo 0.09A / building-A 20.0A)",
        )
        pub.loop_stop()

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
