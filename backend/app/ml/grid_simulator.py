"""
pandapower 기반 아파트 단지 배전망 시뮬레이터.

IEEE 33-bus 방식의 방사형(radial) 배전 구조를 아파트 단지 규모로 축소해
변압기 부하율과 PeakBridge(묶음 ESS 방전) 적용 전후 효과를 계산합니다.
pandapower 미설치/조류계산 실패 시 해석적 계산으로 폴백합니다 (500 금지).
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── 모델 가정 (시연 스케일, 발표 자료와 일치시킬 것) ──────────────
HOUSEHOLDS = 50          # 단지 세대 수
FEEDERS = 4              # 동(피더) 수
EV_CHARGER_KW = 7.0      # EV 충전기 1대 정격 (kW)
ESS_UNITS = 20           # 묶음 ESS 유닛 수 (PPO 학습 환경과 동일)
POWER_FACTOR = 0.95      # 역률
LOAD_DIVERSITY = 0.31    # 실측 그리드 전류를 단지 동시부하로 환산하는 계수

OVERLOAD_PCT = 100.0     # 과부하 기준 (%)
WARNING_PCT = 80.0       # 경고 기준 (%)


def _status_of(loading_percent: float) -> str:
    if loading_percent >= OVERLOAD_PCT:
        return "과부하"
    if loading_percent >= WARNING_PCT:
        return "경고"
    return "정상"


class GridSimulator:
    """아파트 단지 변압기/배전망 시뮬레이터."""

    def __init__(self) -> None:
        self._pp: Any = None
        self._available: bool | None = None

    # ── pandapower 지연 로드 ──────────────────────────────
    def _pandapower(self) -> Any:
        if self._available is None:
            try:
                import pandapower as pp

                self._pp = pp
                self._available = True
                logger.info("pandapower_loaded", version=pp.__version__)
            except Exception as exc:  # pragma: no cover
                self._available = False
                logger.warning("pandapower_unavailable", error=str(exc))
        return self._pp if self._available else None

    # ── 부하 산정 ─────────────────────────────────────────
    @staticmethod
    def _loads_kw(grid_current: float, ev_count: int) -> tuple[float, float]:
        """세대 대표 전류(A) → 단지 기본 부하, EV 충전 부하 (kW)."""
        # grid_current는 단지 전체 계통에서 관측된 대표 전류로 보고,
        # 세대 수 전체를 그대로 곱하지 않고 동시 사용률(diversity)을 반영한다.
        base_kw = max(0.0, grid_current) * 0.220 * HOUSEHOLDS * LOAD_DIVERSITY
        ev_kw = max(0, ev_count) * EV_CHARGER_KW
        return base_kw, ev_kw

    # ── pandapower 네트워크 구성 ──────────────────────────
    def _build_net(
        self,
        pp: Any,
        base_kw: float,
        ev_kw: float,
        ess_kw: float,
        transformer_kva: float,
    ) -> Any:
        net = pp.create_empty_network(name="apartment")
        hv = pp.create_bus(net, vn_kv=22.9, name="한전 계통")
        lv = pp.create_bus(net, vn_kv=0.4, name="단지 주배전반")
        pp.create_ext_grid(net, hv, vm_pu=1.0)
        pp.create_transformer_from_parameters(
            net,
            hv,
            lv,
            sn_mva=transformer_kva / 1000.0,
            vn_hv_kv=22.9,
            vn_lv_kv=0.4,
            vkr_percent=1.2,
            vk_percent=4.0,
            pfe_kw=0.5,
            i0_percent=0.2,
            name="단지 변압기",
        )
        q_ratio = 0.329  # pf 0.95 기준 q/p

        per_feeder_mw = base_kw / FEEDERS / 1000.0
        for i in range(FEEDERS):
            bus = pp.create_bus(net, vn_kv=0.4, name=f"{i + 1}동")
            pp.create_line_from_parameters(
                net, lv, bus,
                length_km=0.05 + 0.02 * i,
                r_ohm_per_km=0.2, x_ohm_per_km=0.08,
                c_nf_per_km=0.0, max_i_ka=0.4,
            )
            if per_feeder_mw > 0:
                pp.create_load(
                    net, bus,
                    p_mw=per_feeder_mw, q_mvar=per_feeder_mw * q_ratio,
                    name=f"{i + 1}동 부하",
                )

        ev_bus = pp.create_bus(net, vn_kv=0.4, name="EV 충전소")
        pp.create_line_from_parameters(
            net, lv, ev_bus,
            length_km=0.03, r_ohm_per_km=0.2, x_ohm_per_km=0.08,
            c_nf_per_km=0.0, max_i_ka=0.4,
        )
        if ev_kw > 0:
            pp.create_load(
                net, ev_bus,
                p_mw=ev_kw / 1000.0, q_mvar=ev_kw * q_ratio / 1000.0,
                name="EV 충전 부하",
            )

        if ess_kw > 0:
            ess_bus = pp.create_bus(net, vn_kv=0.4, name="묶음 ESS")
            pp.create_line_from_parameters(
                net, lv, ess_bus,
                length_km=0.01, r_ohm_per_km=0.2, x_ohm_per_km=0.08,
                c_nf_per_km=0.0, max_i_ka=0.4,
            )
            pp.create_sgen(
                net, ess_bus, p_mw=ess_kw / 1000.0, q_mvar=0.0, name="ESS 방전"
            )
        return net

    def _run_pf(
        self,
        pp: Any,
        base_kw: float,
        ev_kw: float,
        ess_kw: float,
        transformer_kva: float,
    ) -> tuple[float, list[float]]:
        """조류계산 → (변압기 부하율 %, 모선 전압 pu 리스트)."""
        net = self._build_net(pp, base_kw, ev_kw, ess_kw, transformer_kva)
        pp.runpp(net, calculate_voltage_angles=True)
        loading = float(net.res_trafo.loading_percent.iloc[0])
        voltages = [round(float(v), 4) for v in net.res_bus.vm_pu.tolist()]
        return loading, voltages

    # ── 해석적 폴백 ───────────────────────────────────────
    @staticmethod
    def _analytic_loading(total_kw: float, transformer_kva: float) -> float:
        if transformer_kva <= 0:
            return 0.0
        return max(0.0, (total_kw / POWER_FACTOR) / transformer_kva * 100.0)

    # ── 공개 API ──────────────────────────────────────────
    def simulate(
        self,
        grid_current: float,
        ess_discharge_kw: float,
        ev_count: int,
        transformer_kva: float = 300.0,
        season: str | None = None,
    ) -> dict:
        """PeakBridge 적용 전/후 변압기 부하율 시뮬레이션."""
        base_kw, ev_kw = self._loads_kw(grid_current, ev_count)
        # API/테스트 입력의 ess_discharge_kw는 이미 총 방전량(kW)으로 취급한다.
        ess_total_kw = max(0.0, ess_discharge_kw)
        engine = "analytic"
        bus_voltages: list[float] = []

        before = self._analytic_loading(base_kw + ev_kw, transformer_kva)
        after = self._analytic_loading(
            max(0.0, base_kw + ev_kw - ess_total_kw), transformer_kva
        )

        pp = self._pandapower()
        if pp is not None:
            try:
                before, _ = self._run_pf(pp, base_kw, ev_kw, 0.0, transformer_kva)
                after, bus_voltages = self._run_pf(
                    pp, base_kw, ev_kw, ess_total_kw, transformer_kva
                )
                engine = "pandapower"
            except Exception as exc:
                logger.warning("grid_powerflow_failed_fallback", error=str(exc))

        status = _status_of(after)
        if before >= WARNING_PCT and ess_total_kw > 0:
            recommendation = "ESS 방전 권장"
        elif before >= WARNING_PCT:
            recommendation = "ESS 방전 필요 (가용 ESS 없음)"
        else:
            recommendation = "정상 운전"

        return {
            "transformer_load_percent": round(before, 1),
            "after_peakbridge_percent": round(after, 1),
            "peak_reduction": round(before - after, 1),
            "status": status,
            "status_before": _status_of(before),
            "bus_voltages": bus_voltages,
            "recommendation": recommendation,
            "engine": engine,
            "assumptions": {
                "households": HOUSEHOLDS,
                "feeders": FEEDERS,
                "ev_charger_kw": EV_CHARGER_KW,
                "load_diversity": LOAD_DIVERSITY,
                "ess_units": ESS_UNITS,
                "transformer_kva": transformer_kva,
                "season": season,
                "base_load_kw": round(base_kw, 1),
                "ev_load_kw": round(ev_kw, 1),
                "ess_discharge_total_kw": round(ess_total_kw, 1),
            },
        }

    def get_apartment_model(
        self,
        grid_current: float = 15.0,
        ev_count: int = 1,
        transformer_kva: float = 300.0,
    ) -> dict:
        """아파트 단지 배전망 모델 (노드별 부하율, 변압기 현황)."""
        base_kw, ev_kw = self._loads_kw(grid_current, ev_count)
        per_feeder = base_kw / FEEDERS
        total_kw = base_kw + ev_kw
        loading = self._analytic_loading(total_kw, transformer_kva)

        nodes = [
            {
                "id": f"feeder-{i + 1}",
                "name": f"{i + 1}동",
                "load_kw": round(per_feeder, 1),
                "load_percent": round(
                    self._analytic_loading(per_feeder, transformer_kva / FEEDERS), 1
                ),
            }
            for i in range(FEEDERS)
        ]
        nodes.append(
            {
                "id": "ev-station",
                "name": "EV 충전소",
                "load_kw": round(ev_kw, 1),
                "load_percent": round(
                    self._analytic_loading(ev_kw, transformer_kva / FEEDERS), 1
                ),
            }
        )

        return {
            "topology": "radial (IEEE 33-bus 축소형)",
            "transformer": {
                "rating_kva": transformer_kva,
                "load_kw": round(total_kw, 1),
                "loading_percent": round(loading, 1),
                "status": _status_of(loading),
            },
            "nodes": nodes,
            "households": HOUSEHOLDS,
            "ess_units": ESS_UNITS,
        }


# 전역 인스턴스 (라우터에서 재사용)
grid_simulator = GridSimulator()
