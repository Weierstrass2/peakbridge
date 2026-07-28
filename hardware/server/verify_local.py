"""자동 통합 검증 — 계획서 8절(합숙 전 검증 계획)의 소프트웨어 단독 항목을 자동화.

실기 테스트가 합숙 1일차에 처음이므로, 이 검증이 사실상 최종 검증이다.
서버 기동 → config 검증(422 3종) → mock 시나리오 실행 → 3대 증거 확인까지 한 번에 수행.

실행:
    python verify_local.py

시간축은 --scale로 압축해 돌린다 (검증 자동화 전용). 시연은 항상 1.0 실속도.
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
PORT = int(os.environ.get("VERIFY_PORT", "8011"))
BASE = f"http://127.0.0.1:{PORT}"

# 검증용 압축 시간축: 스케줄 ×0.35, min_hold_s=5
SCALE = 0.35
HOLD_S = 5
RUN_SECONDS = 25

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


def main() -> int:
    db_path = os.path.join(tempfile.mkdtemp(), "verify.db")
    env = dict(os.environ, HARDWARE_DB_PATH=db_path)
    env.pop("MQTT_BROKER", None)
    env.pop("BRIDGE_URL", None)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    mock = None
    try:
        # 서버 기동 대기
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

        print("\n[1] 초기 상태")
        _, cfg = req("GET", "/api/config")
        check(
            cfg["threshold_high_a"] == 0.09 and cfg["threshold_low_a"] == 0.055 and cfg["min_hold_s"] == 30,
            f"시드 config 0.09/0.055/30 (실제 {cfg['threshold_high_a']}/{cfg['threshold_low_a']}/{cfg['min_hold_s']})",
        )
        check(req("GET", "/api/latest")[0] == 404, "텔레메트리 없을 때 /api/latest 404")

        print("\n[2] config 검증 (위반값 → 422 + 한국어 사유)")
        for label, body in [
            ("I_high <= I_low", {"threshold_high_a": 0.05, "threshold_low_a": 0.055, "min_hold_s": 30}),
            ("I_low 음수", {"threshold_high_a": 0.09, "threshold_low_a": -0.01, "min_hold_s": 30}),
            ("hold 4초 (하한 위반)", {"threshold_high_a": 0.09, "threshold_low_a": 0.055, "min_hold_s": 4}),
            ("hold 301초 (상한 위반)", {"threshold_high_a": 0.09, "threshold_low_a": 0.055, "min_hold_s": 301}),
        ]:
            status, payload = req("PUT", "/api/config", body)
            detail = payload.get("detail", "") if isinstance(payload, dict) else str(payload)
            check(status == 422 and isinstance(detail, str) and detail.strip() != "", f"{label} → 422 «{detail[:40]}»")

        status, payload = req("PUT", "/api/config", {"threshold_high_a": 0.09, "threshold_low_a": 0.055, "min_hold_s": HOLD_S})
        check(status == 200 and payload["min_hold_s"] == HOLD_S, f"유효값 저장 → 200 (min_hold_s={HOLD_S})")

        print(f"\n[3] mock 시나리오 실행 ({RUN_SECONDS}초, 시간축 ×{SCALE})")
        mock = subprocess.Popen(
            [sys.executable, "mock_esp32.py", "--url", BASE, "--scale", str(SCALE), "--interval", "0.5"],
            cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(RUN_SECONDS)
        mock.terminate()
        mock_log = mock.communicate(timeout=5)[0] or ""

        _, hist = req("GET", "/api/history?minutes=10")
        _, events = req("GET", "/api/events")
        events = sorted(events, key=lambda e: e["received_at"])
        print(f"  (텔레메트리 {len(hist)}건, 이벤트 {len(events)}건)")

        check(len(hist) > 20, f"텔레메트리 누적 {len(hist)}건")
        check("config 갱신" in mock_log, "mock이 서버 config를 라운드트립 수신")

        print("\n[4] A-2 시나리오 3대 증거")
        trips = [e for e in events if e["from_state"] == "NC" and e["to_state"] == "NO"]
        returns = [e for e in events if e["from_state"] == "NO" and e["to_state"] == "NC"]

        check(
            bool(trips) and trips[0]["grid_current_a"] > 0.09,
            f"① NC→NO 절체 기록 (트리거 전류 {trips[0]['grid_current_a'] if trips else 'N/A'}A > I_high 0.09A)",
        )

        # ② hold 만료(hold_remaining_s == 0) 후에도 NO를 유지하며 전류가 I_low 초과인 샘플
        held = [
            t for t in hist
            if t["relay_state"] == "NO" and t["hold_remaining_s"] == 0 and t["grid_current_a"] > 0.055
        ]
        check(len(held) >= 3, f"② hold 만료 후에도 NO 유지 (해당 샘플 {len(held)}건 — 히스테리시스)")

        check(
            bool(returns) and returns[0]["grid_current_a"] < 0.055,
            f"③ NO→NC 복귀 기록 (복귀 전류 {returns[0]['grid_current_a'] if returns else 'N/A'}A < I_low 0.055A)",
        )

        if returns:
            after = [t for t in hist if t["received_at"] > returns[0]["received_at"] and t["relay_state"] == "NC"]
            rise = max((t["grid_current_a"] for t in after), default=0.0)
            check(rise > 0.055, f"③-b 복귀 직후 계통 전류 상승 (부하3 한전 복귀, 최대 {rise}A)")
        else:
            check(False, "③-b 복귀 직후 전류 상승 — 복귀 이벤트 없음")

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
