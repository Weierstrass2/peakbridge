"""
APScheduler 기반 백그라운드 작업.

- 5분마다: 피크 예측 → 30분 전 ESS 사전 충전
- 매일 02:00: Prophet 모델 재학습
- 매일 00:00: energy_saving 일별 집계
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.db.base import async_session_factory
from app.mqtt.publisher import mqtt_publisher

logger = structlog.get_logger(__name__)

scheduler = AsyncIOScheduler()

# 모니터링 대상 건물 (운영 시 DB에서 로드)
DEFAULT_BUILDINGS = ["building-001"]


async def _predict_and_precharge() -> None:
    """5분마다: 피크 30분 전 ESS 사전 충전 준비."""
    from datetime import datetime, timedelta, timezone

    from app.core.constants import ControlAction
    from app.services.forecast_service import ForecastService

    for building_id in DEFAULT_BUILDINGS:
        try:
            async with async_session_factory() as session:
                forecast_svc = ForecastService(session)
                exceed_time = await forecast_svc.will_exceed_threshold(building_id)
                if exceed_time:
                    now = datetime.now(timezone.utc)
                    delta = (exceed_time - now).total_seconds() / 60
                    if 0 < delta <= 30:
                        await mqtt_publisher.publish_relay_control(
                            building_id,
                            ControlAction.CHARGE.value,
                            "ai_auto",
                        )
                        logger.info(
                            "precharge_triggered",
                            building_id=building_id,
                            minutes_until_peak=round(delta, 1),
                        )
                await session.commit()
        except Exception as exc:
            logger.error("predict_precharge_failed", building_id=building_id, error=str(exc))


async def _retrain_models() -> None:
    """매일 02:00 Prophet 모델 재학습."""
    from app.services.forecast_service import ForecastService

    for building_id in DEFAULT_BUILDINGS:
        try:
            async with async_session_factory() as session:
                forecast_svc = ForecastService(session)
                await forecast_svc.train(building_id)
                await session.commit()
                logger.info("model_retrained", building_id=building_id)
        except Exception as exc:
            logger.error("model_retrain_failed", building_id=building_id, error=str(exc))


async def _aggregate_daily_savings() -> None:
    """매일 자정 energy_saving 일별 집계 확인."""
    from datetime import date

    from app.repositories.energy_repository import EnergyRepository

    for building_id in DEFAULT_BUILDINGS:
        try:
            async with async_session_factory() as session:
                repo = EnergyRepository(session)
                existing = await repo.get_by_date(building_id, date.today())
                if not existing:
                    await repo.increment_savings(building_id, 0, 0, 0, 0)
                await session.commit()
                logger.info("daily_aggregation_checked", building_id=building_id)
        except Exception as exc:
            logger.error("daily_aggregation_failed", building_id=building_id, error=str(exc))


def setup_scheduler() -> None:
    """스케줄러 작업 등록 및 시작."""
    if scheduler.running:
        return

    scheduler.add_job(
        _predict_and_precharge,
        IntervalTrigger(minutes=5),
        id="predict_precharge",
        replace_existing=True,
    )
    scheduler.add_job(
        _retrain_models,
        CronTrigger(hour=2, minute=0),
        id="retrain_models",
        replace_existing=True,
    )
    scheduler.add_job(
        _aggregate_daily_savings,
        CronTrigger(hour=0, minute=0),
        id="daily_aggregation",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler_started", environment=settings.ENVIRONMENT.value)


def shutdown_scheduler() -> None:
    """스케줄러 종료."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
