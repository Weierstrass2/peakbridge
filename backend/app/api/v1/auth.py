"""인증 API — 회원가입, 로그인, 토큰 갱신."""

import uuid

from fastapi import APIRouter

from app.core.deps import DbSession
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationAppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    TOKEN_TYPE_REFRESH,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.api import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.response import success_response

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(session: DbSession, body: RegisterRequest) -> dict:
    """POST /api/v1/auth/register — 사용자 등록."""
    repo = UserRepository(session)
    existing = await repo.get_by_email(body.email)
    if existing:
        raise ConflictError("Email already registered", code="EMAIL_EXISTS")

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        building_id=body.building_id,
    )
    await repo.create(user)

    tokens = TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )
    return success_response(tokens.model_dump())


@router.post("/login")
async def login(session: DbSession, body: LoginRequest) -> dict:
    """POST /api/v1/auth/login — 로그인."""
    repo = UserRepository(session)
    user = await repo.get_by_email(body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")

    tokens = TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )
    return success_response(tokens.model_dump())


@router.post("/refresh")
async def refresh_token(session: DbSession, body: RefreshRequest) -> dict:
    """POST /api/v1/auth/refresh — access 토큰 갱신."""
    payload = decode_token(body.refresh_token, TOKEN_TYPE_REFRESH)
    if not payload:
        raise UnauthorizedError("Invalid or expired refresh token")

    repo = UserRepository(session)
    user = await repo.get_by_id(uuid.UUID(payload["sub"]))
    if not user:
        raise UnauthorizedError("User not found")

    tokens = TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )
    return success_response(tokens.model_dump())
