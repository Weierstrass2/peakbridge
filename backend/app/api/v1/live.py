"""실시간 현장 카메라 중계 — 발표장 시연용.

── 무엇을 하는가 ──────────────────────────────────────────────

발표 중 하드웨어 리그를 **휴대폰 카메라로 비추면**, 발표덱(/deck)과 관제 화면을
보고 있는 모든 사람이 그 화면을 함께 봅니다.

    폰(송출) → POST /live/frame → 백엔드 메모리 → GET /live/frame.jpg → 관람자

WebRTC를 쓰지 않는 이유: 시연장 네트워크에서 P2P·STUN/TURN이 막히는 경우가 잦다.
JPEG 프레임을 그냥 HTTP로 올리고 내려받는 방식은 프록시 뒤에서도 확실히 동작한다.
5fps면 릴레이 절체를 보여주기에 충분하다.

상태는 **메모리에만** 둔다(서버 재시작 시 초기화). 프레임 1장만 보관한다.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from urllib.parse import unquote

import structlog
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.schemas.response import success_response

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/live", tags=["live"])

# 프레임 상한 — 폰이 과하게 큰 이미지를 올려 메모리를 먹는 것을 막는다
MAX_FRAME_BYTES = 900_000
STALE_AFTER_S = 8.0  # 이 시간 이상 새 프레임이 없으면 오프라인으로 본다


@dataclass
class LiveState:
    """최신 프레임 1장 + 메타 (in-memory 싱글톤)."""

    frame: bytes | None = None
    seq: int = 0
    updated_at: float = 0.0
    started_at: float = 0.0
    label: str = "하드웨어 실증 리그"
    viewers_served: int = 0
    _hist: list[float] = field(default_factory=list)

    # ── 송출 ──
    def put(self, data: bytes, label: str | None = None) -> dict:
        now = time.time()
        if self.frame is None:
            self.started_at = now
            logger.info("live_stream_started")
        self.frame = data
        self.seq += 1
        self.updated_at = now
        if label:
            self.label = label[:60]
        # 최근 20프레임 간격으로 실측 fps 산출
        self._hist.append(now)
        if len(self._hist) > 20:
            self._hist.pop(0)
        return self.status()

    # ── 상태 ──
    @property
    def online(self) -> bool:
        return self.frame is not None and (time.time() - self.updated_at) < STALE_AFTER_S

    @property
    def fps(self) -> float:
        if len(self._hist) < 2:
            return 0.0
        span = self._hist[-1] - self._hist[0]
        return round((len(self._hist) - 1) / span, 1) if span > 0 else 0.0

    def status(self) -> dict:
        return {
            "online": self.online,
            "seq": self.seq,
            "fps": self.fps,
            "label": self.label,
            "size_kb": round(len(self.frame) / 1024, 1) if self.frame else 0,
            "age_s": round(time.time() - self.updated_at, 2) if self.updated_at else None,
            "uptime_s": round(time.time() - self.started_at) if self.started_at else 0,
            "viewers_served": self.viewers_served,
        }

    def stop(self) -> dict:
        n = self.seq
        self.frame = None
        self.seq = 0
        self.updated_at = 0.0
        self.started_at = 0.0
        self._hist.clear()
        logger.info("live_stream_stopped", frames=n)
        return {"stopped": True, "frames": n}


live_state = LiveState()


class FrameReq(BaseModel):
    """base64 data URL 또는 순수 base64 문자열."""

    image: str = Field(..., description="data:image/jpeg;base64,... 또는 base64 본문")
    label: str | None = Field(default=None, max_length=60)


@router.post("/frame")
async def put_frame(body: FrameReq) -> dict:
    """폰에서 캡처한 JPEG 1장 업로드 (base64)."""
    try:
        raw = body.image.split(",", 1)[-1]
        data = base64.b64decode(raw, validate=False)
        if not data:
            return success_response({"error": "빈 프레임"})
        if len(data) > MAX_FRAME_BYTES:
            return success_response({"error": "프레임이 너무 큽니다", "limit": MAX_FRAME_BYTES})
        return success_response(live_state.put(data, body.label))
    except Exception as exc:  # noqa: BLE001
        logger.error("live_put_frame_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


@router.post("/frame-raw")
async def put_frame_raw(request: Request) -> dict:
    """JPEG 바이트를 그대로 업로드 (base64 오버헤드 없음)."""
    try:
        data = await request.body()
        if not data:
            return success_response({"error": "빈 프레임"})
        if len(data) > MAX_FRAME_BYTES:
            return success_response({"error": "프레임이 너무 큽니다", "limit": MAX_FRAME_BYTES})
        # 헤더는 ASCII만 실을 수 있으므로 송출 페이지가 URL 인코딩해 보낸다 → 여기서 복원
        raw_label = request.headers.get("x-live-label")
        label = unquote(raw_label) if raw_label else None
        return success_response(live_state.put(data, label))
    except Exception as exc:  # noqa: BLE001
        logger.error("live_put_frame_raw_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


@router.get("/frame.jpg")
async def get_frame() -> Response:
    """최신 프레임 (image/jpeg). 없으면 204."""
    if live_state.frame is None:
        return Response(status_code=204)
    live_state.viewers_served += 1
    return Response(
        content=live_state.frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Live-Seq": str(live_state.seq),
        },
    )


@router.get("/status")
async def get_status() -> dict:
    """송출 상태 — 관람자 화면이 폴링해 온라인 여부를 판단한다."""
    return success_response(live_state.status())


@router.post("/stop")
async def stop() -> dict:
    """송출 종료 (프레임 삭제)."""
    return success_response(live_state.stop())
