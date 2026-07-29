"""시장 프로파일 — 같은 자원을 어느 시장 문법으로 참여시킬 것인가.

PeakBridge는 두 시장에서 동시에 돈을 번다. 물리 자원(배터리·충전기)과
예측·리스크·정산 엔진은 하나지만, **참여 문법이 완전히 다르다.**

    육지 (현행 CBP)          제주 (시범사업 / 재생에너지 입찰)
    ─────────────────────    ─────────────────────────────────
    가격입찰 없음             가격입찰 있음
    KPX가 SMP 결정·통보       입찰로 낙찰 결정
    아파트 = 수요자원          VPP = 발전자원
    돈: 요금절감 + DR         돈: 시장정산 + 용량 + DR

이 파일을 두는 이유:
  전에는 두 문법이 코드에 섞여 있었다. 화면에는 "24구간 가격입찰"이 떠 있는데
  현행 육지 시장에는 그런 게 없다 — 심사에서 지적당하면 방어가 안 된다.
  프로파일을 명시적으로 분리해 **어느 제도 기준인지 항상 드러내도록** 한다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class RevenueStream:
    key: str
    label: str
    available: bool          # 현행 제도에서 지금 가능한가
    basis: str               # 정산 근거
    note: str = ""


@dataclass
class MarketProfile:
    key: str
    name: str
    region: str
    role: str                # 우리 자원이 시장에서 갖는 지위
    bidding: str             # 입찰 문법
    price_use: str           # 가격 예측을 어디에 쓰는가
    settlement: str
    penalty: str
    status: str              # live | pilot | planned
    streams: list[RevenueStream] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["available_streams"] = [s.label for s in self.streams if s.available]
        return d


# ── 육지: 현행 변동비반영시장(CBP) ─────────────────────────────
INLAND_CBP = MarketProfile(
    key="inland_cbp",
    name="육지 — 현행 변동비반영시장(CBP)",
    region="inland",
    role="수요자원 (아파트 단지). 발전기가 아니라 부하로 참여한다",
    bidding=(
        "가격입찰 없음. 발전사는 공급가능용량만 제출하고 KPX가 변동비 순으로 "
        "급전순위와 SMP를 결정해 통보한다. 우리는 입찰가를 쓰지 않는다."
    ),
    price_use=(
        "입찰가 결정이 아니라 **충·방전 타이밍 결정**에 쓴다. "
        "ESS는 급전지시를 받는 대상이 아니라 스스로 스케줄을 짜는 자원이다."
    ),
    settlement="요금제(계약전력·시간대별 요금) 기준 절감 + DR 정산",
    penalty="DR 미이행 시 정산금 차감 (시장 위약금 개념 아님)",
    status="live",
    streams=[
        RevenueStream("peak_saving", "피크쉐이빙 기본요금 절감", True,
                      "그달 최대수요 × 기본요금 단가",
                      "전기요금은 그달 최고 순간 하나로 기본요금이 결정된다"),
        RevenueStream("arbitrage", "경부하↔최대부하 차익", True,
                      "시간대별 요금 차 × 방전량",
                      "SMP가 아니라 소비자 요금제 기준"),
        RevenueStream("dr", "수요반응(DR) 정산", True,
                      "감축량 × DR 단가", "OpenADR 신호 수신 후 응동"),
        RevenueStream("broker_market", "소규모전력중개시장", False,
                      "SMP 기준 정산", "중개사업자 등록 후 가능"),
    ],
)

# ── 제주: 시범사업 (실시간시장 + 재생에너지 입찰) ─────────────
JEJU_PILOT = MarketProfile(
    key="jeju_pilot",
    name="제주 — 시범사업 (실시간·예비력·재생에너지 입찰)",
    region="jeju",
    role="VPP 발전자원. 여러 단지를 묶어 하나의 발전기처럼 참여한다",
    bidding=(
        "가격입찰 있음. 하루전시장에 24구간 수량·가격을 제출하고 "
        "실시간시장(15분)에서 조정한다. 재생에너지도 입찰에 참여하며 "
        "가격원리에 의한 출력제어가 적용된다."
    ),
    price_use="입찰가 결정 + 충·방전 스케줄링 양쪽 모두",
    settlement="pay-as-clear (입찰가 ≤ MCP면 낙찰, 정산은 MCP로) + 용량요금(CP)",
    penalty="미이행 부족분 × MCP × 위약계수",
    status="pilot",
    streams=[
        RevenueStream("energy", "에너지 정산금", True,
                      "낙찰·이행량 × MCP", "제주 시범사업 참여 자격 필요"),
        RevenueStream("capacity", "용량요금(CP)", True,
                      "신고용량 × CP 단가", "낙찰 여부와 무관 — 손실 방어선"),
        RevenueStream("reserve", "예비력(보조서비스)", False,
                      "응동 가능 용량 × 단가", "응답시간 요건 충족 시"),
        RevenueStream("curtail_absorb", "출력제어 흡수", True,
                      "버려질 전력 저가 충전 → 고가 시간 방전",
                      "제주 재생에너지 과잉의 직접 수혜 — 이게 핵심 가치"),
        RevenueStream("dr", "수요반응(DR) 정산", True, "감축량 × 단가"),
    ],
)

PROFILES: dict[str, MarketProfile] = {
    INLAND_CBP.key: INLAND_CBP,
    JEJU_PILOT.key: JEJU_PILOT,
}

DEFAULT_PROFILE = INLAND_CBP.key


def get_profile(key: str | None = None) -> MarketProfile:
    return PROFILES.get(key or DEFAULT_PROFILE, INLAND_CBP)


def compare() -> dict:
    """두 시장의 차이를 한 표로 — 발표·화면 설명용."""
    rows = [
        ("자원 지위", INLAND_CBP.role, JEJU_PILOT.role),
        ("입찰 문법", INLAND_CBP.bidding, JEJU_PILOT.bidding),
        ("가격 예측 용도", INLAND_CBP.price_use, JEJU_PILOT.price_use),
        ("정산", INLAND_CBP.settlement, JEJU_PILOT.settlement),
        ("미이행", INLAND_CBP.penalty, JEJU_PILOT.penalty),
        ("제도 상태", "현재 운영 중", "시범사업 진행 중"),
    ]
    return {
        "profiles": [INLAND_CBP.to_dict(), JEJU_PILOT.to_dict()],
        "comparison": [{"item": a, "inland": b, "jeju": c} for a, b, c in rows],
        "shared_engine": [
            "자원 물리 모델 (용량·정격·SOC·열화)",
            "수요·가격 예측 (XGBoost)",
            "리스크 엔진 (한도·VaR·킬스위치)",
            "이행 감시 및 정산 검증",
        ],
        "note": (
            "엔진은 하나, 시장 문법만 갈아끼운다. 육지에서 요금절감·DR로 매출을 만들고, "
            "제주에서 시장 입찰로 확장한다. 제도가 PBP로 전환되면 육지도 제주 프로파일로 이동한다."
        ),
    }
