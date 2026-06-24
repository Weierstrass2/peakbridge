"""API v1 Pydantic 스키마."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SensorReadingCreate(BaseModel):
    """단일 센서 측정값 요청."""

    device_id: str
    sensor_type: Literal["grid_current", "ess_soc", "charger_current"]
    value: float
    unit: str = "A"
    building_id: str | None = None


class SensorReadingBatchCreate(BaseModel):
    """배치 센서 측정값 — readings 배열 또는 단일."""

    readings: list[SensorReadingCreate] | None = None
    device_id: str | None = None
    sensor_type: Literal["grid_current", "ess_soc", "charger_current"] | None = None
    value: float | None = None
    unit: str = "A"
    building_id: str | None = None


class SensorReadingResponse(BaseModel):
    """센서 기록 응답."""

    status: str
    peak_triggered: bool
    forecast_next_hour: list[dict]


class RegisterRequest(BaseModel):
    """회원가입."""

    email: EmailStr
    password: str = Field(min_length=8)
    role: Literal["admin", "manager", "viewer"] = "viewer"
    building_id: str | None = None


class LoginRequest(BaseModel):
    """로그인."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """토큰 갱신."""

    refresh_token: str


class TokenResponse(BaseModel):
    """JWT 토큰 응답."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RelayControlRequest(BaseModel):
    """ESS 릴레이 제어."""

    action: Literal["discharge", "charge", "standby"]
