"""리스크 엔진 — 거래소·중개사업자의 리스크팀이 보는 계층.

실제 트레이딩 데스크에서 리스크 엔진은 '수익을 내는 곳'이 아니라
**'주문을 막는 곳'**이다. 전략이 아무리 좋아 보여도 한도를 넘으면 주문이 나가지 않는다.

구성:
  1. 한도(Limit) 체계      — 물량·금액·구간집중도·최대손실
  2. 사전 리스크 체크       — 제출 전에 위반 주문을 차단 (pre-trade)
  3. VaR / CVaR            — 과거 손익 분포 기반 하방 위험
  4. 스트레스 시나리오      — 가격 급등, 이행 실패, SOC 급감
  5. 킬스위치              — 누적 손실이 한도를 넘으면 자동 거래 중지

전력시장 특유의 항목은 **이행 리스크(delivery risk)**다.
금융시장은 돈만 있으면 결제되지만, 전력은 실물을 못 내면 위약금을 문다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np

Severity = Literal["ok", "warn", "breach"]


@dataclass
class RiskLimits:
    """운영 한도. 실제 데스크에서는 리스크팀이 정하고 트레이더는 못 바꾼다."""

    max_total_qty_kw: float = 2000.0        # 일 총 응찰 물량 상한
    max_hour_qty_kw: float = 250.0          # 단일 구간 집중 상한 (정격 초과 방지)
    max_notional_won: float = 3_000_000.0   # 일 명목 거래금액 상한
    max_daily_loss_won: float = 150_000.0   # 일 손실 한도 (초과 시 킬스위치)
    max_drawdown_won: float = 500_000.0     # 누적 드로다운 한도
    min_coverage_ratio: float = 1.0         # 낙찰 의무 대비 가용 에너지 비율 하한
    max_concentration: float = 0.45         # 한 구간이 총 물량에서 차지하는 최대 비중
    var_limit_won: float = 120_000.0        # VaR 95% 한도


@dataclass
class RiskCheck:
    code: str
    severity: Severity
    message: str
    value: float
    limit: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RiskState:
    """데스크의 현재 리스크 상태 스냅샷."""

    checks: list[RiskCheck] = field(default_factory=list)
    blocked: bool = False
    kill_switch: bool = False
    reason: str = ""

    @property
    def worst(self) -> Severity:
        if any(c.severity == "breach" for c in self.checks):
            return "breach"
        if any(c.severity == "warn" for c in self.checks):
            return "warn"
        return "ok"

    def to_dict(self) -> dict:
        return {
            "status": self.worst,
            "blocked": self.blocked,
            "kill_switch": self.kill_switch,
            "reason": self.reason,
            "checks": [c.to_dict() for c in self.checks],
        }


def _check(code: str, value: float, limit: float, msg: str,
           warn_ratio: float = 0.85, invert: bool = False) -> RiskCheck:
    """한도 대비 판정. invert=True면 '값이 한도보다 작으면 위반'."""
    if invert:
        sev: Severity = "breach" if value < limit else ("warn" if value < limit * 1.1 else "ok")
    else:
        sev = "breach" if value > limit else ("warn" if value > limit * warn_ratio else "ok")
    return RiskCheck(code=code, severity=sev, message=msg, value=round(value, 1), limit=round(limit, 1))


class RiskEngine:
    """사전 리스크 체크 + 위험지표 산출."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self._kill = False
        self._kill_reason = ""

    # ── 킬스위치 ──
    @property
    def kill_switch(self) -> bool:
        return self._kill

    def trip(self, reason: str) -> None:
        self._kill = True
        self._kill_reason = reason

    def reset(self) -> None:
        self._kill = False
        self._kill_reason = ""

    # ── 사전 리스크 체크 ──
    def pre_trade(self, bids: list[dict], mcp_forecast: list[float],
                  usable_kwh: float, realized_pnl_today: float = 0.0,
                  drawdown: float = 0.0, var95: float = 0.0) -> RiskState:
        """제출 전 검사. breach가 하나라도 있으면 blocked=True."""
        L = self.limits
        qtys = [float(b.get("qty_kw", 0) or 0) for b in bids]
        total = sum(qtys)
        peak = max(qtys) if qtys else 0.0
        notional = sum(
            (b.get("qty_kw", 0) or 0) * (mcp_forecast[int(b["hour"])] if int(b["hour"]) < len(mcp_forecast) else 0)
            for b in bids
        )
        concentration = (peak / total) if total > 0 else 0.0
        coverage = (usable_kwh / total) if total > 0 else 999.0

        checks = [
            _check("QTY_TOTAL", total, L.max_total_qty_kw, "일 총 응찰 물량"),
            _check("QTY_HOUR", peak, L.max_hour_qty_kw, "단일 구간 최대 물량"),
            _check("NOTIONAL", notional, L.max_notional_won, "명목 거래금액"),
        ]

        # 집중도 한도는 '분산할 여지가 있을 때'만 의미가 있다.
        # 가용 에너지가 2구간치도 안 되면 한 구간 집중은 물리적으로 불가피하므로
        # 위반으로 잡지 않는다 (거짓 경보가 반복되면 리스크 경고 전체가 무시된다).
        spreadable = usable_kwh >= (peak * 2) if peak > 0 else True
        if spreadable:
            checks.append(_check("CONCENTRATION", concentration, L.max_concentration, "구간 집중도"))
        else:
            checks.append(RiskCheck(
                code="CONCENTRATION", severity="ok",
                message="구간 집중도 (에너지 부족으로 분산 불가 — 검사 면제)",
                value=round(concentration, 2), limit=L.max_concentration,
            ))

        checks += [
            _check("COVERAGE", coverage, L.min_coverage_ratio, "가용 에너지 커버리지", invert=True),
            _check("DAILY_LOSS", -realized_pnl_today, L.max_daily_loss_won, "당일 실현손실"),
            _check("DRAWDOWN", drawdown, L.max_drawdown_won, "누적 드로다운"),
            _check("VAR95", abs(var95), L.var_limit_won, "VaR 95%"),
        ]

        state = RiskState(checks=checks, kill_switch=self._kill, reason=self._kill_reason)
        breaches = [c for c in checks if c.severity == "breach"]
        if self._kill:
            state.blocked = True
            state.reason = self._kill_reason or "킬스위치 작동 중"
        elif breaches:
            state.blocked = True
            state.reason = " / ".join(f"{c.message} 한도 초과 ({c.value:,.0f} > {c.limit:,.0f})" for c in breaches[:2])
        return state

    # ── 위험지표 ──
    @staticmethod
    def var_cvar(pnl: list[float], alpha: float = 0.05) -> tuple[float, float]:
        """과거 일손익 분포 기반 VaR·CVaR (음수 = 손실)."""
        if len(pnl) < 5:
            return 0.0, 0.0
        arr = np.sort(np.asarray(pnl, dtype=float))
        idx = max(1, int(len(arr) * alpha))
        return float(arr[idx - 1]), float(arr[:idx].mean())

    @staticmethod
    def stress(bids: list[dict], mcp_forecast: list[float], usable_kwh: float,
               degradation_won: float = 50.0, penalty_factor: float = 1.2) -> list[dict]:
        """스트레스 시나리오 — 각 충격에서의 손익을 사전 계산한다.

        실제 데스크의 스트레스 테스트와 같은 목적: "최악이면 얼마 잃는가"를
        주문 내기 전에 숫자로 확인한다.
        """
        def settle(mcp: list[float], energy: float) -> float:
            rev = pen = deg = 0.0
            left = energy
            for b in bids:
                h = int(b["hour"])
                q = float(b.get("qty_kw", 0) or 0)
                p = float(b.get("price", 0) or 0)
                if q <= 0 or h >= len(mcp):
                    continue
                if p > mcp[h]:
                    continue
                d = min(q, left)
                left -= d
                rev += d * mcp[h]
                deg += d * degradation_won
                short = q - d
                if short > 0.5:
                    pen += short * mcp[h] * penalty_factor
            return rev - deg - pen

        base_mcp = list(mcp_forecast)
        scenarios = [
            ("기준", base_mcp, usable_kwh, "예측대로 실현"),
            ("가격 −30%", [p * 0.7 for p in base_mcp], usable_kwh, "수요 급감·연료가 하락"),
            ("가격 +50%", [p * 1.5 for p in base_mcp], usable_kwh, "혹서기 급등 (낙찰 증가)"),
            ("SOC 절반", base_mcp, usable_kwh * 0.5, "충전 실패·자가소비 급증"),
            ("이행 불능", base_mcp, usable_kwh * 0.15, "설비 고장 — 대량 위약"),
            ("복합 충격", [p * 1.4 for p in base_mcp], usable_kwh * 0.4, "가격 급등 + 가용량 급감"),
        ]
        out = []
        for name, mcp, energy, desc in scenarios:
            out.append({
                "scenario": name,
                "description": desc,
                "pnl_won": round(settle(mcp, energy)),
                "energy_kwh": round(energy, 1),
            })
        base = out[0]["pnl_won"]
        for row in out:
            row["delta_won"] = round(row["pnl_won"] - base)
        return out
