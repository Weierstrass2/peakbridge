"""EV 충전 세션 & 유연성 재고 서비스 (in-memory).

── 무엇을 하는가 ──────────────────────────────────────────────

차주가 폰(`/drive`)에서 충전 세션을 등록한다.
    - 출발 시각 · 필요 kWh 입력
    - '알뜰 충전'(eco) 또는 '즉시 충전'(now) 선택

'알뜰 충전'을 고른 세션의 필요 전력량은 **유연성 재고**로 집계된다.
알뜰 = "출발 전까지만 채워두면 언제 충전하든 상관없다" = 충전 시점을
우리가 옮길 수 있다는 뜻이고, 그만큼이 우리가 시장에 낼 수 있는 유연성이다.
'즉시 충전'은 지금 당장 채워야 하므로 유연성에 기여하지 않는다.

이 재고는 목업이 아니다. 하나의 in-memory 상태를 세 화면이 공유한다.
    폰(/drive)  →  관제(/app 충전기 탭)  →  VPP OS 제주 플러스DR 배분

상태는 메모리에만 둔다(서버 재시작 시 초기화 — 시연 직전 재현).
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog

logger = structlog.get_logger(__name__)

KST = timezone(timedelta(hours=9))

# 세션 코드에서 헷갈리는 글자(0/O, 1/I) 제외 — 폰에서 육안 확인/공유 편의
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now_kst_str() -> str:
    return datetime.now(KST).strftime("%H:%M:%S")


def _parse_hour(depart: str) -> int | None:
    """'18:30' 같은 표시용 문자열에서 시(hour)만 뽑는다. 실패하면 None."""
    if not depart:
        return None
    try:
        h = int(depart.split(":")[0])
        return h if 0 <= h <= 23 else None
    except (ValueError, IndexError):
        return None


@dataclass
class FlexSession:
    """차주 충전 세션 1건."""

    code: str
    household: str               # 세대 식별 코드 (예: "1203") — 로그인 대체
    building_id: str
    need_kwh: float              # 출발 전까지 채워야 하는 전력량
    depart: str                  # 출발 시각 표시용 (예: "18:30")
    mode: str                    # eco(알뜰) | now(즉시)
    status: str = "active"       # active | cancelled | done
    created_at: str = field(default_factory=_now_kst_str)
    created_ts: float = field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp()
    )

    @property
    def is_flexible(self) -> bool:
        """유연성 재고에 잡히는가 — 활성 상태의 '알뜰 충전'만 해당."""
        return self.status == "active" and self.mode == "eco"

    @property
    def depart_hour(self) -> int | None:
        return _parse_hour(self.depart)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "household": self.household,
            "building_id": self.building_id,
            "need_kwh": round(self.need_kwh, 1),
            "depart": self.depart,
            "depart_hour": self.depart_hour,
            "mode": self.mode,
            "mode_label": "알뜰 충전" if self.mode == "eco" else "즉시 충전",
            "status": self.status,
            "is_flexible": self.is_flexible,
            "created_at": self.created_at,
        }


class FlexService:
    """EV 충전 세션 등록·조회·취소 + 유연성 재고 집계 (in-memory 싱글톤)."""

    def __init__(self) -> None:
        self._sessions: dict[str, FlexSession] = {}
        self._rng = random.Random()

    # ── 코드 발급 ──
    def _new_code(self) -> str:
        for _ in range(20):
            code = "".join(self._rng.choice(_CODE_ALPHABET) for _ in range(6))
            if code not in self._sessions:
                return code
        # 극히 드문 충돌 폭주 — 타임스탬프로 강제 유일화
        return "S" + str(int(datetime.now(timezone.utc).timestamp() * 1000))[-6:]

    # ── 등록 ──
    def register(
        self,
        household: str,
        need_kwh: float,
        depart: str = "",
        mode: str = "eco",
        building_id: str = "building-A",
    ) -> dict:
        """새 충전 세션 등록. 잘못된 mode는 eco로 정규화한다."""
        mode = mode if mode in ("eco", "now") else "eco"
        sess = FlexSession(
            code=self._new_code(),
            household=household.strip() or "미상",
            building_id=building_id,
            need_kwh=float(need_kwh),
            depart=depart.strip(),
            mode=mode,
        )
        self._sessions[sess.code] = sess
        logger.info(
            "flex_session_registered",
            code=sess.code,
            household=sess.household,
            need_kwh=sess.need_kwh,
            mode=sess.mode,
            building_id=building_id,
        )
        return sess.to_dict()

    # ── 단건 조회 ──
    def get(self, code: str) -> dict | None:
        sess = self._sessions.get(code.upper().strip())
        return sess.to_dict() if sess else None

    # ── 취소 ──
    def cancel(self, code: str) -> dict | None:
        sess = self._sessions.get(code.upper().strip())
        if sess is None:
            return None
        sess.status = "cancelled"
        logger.info("flex_session_cancelled", code=sess.code)
        return sess.to_dict()

    # ── 목록 (운영자용) ──
    def list_sessions(
        self, building_id: str | None = None, active_only: bool = False
    ) -> list[dict]:
        rows = sorted(
            self._sessions.values(), key=lambda s: s.created_ts, reverse=True
        )
        out = []
        for s in rows:
            if building_id and s.building_id != building_id:
                continue
            if active_only and s.status != "active":
                continue
            out.append(s.to_dict())
        return out

    # ── 유연성 재고 집계 ──
    def flexibility(self, building_id: str | None = "building-A") -> dict:
        """유연성 재고 — 활성 '알뜰 충전' 세션의 필요 전력량 합.

        관제 화면과 제주 플러스DR 배분이 함께 참조하는 단일 진실원(SSOT).
        """
        flex_sessions = [
            s for s in self._sessions.values()
            if s.is_flexible and (not building_id or s.building_id == building_id)
        ]
        immediate = [
            s for s in self._sessions.values()
            if s.status == "active" and s.mode == "now"
            and (not building_id or s.building_id == building_id)
        ]
        flex_kwh = sum(s.need_kwh for s in flex_sessions)
        return {
            "building_id": building_id,
            "flex_kwh": round(flex_kwh, 1),
            "flex_session_count": len(flex_sessions),
            "immediate_kwh": round(sum(s.need_kwh for s in immediate), 1),
            "immediate_session_count": len(immediate),
            "sessions": [s.to_dict() for s in flex_sessions],
            "updated_at": _now_kst_str(),
        }

    def available_kwh(self, building_id: str | None = "building-A") -> float:
        """제주 배분 등에서 쓰는 단순 조회 — 유연성 재고 kWh만 반환."""
        return self.flexibility(building_id)["flex_kwh"]

    # ── 초기화 (시연 리허설 반복용) ──
    def reset(self) -> dict:
        n = len(self._sessions)
        self._sessions.clear()
        logger.info("flex_reset", cleared=n)
        return {"cleared": n}


flex_service = FlexService()
