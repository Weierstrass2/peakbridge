"""절감 리포트 API — 집계 및 CSV 내보내기."""

import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.deps import DbSession
from app.repositories.energy_repository import EnergyRepository
from app.schemas.response import success_response

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{building_id}/savings")
async def get_savings_report(
    session: DbSession,
    building_id: str,
    period: Literal["day", "week", "month", "year"] = Query(default="month"),
) -> dict:
    """GET /api/v1/reports/{building_id}/savings — 기간별 절감 리포트."""
    repo = EnergyRepository(session)
    summary = await repo.get_period_summary(building_id, period)
    return success_response({"building_id": building_id, "period": period, **summary})


@router.get("/{building_id}/export")
async def export_savings_csv(
    session: DbSession,
    building_id: str,
    days: int = Query(default=30, ge=1, le=365),
) -> StreamingResponse:
    """GET /api/v1/reports/{building_id}/export — CSV 다운로드."""
    repo = EnergyRepository(session)
    end = date.today()
    start = end - timedelta(days=days)
    rows = await repo.export_csv_rows(building_id, start, end)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["date", "saved_kwh", "saved_won", "co2_reduced_kg", "peak_count"]
    )
    for row in rows:
        writer.writerow(
            [
                row.date.isoformat(),
                row.saved_kwh,
                row.saved_won,
                row.co2_reduced_kg,
                row.peak_count,
            ]
        )

    output.seek(0)
    filename = f"savings_{building_id}_{start}_{end}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
