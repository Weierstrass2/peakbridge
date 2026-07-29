"""SQLite 저장 계층 (stdlib sqlite3만 사용 — 라즈베리파이 이식성).

설계 원칙:
- SQLAlchemy 금지. 파이에 추가 의존성을 만들지 않는다.
- 시간은 전부 received_at(서버 UTC epoch) 기준으로 정렬·조회한다.
  ESP32의 timestamp는 NTP 미동기 시 0으로 올 수 있으며, 0을 그대로 보존한다.
  (절대 서버 시각으로 바꿔치기하지 말 것 — 하드웨어 담당 확정 사항)
- HTTP 경로와 MQTT 경로가 반드시 동일한 저장 함수(save_telemetry)를 공유한다.
  이벤트 감지 로직이 두 벌 존재하면 현장에서 불일치가 생긴다.
"""

import os
import sqlite3
import threading
import time
from typing import Any

DB_PATH = os.environ.get(
    "HARDWARE_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "peakbridge_hardware.db"),
)

# 시드 설정값 (계획서 확정: 0.09A / 0.055A / 30s)
SEED_THRESHOLD_HIGH_A = 0.09
SEED_THRESHOLD_LOW_A = 0.055
SEED_MIN_HOLD_S = 30
# 실기 펌웨어(peak_shaving_core.ino) 복귀 기준: INA226 전류(mA).
# 실측 대기 ~626mA / 공급 ~800mA의 중간값 710을 확정값으로 사용한다.
SEED_INA_LOW_MA = 710.0

# sqlite 쓰기 직렬화용 락 (MQTT 스레드 + HTTP 스레드 동시 접근 대비)
_write_lock = threading.Lock()


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """기존 DB 파일을 지우지 않고 컬럼을 덧붙인다 (시연 중 데이터 손실 방지)."""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """스키마 생성 + config 싱글턴 시드 보장. 기동 시 1회 호출."""
    with _write_lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    received_at REAL NOT NULL,
                    grid_current_a REAL NOT NULL,
                    relay_state TEXT NOT NULL,
                    threshold_high_a REAL NOT NULL,
                    threshold_low_a REAL NOT NULL,
                    hold_remaining_s INTEGER NOT NULL,
                    battery_voltage_v REAL,
                    ess_current_a REAL,
                    ess_power_w REAL
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_device_received
                    ON telemetry (device_id, received_at);

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    received_at REAL NOT NULL,
                    grid_current_a REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_device_received
                    ON events (device_id, received_at);

                CREATE TABLE IF NOT EXISTS config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    threshold_high_a REAL NOT NULL,
                    threshold_low_a REAL NOT NULL,
                    min_hold_s INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            # 마이그레이션: 실기 펌웨어(INA226 복귀 판단) 대응 컬럼을 나중에 추가했다.
            _add_column_if_missing(conn, "telemetry", "ina_current_ma", "REAL")
            _add_column_if_missing(conn, "config", "ina_low_ma", f"REAL NOT NULL DEFAULT {SEED_INA_LOW_MA}")
            # 마이그레이션: XIAO 쿨롱 카운팅 SOC(%)·잔여 가동시간(h)
            _add_column_if_missing(conn, "telemetry", "battery_soc", "REAL")
            _add_column_if_missing(conn, "telemetry", "remain_hours", "REAL")

            conn.execute(
                """
                INSERT OR IGNORE INTO config (id, threshold_high_a, threshold_low_a, min_hold_s, ina_low_ma, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    SEED_THRESHOLD_HIGH_A,
                    SEED_THRESHOLD_LOW_A,
                    SEED_MIN_HOLD_S,
                    SEED_INA_LOW_MA,
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_config() -> dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT threshold_high_a, threshold_low_a, min_hold_s, ina_low_ma, updated_at FROM config WHERE id = 1"
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_config(
    threshold_high_a: float, threshold_low_a: float, min_hold_s: int, ina_low_ma: float
) -> dict[str, Any]:
    """검증은 호출 측(main.py)에서 이미 끝난 상태로 들어온다."""
    now = time.time()
    with _write_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE config
                SET threshold_high_a = ?, threshold_low_a = ?, min_hold_s = ?, ina_low_ma = ?, updated_at = ?
                WHERE id = 1
                """,
                (threshold_high_a, threshold_low_a, min_hold_s, ina_low_ma, now),
            )
            conn.commit()
        finally:
            conn.close()
    return get_config()


