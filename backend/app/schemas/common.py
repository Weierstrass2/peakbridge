"""공통 API 응답 스키마."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """/health 엔드포인트 응답."""

    status: str = Field(..., examples=["ok"])
    version: str
    environment: str


class ReadyResponse(BaseModel):
    """/ready 엔드포인트 응답 — DB 등 의존성 준비 상태."""

    status: str = Field(..., examples=["ready", "not_ready"])
    database: str = Field(..., examples=["connected", "disconnected"])
