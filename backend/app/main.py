"""
FastAPI 애플리케이션 진입점.

lifespan으로 DB/MQTT/스케줄러 시작·종료를 관리하고,
CORS, 로깅, 글로벌 예외 처리, 헬스체크를 설정합니다.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import api_v1_router

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import CorrelationIdMiddleware, get_logger, setup_logging
from app.core.scheduler import setup_scheduler, shutdown_scheduler
from app.db.base import async_session_factory, close_db, init_db
from app.mqtt.publisher import mqtt_publisher
from app.mqtt.subscriber import mqtt_subscriber
from app.schemas.common import HealthResponse, ReadyResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """애플리케이션 시작/종료 시 리소스 초기화 및 정리."""
    setup_logging()
    logger.info(
        "application_starting",
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT.value,
    )
    await init_db()
    await mqtt_publisher.connect()
    await mqtt_subscriber.start()
    setup_scheduler()
    logger.info("application_ready")

    yield

    logger.info("application_shutting_down")
    shutdown_scheduler()
    await mqtt_subscriber.stop()
    await mqtt_publisher.disconnect()
    await close_db()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """FastAPI 앱 팩토리."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware)

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        """비즈니스 예외 — 일관된 JSON 에러 포맷."""
        logger.warning(
            "app_exception",
            path=request.url.path,
            code=exc.code,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "detail": exc.detail, "code": exc.code},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic 유효성 검증 오류."""
        logger.warning("validation_error", path=request.url.path, errors=exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation Error",
                "detail": str(exc.errors()),
                "code": "VALIDATION_ERROR",
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """처리되지 않은 예외."""
        logger.exception("unhandled_exception", path=request.url.path, error=str(exc))
        detail = str(exc) if settings.is_development else "Internal server error"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "detail": detail,
                "code": "INTERNAL_ERROR",
            },
        )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=settings.APP_VERSION,
            environment=settings.ENVIRONMENT.value,
        )

    @app.get("/ready", response_model=ReadyResponse, tags=["health"])
    async def ready() -> ReadyResponse:
        db_status = "disconnected"
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
                db_status = "connected"
        except Exception as exc:
            logger.error("readiness_check_failed", error=str(exc))
        return ReadyResponse(
            status="ready" if db_status == "connected" else "not_ready",
            database=db_status,
        )

    app.include_router(api_v1_router)
    return app


app = create_app()
