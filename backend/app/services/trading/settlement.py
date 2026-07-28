"""정산 검증 (Shadow Settlement) — 거래소 정산서를 그대로 믿지 않는다.

중개사업자의 실질적 존재 이유 중 하나다. 거래소·한전이 보내온 정산 내역과
우리가 계측·기록한 값으로 독립 계산한 결과를 **항목별로 대조**해,
차이가 허용오차를 넘으면 이의신청 근거를 만든다.

단지 입장에서 이 기능의 의미는 분명하다:
    "우리가 제대로 정산받고 있는지 검증해 주는 사업자"

대조 항목:
    energy_revenue  에너지 정산금 (낙찰량 × MCP)
    capacity_payment 용량요금
    penalty         미이행 위약금
    total           합계

판정:
    match     차이가 허용오차 이내
    minor     허용오차 초과하지만 소액 (기록만)
    dispute   금액·비율 모두 유의미 → 이의신청 대상
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

# 허용오차: 반올림·계량 오차 수준까지는 정상으로 본다
TOL_RATIO = 0.005      # 0.5% — 계량·반올림 오차 범위
TOL_ABS_WON = 100.0    # 절대 허용액 (실증 규모 기준. 상용에서는 상향)
# 이의신청 기준: 비율이 크면 금액이 작아도 계통적 오류이므로 dispute로 본다
DISPUTE_RATIO = 0.02        # 2% 이상 어긋나면 구조적 오류로 판단
DISPUTE_MIN_WON = 2_000.0   # 또는 절대 실익이 이 금액 이상일 때


@dataclass
class LineCheck:
    item: str
    label: str
    ours_won: float
    theirs_won: float

    @property
    def diff(self) -> float:
        return self.theirs_won - self.ours_won      # 음수 = 우리가 덜 받음

    @property
    def ratio(self) -> float:
        base = abs(self.ours_won) or 1e-9
        return self.diff / base

    @property
    def verdict(self) -> str:
        if abs(self.diff) <= max(TOL_ABS_WON, abs(self.ours_won) * TOL_RATIO):
            return "match"
        # 비율이 크면 소액이라도 계통적 오류 — 반복되면 큰 금액이 된다
        if abs(self.ratio) >= DISPUTE_RATIO or abs(self.diff) >= DISPUTE_MIN_WON:
            return "dispute"
        return "minor"

    def to_dict(self) -> dict:
        return {
            "item": self.item,
            "label": self.label,
            "ours_won": round(self.ours_won),
            "theirs_won": round(self.theirs_won),
            "diff_won": round(self.diff),
            "diff_pct": round(self.ratio * 100, 2),
            "verdict": self.verdict,
        }


def own_settlement(awarded: list[dict], delivered_kwh_by_hour: dict[int, float],
                   mcp: list[float], cp_rate: float = 8.0,
                   penalty_factor: float = 1.2) -> dict:
    """우리 계측 기록으로 독립 계산한 정산 내역."""
    energy = capacity = penalty = 0.0
    for row in awarded:
        h = int(row["hour"])
        q = float(row.get("qty_kw", 0) or 0)
        if q <= 0:
            continue
        d = float(delivered_kwh_by_hour.get(h, 0.0))
        capacity += q * cp_rate
        energy += d * mcp[h]
        short = max(0.0, q - d)
        if short > 0.5:
            penalty += short * mcp[h] * penalty_factor
    return {
        "energy_revenue": round(energy, 1),
        "capacity_payment": round(capacity, 1),
        "penalty": round(penalty, 1),
        "total": round(energy + capacity - penalty, 1),
    }


def reconcile(ours: dict, theirs: dict) -> dict:
    """항목별 대조 결과 + 종합 판정."""
    labels = {
        "energy_revenue": "에너지 정산금",
        "capacity_payment": "용량요금",
        "penalty": "위약금",
        "total": "합계",
    }
    checks = [
        LineCheck(k, labels[k], float(ours.get(k, 0.0)), float(theirs.get(k, 0.0)))
        for k in labels
    ]
    disputes = [c for c in checks if c.verdict == "dispute"]
    minors = [c for c in checks if c.verdict == "minor"]

    total = next(c for c in checks if c.item == "total")
    status = "dispute" if disputes else ("minor" if minors else "match")

    return {
        "status": status,
        "checks": [c.to_dict() for c in checks],
        "underpaid_won": round(-total.diff) if total.diff < 0 else 0,
        "overpaid_won": round(total.diff) if total.diff > 0 else 0,
        "dispute_items": [c.item for c in disputes],
        "summary": (
            f"이의신청 대상 {len(disputes)}건 — 합계 차이 ₩{total.diff:,.0f}"
            if disputes else
            "경미한 차이 — 기록만 남김" if minors else
            "정산서와 자체 계산 일치"
        ),
        "tolerance": {"ratio_pct": TOL_RATIO * 100, "abs_won": TOL_ABS_WON},
    }


def simulate_statement(ours: dict, error_mode: str = "none", seed: int = 11) -> dict:
    """거래소 정산서 시뮬레이터 — 실제 연동 전 검증용.

    실무에서 자주 보이는 오류 유형을 재현한다.
        none        정상 (반올림 오차만)
        underpay    에너지 정산금 누락 (계량값 절사)
        penalty_over 위약금 과다 부과
        capacity_miss 용량요금 일부 미지급
    """
    import random

    rng = random.Random(seed)
    out = {k: float(v) for k, v in ours.items()}
    jitter = lambda v: v * (1 + rng.uniform(-0.002, 0.002))  # noqa: E731

    if error_mode == "underpay":
        out["energy_revenue"] *= 0.94          # 6% 누락
    elif error_mode == "penalty_over":
        out["penalty"] *= 1.35                 # 위약금 35% 과다
    elif error_mode == "capacity_miss":
        out["capacity_payment"] *= 0.8         # 용량요금 20% 미지급

    for k in ("energy_revenue", "capacity_payment", "penalty"):
        out[k] = round(jitter(out[k]), 1)
    out["total"] = round(out["energy_revenue"] + out["capacity_payment"] - out["penalty"], 1)
    return out