def save_telemetry(payload: dict[str, Any]) -> dict[str, Any]:
    """텔레메트리 1건 저장 + relay_state 변화 시 events 파생 기록.

    HTTP 핸들러와 MQTT 게이트웨이가 **공유하는 유일한 저장 경로**.
    반환: {"telemetry_id": int, "event": dict | None}
    """
    received_at = time.time()
    device_id = payload["device_id"]
    relay_state = payload["relay_state"]
    grid_current_a = payload["grid_current_a"]

    with _write_lock:
        conn = _connect()
        try:
            prev = conn.execute(
                """
                SELECT relay_state FROM telemetry
                WHERE device_id = ?
                ORDER BY received_at DESC, id DESC
                LIMIT 1
                """,
                (device_id,),
            ).fetchone()

            cur = conn.execute(
                """
                INSERT INTO telemetry (
                    device_id, timestamp, received_at, grid_current_a, relay_state,
                    threshold_high_a, threshold_low_a, hold_remaining_s,
                    battery_voltage_v, ess_current_a, ess_power_w, ina_current_ma,
                    battery_soc, remain_hours
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    payload["timestamp"],
                    received_at,
                    grid_current_a,
                    relay_state,
                    payload["threshold_high_a"],
                    payload["threshold_low_a"],
                    payload["hold_remaining_s"],
                    payload.get("battery_voltage_v"),
                    payload.get("ess_current_a"),
                    payload.get("ess_power_w"),
                    payload.get("ina_current_ma"),
                    payload.get("battery_soc"),
                    payload.get("remain_hours"),
                ),
            )
            telemetry_id = cur.lastrowid

            event = None
            if prev is not None and prev["relay_state"] != relay_state:
                ev = conn.execute(
                    """
                    INSERT INTO events (device_id, from_state, to_state, timestamp, received_at, grid_current_a)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        prev["relay_state"],
                        relay_state,
                        payload["timestamp"],
                        received_at,
                        grid_current_a,
                    ),
                )
                event = {
                    "id": ev.lastrowid,
                    "device_id": device_id,
                    "from_state": prev["relay_state"],
                    "to_state": relay_state,
                    "timestamp": payload["timestamp"],
                    "received_at": received_at,
                    "grid_current_a": grid_current_a,
                }

            conn.commit()
        finally:
            conn.close()

    return {"telemetry_id": telemetry_id, "event": event}


def get_latest(device_id: str | None = None) -> dict[str, Any] | None:
    conn = _connect()
    try:
        if device_id:
            row = conn.execute(
                "SELECT * FROM telemetry WHERE device_id = ? ORDER BY received_at DESC, id DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM telemetry ORDER BY received_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_history(minutes: int = 10, device_id: str | None = None) -> list[dict[str, Any]]:
    """received_at 기준 최근 구간. 오래된 것부터(오름차순) 반환 — 차트 입력용."""
    since = time.time() - minutes * 60
    conn = _connect()
    try:
        if device_id:
            rows = conn.execute(
                """
                SELECT * FROM telemetry
                WHERE device_id = ? AND received_at >= ?
                ORDER BY received_at ASC, id ASC
                """,
                (device_id, since),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM telemetry WHERE received_at >= ? ORDER BY received_at ASC, id ASC",
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_devices() -> list[dict[str, Any]]:
    """수신 이력이 있는 디바이스 목록 (구성 A의 ess-demo-01, 구성 B의 building-A 등)."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT device_id, COUNT(*) AS samples, MAX(received_at) AS last_seen
            FROM telemetry
            GROUP BY device_id
            ORDER BY last_seen DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_events(limit: int = 100, device_id: str | None = None) -> list[dict[str, Any]]:
    """최신순 반환."""
    conn = _connect()
    try:
        if device_id:
            rows = conn.execute(
                """
                SELECT * FROM events WHERE device_id = ?
                ORDER BY received_at DESC, id DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY received_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
