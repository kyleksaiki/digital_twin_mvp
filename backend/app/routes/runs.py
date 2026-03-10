"""Run-related API endpoints — DB-backed version."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models import Run, RunDetail
from app.database import get_db
from app.db_models import RunRow, RunMetricsRow

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _row_to_run(row: RunRow) -> Run:
    return Run(
        id=row.id,
        name=row.name,
        date=str(row.date),
        scenario=row.scenario,
        model=row.model,
        hw=row.hw,
        duration=row.duration,
        status=row.status,
    )


@router.get("")
def list_runs(db: Session = Depends(get_db)):
    """List all available simulation runs."""
    rows = db.query(RunRow).order_by(RunRow.date.desc()).all()
    return {"runs": [_row_to_run(r) for r in rows]}


@router.get("/{run_id}")
def get_run_detail(run_id: int, db: Session = Depends(get_db)) -> RunDetail:
    """Get detailed information for a specific run."""
    row = db.query(RunRow).filter(RunRow.id == run_id).first()

    if not row:
        return RunDetail(
            id=run_id, name="Unknown Run", model="Unknown",
            hw="Unknown", duration="N/A", status="unknown", metrics={},
        )

    m: RunMetricsRow = row.metrics
    metrics = {}
    if m:
        metrics = {
            "accuracy":        m.accuracy,
            "fpr":             m.fpr,
            "latency":         m.latency_ms,
            "detections":      m.detection_count,
            "battery":         m.battery_health,
            "congestion":      m.congestion,
            "throughput":      m.throughput,
            "conf_threshold":  m.conf_threshold,
        }

    return RunDetail(
        id=row.id, name=row.name, model=row.model,
        hw=row.hw, duration=row.duration, status=row.status,
        metrics=metrics,
    )


@router.get("/{run_id}/dashboard")
def get_dashboard(run_id: int, db: Session = Depends(get_db)):
    """
    Single endpoint that returns everything the Overview Dashboard needs.
    Frontend calls this once to populate all cards and charts.
    """
    row = db.query(RunRow).filter(RunRow.id == run_id).first()
    if not row:
        return {"error": "Run not found"}

    m = row.metrics

    return {
        "run": {
            "id": row.id, "name": row.name, "date": str(row.date),
            "scenario": row.scenario, "model": row.model,
            "hw": row.hw, "duration": row.duration, "status": row.status,
        },
        "metrics": {
            "accuracy":        m.accuracy        if m else None,
            "fpr":             m.fpr             if m else None,
            "latency_ms":      m.latency_ms      if m else None,
            "detection_count": m.detection_count if m else None,
            "battery_health":  m.battery_health  if m else None,
            "congestion":      m.congestion      if m else None,
            "throughput":      m.throughput      if m else None,
            "conf_threshold":  m.conf_threshold  if m else None,
        },
        "detections_by_type": [
            {"event_type": d.event_type, "count": d.count}
            for d in sorted(row.detections, key=lambda x: -x.count)
        ],
        "latency_by_rank": [
            {"rank": lr.rank, "latency_ms": lr.latency_ms}
            for lr in sorted(row.latency_by_rank, key=lambda x: x.rank)
        ],
        "accuracy_confidence_curve": [
            {"threshold": pt.threshold, "accuracy": pt.accuracy, "fpr": pt.fpr}
            for pt in sorted(row.acc_curve, key=lambda x: x.threshold)
        ],
    }