"""API 공통 응답 envelope 포맷."""

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """일관된 에러 JSON 포맷."""

    error: str
    detail: str
    code: str


class EnvelopeResponse(BaseModel, Generic[T]):
    """모든 API 성공 응답 envelope."""

    success: bool = True
    data: T
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def success_response(data: Any) -> dict[str, Any]:
    """envelope dict 생성 헬퍼."""
    return {
        "success": True,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
