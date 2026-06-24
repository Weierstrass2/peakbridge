"""
SQLAlchemy 2.0 async 엔진 및 세션 팩토리.

FastAPI 의존성 주입용 get_db()를 제공합니다.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """모든 ORM 모델의 기본 클래스."""

    pass


# 비동기 엔진 — PostgreSQL + asyncpg 드라이버
engine: AsyncEngine = create_async_engine(
    str(settings.DB_URL),
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
)

# 세션 팩토리 — 요청마다 독립 세션 생성
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Depends용 DB 세션 의존성.

    요청 종료 시 자동 commit/rollback 및 세션 close.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """애플리케이션 시작 시 모든 테이블 자동 생성."""
    # 모든 모델 import (테이블 등록용)
    from app.models.user import User
    from app.models.device import Device
    from app.models.sensor_reading import SensorReading
    from app.models.alert import Alert
    from app.models.control_log import ControlLog
    from app.models.energy_saving import EnergySaving

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """애플리케이션 종료 시 커넥션 풀 해제."""
    await engine.dispose()
