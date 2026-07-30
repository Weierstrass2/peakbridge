"""Pydantic 모델 + config 검증 규칙.

검증 규칙은 ESP32 펌웨어와 **동일**하다 (하드웨어 담당 확정).
서버가 거울처럼 같은 규칙으로 먼저 막기 때문에, 서버와 펌웨어의 설정이
서로 다른 상태로 갈라지는 일이 구조적으로 발생할 수 없다.
"""

from typing import Any

from pydantic import BaseModel

# 설정 검증 상수 (펌웨어와 동일)
MIN_HOLD_LOWER_S = 5
MIN_HOLD_UPPER_S = 300
# INA226 복귀 기준 범위. 상한은 사용 중인 R100 션트 모듈의 측정 상한(~819mA)을 넘어
# R010 모듈로 교체할 경우(8.2A)까지 허용한다.
INA_LOW_LOWER_MA = 50.0
INA_LOW_UPPER_MA = 8200.0


class TelemetryIn(BaseModel):
    """ESP32 → 서버 텔레메트리. v1 필수 + v2 옵셔널(INA226 확장 자리)."""

    # v1 (필수)
    device_id: str
    timestamp: int  # epoch 초. NTP 미동기 시 0으로 올 수 있음 — 그대로 보존한다.
    grid_current_a: float
    relay_state: str  # "NC" | "NO"
    threshold_high_a: float
    threshold_low_a: float
    hold_remaining_s: int

    # v2 (옵셔널 — 미장착 시 null)
    battery_voltage_v: float | None = None
    ess_current_a: float | None = None
    ess_power_w: float | None = None

    # v3 (옵셔널 — 실기 펌웨어 peak_shaving_core.ino의 복귀 판단 센서)
    # INA226이 측정한 배터리→인버터 전류(mA). 복귀는 이 값이 ina_low_ma 아래로
    # 연속 2회 떨어질 때 일어난다 (CT만으로는 '부하3 꺼짐'과 '부하3 ESS 이관'을 구분할 수 없음).
    ina_current_ma: float | None = None

    # v4 (옵셔널 — XIAO 펌웨어의 쿨롱 카운팅 SOC)
    # 펌웨어가 INA219 전류를 시간 적분해 계산한 SOC(%)와 잔여 가동시간(h).
    # 전압 단독 SOC보다 정확(LiFePO4 평평 구간 대응). 브리지가 아파트 대시보드로 전달.
    battery_soc: float | None = None
    remain_hours: float | None = None

    # v5 (옵셔널 — Sense 보드 BME280 온도 + 메인 보드 열 차단 상태)
    # 메인 보드가 sense_telemetry로 받은 온도를 자기 텔레메트리에 실어 재발행한다.
    # 온도 판정(트립/해제)은 펌웨어가 로컬로 하고, 서버는 표시·기록만 한다.
    battery_temp_c: float | None = None
    inverter_temp_c: float | None = None
    thermal_lock: bool | None = None


class ConfigModel(BaseModel):
    threshold_high_a: float
    threshold_low_a: float
    min_hold_s: int
    ina_low_ma: float
    updated_at: float


class ConfigUpdate(BaseModel):
    threshold_high_a: float
    threshold_low_a: float
    min_hold_s: int
    # 미지정 시 기존 저장값을 유지한다 (구버전 클라이언트 호환)
    ina_low_ma: float | None = None


class TelemetryResponse(BaseModel):
    """POST /api/telemetry 응답.

    응답 body에 현재 config를 실어 보낸다 — ESP32가 별도 폴링 없이
    최신 임계값을 받아가는 HTTP 폴백 경로의 핵심.
    """

    ok: bool
    config: ConfigModel


class TelemetryRecord(BaseModel):
    id: int
    device_id: str
    timestamp: int
    received_at: float
    grid_current_a: float
    relay_state: str
    threshold_high_a: float
    threshold_low_a: float
    hold_remaining_s: int
    battery_voltage_v: float | None = None
    ess_current_a: float | None = None
    ess_power_w: float | None = None
    ina_current_ma: float | None = None
    battery_soc: float | None = None
    remain_hours: float | None = None
    battery_temp_c: float | None = None
    inverter_temp_c: float | None = None
    thermal_lock: bool | None = None


class EventRecord(BaseModel):
    id: int
    device_id: str
    from_state: str
    to_state: str
    timestamp: int
    received_at: float
    grid_current_a: float


def validate_config(
    threshold_high_a: float, threshold_low_a: float, min_hold_s: int, ina_low_ma: float | None = None
) -> str | None:
    """설정 검증. 통과하면 None, 위반하면 한국어 사유 문자열을 반환.

    펌웨어와 동일 규칙:
      - threshold_high_a > threshold_low_a > 0
      - 5 <= min_hold_s <= 300
      - 50 <= ina_low_ma <= 8200 (지정된 경우)
    """
    if threshold_low_a <= 0:
        return f"복귀 임계값(I_low)은 0보다 커야 합니다. 입력값: {threshold_low_a}A"
    if threshold_high_a <= threshold_low_a:
        return (
            "절체 임계값(I_high)은 복귀 임계값(I_low)보다 커야 합니다. "
            f"입력값: I_high={threshold_high_a}A, I_low={threshold_low_a}A"
        )
    if min_hold_s < MIN_HOLD_LOWER_S or min_hold_s > MIN_HOLD_UPPER_S:
        return (
            f"최소 유지시간(min_hold_s)은 {MIN_HOLD_LOWER_S}~{MIN_HOLD_UPPER_S}초 범위여야 합니다. "
            f"입력값: {min_hold_s}초"
        )
    if ina_low_ma is not None and not (INA_LOW_LOWER_MA <= ina_low_ma <= INA_LOW_UPPER_MA):
        return (
            f"INA226 복귀 기준(ina_low_ma)은 {INA_LOW_LOWER_MA:.0f}~{INA_LOW_UPPER_MA:.0f}mA "
            f"범위여야 합니다. 입력값: {ina_low_ma}mA"
        )
    return None


def config_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    """ESP32에게 내보내는 config 페이로드 (HTTP 응답 / MQTT retained 공통)."""
    return {
        "threshold_high_a": cfg["threshold_high_a"],
        "threshold_low_a": cfg["threshold_low_a"],
        "min_hold_s": cfg["min_hold_s"],
        "ina_low_ma": cfg["ina_low_ma"],
        "updated_at": cfg["updated_at"],
    }
