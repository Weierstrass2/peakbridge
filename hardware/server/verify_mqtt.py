"""MQTT 경로 자동 검증 (계획서 8절 5번).

mosquitto가 없는 개발 환경에서도 MQTT 파이프라인을 검증할 수 있도록
순수 파이썬 브로커(amqtt)를 임시 기동해 다음을 확인한다:

  1. 서버가 브로커에 접속하고 telemetry 토픽을 구독한다
  2. mock이 발행한 텔레메트리가 **HTTP와 동일한 저장 함수**로 DB에 들어간다
  3. PUT /api/config → config 토픽으로 retained·QoS1 재발행
  4. 나중에 접속한 구독자도 retained config를 즉시 수신한다 (ESP32 재부팅 시나리오)

실행:
    pip install amqtt --break-system-packages
    python verify_mqtt.py

합숙 현장에서는 mosquitto로 동일 검증을 다시 수행할 것 (README 체크리스트 참조).
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BROKER_PORT = 1884
API_PORT = 8013
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


def api(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    import paho.mqtt.client as mqtt

    db_path = os.path.join(tempfile.mkdtemp(), "mqtt.db")
    procs: list[subprocess.Popen] = []

    broker_py = os.path.join(tempfile.mkdtemp(), "broker.py")
    with open(broker_py, "w", encoding="utf-8") as f:
        f.write(BROKER_SCRIPT)

    try:
        print("\n[1] 브로커·서버 기동")
        procs.append(subprocess.Popen([sys.executable, broker_py], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(2.5)

        env = dict(
            os.environ,
            HARDWARE_DB_PATH=db_path,
            MQTT_BROKER="127.0.0.1",
            MQTT_PORT=str(BROKER_PORT),
        )
        env.pop("BRIDGE_URL", None)
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
                cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
        )

        health = None
        for _ in range(40):
            try:
                health = api("GET", "/api/health")[1]
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        time.sleep(2)  # MQTT 접속 완료 대기
        health = api("GET", "/api/health")[1]
        check(health["mqtt"]["enabled"] and health["mqtt"]["connected"], f"서버 MQTT 접속: {health['mqtt']}")

        print("\n[2] mock --mqtt 발행 → DB 저장 (HTTP와 동일 저장 경로)")
        procs.append(
            subprocess.Popen(
                [sys.executable, "mock_esp32.py", "--mqtt", "127.0.0.1", "--mqtt-port", str(BROKER_PORT),
                 "--scale", "0.2", "--interval", "0.4"],
                cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
        )
        time.sleep(6)
        _, hist = api("GET", "/api/history?minutes=10")
        check(len(hist) >= 5, f"MQTT 텔레메트리 {len(hist)}건 저장됨")

        print("\n[3] config retained 발행")
        status, cfg = api("PUT", "/api/config", {"threshold_high_a": 0.088, "threshold_low_a": 0.05, "min_hold_s": 7})
        check(status == 200, "PUT /api/config 200")
        time.sleep(1)

        # 나중에 접속한 신규 구독자가 retained config를 즉시 받는지 (ESP32 재부팅 시나리오)
        got: dict = {}
        try:
            sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            sub = mqtt.Client()
        sub.on_connect = lambda c, u, f, rc, *a: c.subscribe("peakbridge/demo/config", qos=1)
        sub.on_message = lambda c, u, msg: got.update(json.loads(msg.payload.decode()))
        sub.connect("127.0.0.1", BROKER_PORT, 60)
        sub.loop_start()
        time.sleep(3)
        sub.loop_stop()
        check(
            got.get("threshold_high_a") == 0.088 and got.get("min_hold_s") == 7,
            f"신규 구독자가 retained config 즉시 수신: {got or '수신 없음'}",
        )

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
