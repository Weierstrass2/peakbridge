"""FastAPI 의존성 주입 — DB 세션, 인증, 서비스."""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db.base import get_db
from app.models.user import User
from app.mqtt.publisher import MQTTPublisher, mqtt_publisher
from app.repositories.user_repository import UserRepository
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    session: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """JWT Bearer 토큰으로 현재 사용자 조회."""
    if not credentials:
        raise UnauthorizedError("Missing authentication token")

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise UnauthorizedError("Invalid or expired access token")

    user_id = UUID(payload["sub"])
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise UnauthorizedError("User not found")
    return user


async def get_optional_user(
    session: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User | None:
    """선택적 인증 — 토큰 없으면 None."""
    if not credentials:
        return None
    try:
        return await get_current_user(session, credentials)
    except UnauthorizedError:
        return None


def require_roles(*roles: UserRole):
    """역할 기반 접근 제어 의존성 팩토리."""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in [r.value for r in roles]:
            raise ForbiddenError(
                f"Required role: {', '.join(r.value for r in roles)}"
            )
        return user

    return _checker


AdminOrManager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_mqtt_publisher() -> MQTTPublisher:
    """MQTT publisher 싱글톤."""
    return mqtt_publisher
