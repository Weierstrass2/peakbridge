"""
포트폴리오 자원 물리 모델 — 단일 레지스트리 (Single Source of Truth).

입찰 검증(market) · 급전 이행(dispatch) · AI 학습 환경(A3)이
전부 이 정의를 참조한다. 값 변경은 여기서만.
"""

from __future__ import annotations

RESOURCES: dict[str, dict] = {
    "building-A": {
        "type": "ess",
        "name": "실증단지 A — 묶음 ESS",
        "live": True,                     # 실측 연동 (CT/INA219)
        "capacity_kwh": 100.0,
        "max_charge_kw": 50.0,
        "max_discharge_kw": 50.0,
        "soc_min": 20.0,                  # 운영 하한 (%)
        "soc_max": 85.0,                  # 운영 상한 — 열화 보호
        "round_trip_eff": 0.90,
        "ramp_kw_per_min": 50.0,          # 인버터 즉응 — 정격/분
        "min_run_min": 0,
        "min_off_min": 0,
        "response_time_s": 1.0,           # FR급 → AS 시장 확장 근거
        "degradation_won_per_kwh": 50.0,  # 열화 비용 (보상함수 차감항)
        "as_capable": True,
    },
    "building-B": {
        "type": "ess", "name": "단지 B — 묶음 ESS", "live": False,
        "capacity_kwh": 200.0, "max_charge_kw": 100.0, "max_discharge_kw": 100.0,
        "soc_min": 20.0, "soc_max": 85.0, "round_trip_eff": 0.90,
        "ramp_kw_per_min": 100.0, "min_run_min": 0, "min_off_min": 0,
        "response_time_s": 1.0, "degradation_won_per_kwh": 50.0, "as_capable": True,
    },
    "building-C": {
        "type": "ess", "name": "단지 C — 묶음 ESS", "live": False,
        "capacity_kwh": 150.0, "max_charge_kw": 75.0, "max_discharge_kw": 75.0,
        "soc_min": 20.0, "soc_max": 85.0, "round_trip_eff": 0.90,
        "ramp_kw_per_min": 75.0, "min_run_min": 0, "min_off_min": 0,
        "response_time_s": 1.0, "degradation_won_per_kwh": 50.0, "as_capable": True,
    },
    "building-A-dr": {
        "type": "dr", "name": "실증단지 A — 충전기 DR", "live": True,
        "shed_kw": 7.0,                   # 충전기 1대 기준 (대수 × 7kW)
        "max_duration_min": 60,           # 수용성 제약
        "daily_limit": 2,
        "response_time_s": 10.0,
        "rebound_factor": 0.3,            # 종료 후 보상수요
        "as_capable": False,
    },
    # PV 슬롯 (미구현 — 확장 예약): type "pv", curtailable only
}

# 시장 규칙 (KPX 문법)
MARKET_RULES = {
    "price_cap": 300.0,        # 입찰 상한가 ₩/kWh (SMP cap 모사)
    "min_bid_unit_kw": 10.0,   # 최소 입찰 단위
    "cp_rate": 8.0,            # 용량요금 CP ₩/kWh (신고 용량 기준)
    "penalty_factor": 1.2,     # 미이행 위약 계수 (부족분 × MCP × 1.2)
}


def total_max_discharge_kw() -> float:
    return sum(
        r["max_discharge_kw"] for r in RESOURCES.values() if r["type"] == "ess"
    )


def ess_resources() -> dict[str, dict]:
    return {k: v for k, v in RESOURCES.items() if v["type"] == "ess"}
