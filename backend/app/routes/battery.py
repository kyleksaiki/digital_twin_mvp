"""Battery simulation API endpoints."""
import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import BatterySimResultRow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["battery"])


@router.get("/{run_id}/battery")
def get_battery_stats(run_id: int, db: Session = Depends(get_db)):
    """Stored single-node battery simulator output for a run.

    Returns {"available": false} (HTTP 200, not an error) when no simulation
    exists for the run — runs created before this feature must not break the
    Battery Statistics page.
    """
    row = (
        db.query(BatterySimResultRow)
        .filter(BatterySimResultRow.run_id == run_id)
        .order_by(BatterySimResultRow.id.desc())
        .first()
    )
    if not row:
        return {"available": False}

    try:
        battery_over_time = json.loads(row.series_json or "[]")
    except (TypeError, ValueError):
        logger.warning("Corrupt series_json for run %s battery result", run_id)
        battery_over_time = []
    try:
        component_energy_breakdown = json.loads(row.breakdown_json or "{}")
    except (TypeError, ValueError):
        logger.warning("Corrupt breakdown_json for run %s battery result", run_id)
        component_energy_breakdown = {}

    return {
        "available": True,
        "node_id": row.node_id,
        "duration_hours": row.duration_hours,
        "duration_source": row.duration_source,
        "battery_over_time": battery_over_time,
        "component_energy_breakdown": component_energy_breakdown,
        "summary": {
            "battery_wh": row.battery_wh,
            "energy_consumed_wh": row.energy_consumed_wh,
            "energy_remaining_wh": row.energy_remaining_wh,
            "final_battery_percent": row.final_battery_percent,
            "average_power_w": row.average_power_w,
            "avg_drain_percent_per_hour": row.avg_drain_percent_per_hour,
            "projected_total_life_hours": row.projected_total_life_hours,
            "total_detections": row.total_detections,
            "alive": row.alive,
        },
    }
