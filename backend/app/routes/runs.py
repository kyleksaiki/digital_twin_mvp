"""Run-related API endpoints — DB-backed version."""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import logging
import re
import shutil
from app.models import Run, RunDetail
from app.database import get_db, SessionLocal
from app.services.run_export_service import RunExportService
from app.services.audio_processing import process_run_audio, run_node_audio_workflow
from app.db_models import (
    RunRow, RunMetricsRow, NetworkNodeRow, NetworkEdgeRow, 
    RerouteEventRow, DetectionByTypeRow, LatencyByRankRow, 
    AccuracyConfidenceCurveRow, NodeEventRow, NodeChildRow, AIEventRow, NodeAudioRow,
    PipelineStageStatRow, AudioProcessingStatRow, GroundTruthEvalRow,
)


logger = logging.getLogger(__name__)

try:
    from app.services.battery_sim import run_battery_simulation_for_run
except Exception as exc:
    logger.exception("Failed to import battery simulation service: %s", exc)
    run_battery_simulation_for_run = None

router = APIRouter(prefix="/api/runs", tags=["runs"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_ROOT = PROJECT_ROOT / "uploads"
PENDING_ROOT = UPLOAD_ROOT / "pending"


def _resolve_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sanitize_node_id(node_id: str) -> str:
    return "".join(ch for ch in str(node_id) if ch.isalnum() or ch in {"_", "-"}).strip("_-")


def _select_fallback_node(nodes: List[Dict[str, Any]]) -> Optional[str]:
    for node in nodes:
        if str(node.get("role")) == "sensor" and node.get("id"):
            return str(node.get("id"))
    for node in nodes:
        if node.get("id"):
            return str(node.get("id"))
    return None


def _extract_node_audio_map(req: "CreateRunRequest") -> Dict[str, str]:
    node_audio: Dict[str, str] = {}
    media_files = req.mediaFiles or {}

    if isinstance(media_files, dict):
        for key, value in media_files.items():
            if not value:
                continue
            if str(key).lower() == "audio":
                continue
            node_audio[str(key)] = str(value)

    if req.audioFiles:
        sensor_nodes = [str(node.get("id")) for node in req.nodes if node.get("role") == "sensor" and node.get("id")]
        for index, audio_path in enumerate([item for item in req.audioFiles if item]):
            if index < len(sensor_nodes) and sensor_nodes[index] not in node_audio:
                node_audio[sensor_nodes[index]] = str(audio_path)

    if not node_audio:
        fallback_path = None
        if isinstance(media_files, dict):
            fallback_path = media_files.get("audio")
        fallback_path = fallback_path or req.audioPath
        if not fallback_path and req.audioFiles:
            fallback_path = next((item for item in req.audioFiles if item), None)
        if fallback_path:
            fallback_node = _select_fallback_node(req.nodes)
            if fallback_node:
                node_audio[fallback_node] = str(fallback_path)

    return node_audio


def _finalize_audio_uploads(run_id: int, node_audio_map: Dict[str, str]) -> Dict[str, str]:
    finalized: Dict[str, str] = {}
    run_dir = UPLOAD_ROOT / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    for node_id, raw_path in node_audio_map.items():
        resolved = _resolve_path(raw_path)
        if not resolved.exists():
            raise HTTPException(status_code=400, detail=f"Audio file not found: {raw_path}")

        safe_node = _sanitize_node_id(node_id) or "node"
        suffix = resolved.suffix or ".wav"
        filename = f"node_{safe_node}{suffix}" if not safe_node.lower().startswith("node_") else f"{safe_node}{suffix}"
        dest = run_dir / filename

        if resolved.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            if _is_under(resolved, UPLOAD_ROOT):
                resolved.replace(dest)
            else:
                shutil.copy2(resolved, dest)

        finalized[str(node_id)] = _relative_path(dest)

    return finalized


def _evaluate_ground_truth_safe(db: Session, run_id: int, ground_truth: Optional[Any]) -> None:
    """Score this run's detections against a supplied ground-truth log.

    Optional and best-effort: no log, or a malformed one, simply leaves the
    measured-accuracy panel absent rather than failing the run.
    """
    if not ground_truth:
        return
    try:
        from app.services.aed.ground_truth import evaluate_run

        db.flush()
        detection_times = [
            float(row.timestamp_ms) / 1000.0
            for row in db.query(AIEventRow).filter(AIEventRow.run_id == run_id).all()
        ]
        result = evaluate_run(ground_truth, detection_times)
        if not result:
            return

        db.query(GroundTruthEvalRow).filter(GroundTruthEvalRow.run_id == run_id).delete()
        db.add(
            GroundTruthEvalRow(
                run_id=run_id,
                total_events=result["total_events"],
                total_detections=result["total_detections"],
                matched_events=result["matched_events"],
                missed_events=result["missed_events"],
                true_positive_detections=result["true_positive_detections"],
                false_positive_detections=result["false_positive_detections"],
                recall=result["recall"],
                precision=result["precision"],
                f1=result["f1"],
                detections_per_event=result["detections_per_event"],
                by_type_json=json.dumps(result["by_type"]),
            )
        )

        # These are measured on this run's own audio, so they are exactly what
        # the accuracy/FPR metric columns were always meant to hold.
        metrics = db.query(RunMetricsRow).filter(RunMetricsRow.run_id == run_id).first()
        if metrics:
            metrics.accuracy = float(result["recall"])
            metrics.fpr = float(
                result["false_positive_detections"] / result["total_detections"]
            ) if result["total_detections"] else 0.0
        db.commit()
        logger.info(
            "Ground truth for run %s: recall %.3f, precision %.3f over %s events",
            run_id, result["recall"], result["precision"], result["total_events"],
        )
    except Exception:
        logger.exception("Ground-truth evaluation failed for run %s; continuing", run_id)
        try:
            db.rollback()
        except Exception:
            logger.exception("Rollback failed after ground-truth error for run %s", run_id)


def _run_battery_sim_safe(db: Session, run_id: int, shaman_config: Optional[Dict[str, Any]]) -> None:
    """Run the battery simulation for a run; a failure must never fail the run."""
    if run_battery_simulation_for_run is None:
        logger.warning("Battery simulation service unavailable; skipping for run %s", run_id)
        return
    try:
        run_battery_simulation_for_run(db, run_id, shaman_config or {})
        db.commit()
    except Exception:
        logger.exception("Battery simulation failed for run %s; continuing without it", run_id)
        try:
            db.rollback()
        except Exception:
            logger.exception("Failed to roll back after battery simulation error for run %s", run_id)


def _process_audio_background(run_id: int, node_audio_map: Dict[str, str], config: Dict[str, Any], shaman_config: Optional[Dict[str, Any]] = None, ground_truth: Optional[Any] = None) -> None:
    """Background task: opens its own SessionLocal, runs the audio workflow, updates run status."""
    db = SessionLocal()
    try:
        if run_node_audio_workflow is None or process_run_audio is None:
            logger.error("Audio workflow unavailable for run %s; marking failed", run_id)
            run = db.query(RunRow).filter(RunRow.id == run_id).first()
            if run:
                run.status = "failed"
                db.commit()
            return

        process_run_audio(
            db,
            run_id,
            node_audio_map=node_audio_map,
            tinycnn_weights=config.get("tinycnn_weights"),
            tinycnn_threshold=float(config.get("tinycnn_threshold", 0.3)),
            birdnet_threshold=float(config.get("birdnet_threshold", 0.5)),
            human_presence_threshold=float(config.get("human_presence_threshold", 0.5)),
            sr=int(config.get("target_sample_rate") or config.get("sr") or 48000),
            skip_birdnet=bool(True),
            block_seconds=float(config.get("block_seconds") or 60.0),
            clip_s=float(config.get("clip_s") or 3.0),
        )
        # Persist the detection timeline before the battery sim consumes it, so
        # a sim failure (rolled back below) can never discard audio results.
        db.commit()

        _evaluate_ground_truth_safe(db, run_id, ground_truth)

        _run_battery_sim_safe(db, run_id, shaman_config)

        run = db.query(RunRow).filter(RunRow.id == run_id).first()
        if run:
            run.status = "complete"
            db.commit()
    except Exception:
        logger.exception("Audio processing failed for run %s", run_id)
        try:
            db.rollback()
            run = db.query(RunRow).filter(RunRow.id == run_id).first()
            if run:
                run.status = "failed"
                db.commit()
        except Exception:
            logger.exception("Failed to mark run %s as failed", run_id)
    finally:
        db.close()


def get_run_export_service(db: Session = Depends(get_db)) -> RunExportService:
    return RunExportService(db)


class CreateRunRequest(BaseModel):
    """Request body for creating a new run."""
    name: str
    scenario: Optional[str] = "MVP Simulation"
    shamani: Optional[str] = None
    shamanii: Optional[str] = None
    shamanIProcessor: Optional[str] = None
    shamanIIProcessor: Optional[str] = None
    duration: Optional[str] = "24h"
    status: Optional[str] = "pass"
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    mediaFiles: Optional[Dict[str, str]] = {}
    stage1Config: Optional[Dict[str, Any]] = None
    groundTruth: Optional[Any] = None
    confidenceThreshold: Optional[float] = None
    stage4Config: Optional[Dict[str, Any]] = None
    shamanConfig: Optional[Dict[str, Any]] = {}
    calibrationData: Optional[Dict[str, Any]] = None
    shamanIConfig: Optional[Dict[str, Any]] = None
    shamanIIConfig: Optional[Dict[str, Any]] = None
    audioPath: Optional[str] = None
    audioFiles: Optional[List[str]] = None


class CreateRunResponse(BaseModel):
    """Response for run creation."""
    id: int
    name: str
    created_at: str
    status: str


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _detections_from_events(events: List[str]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for event_text in events:
        match = re.search(r"(\d+)\s+([A-Za-z][A-Za-z\s_-]*)", str(event_text or ""))
        if not match:
            continue

        count = int(match.group(1))
        label = match.group(2).strip().replace("_", " ").replace("-", " ").title()
        counts[label] = counts.get(label, 0) + count

    if "Gunshot" not in counts:
        counts["Gunshot"] = 0

    return [
        {"label": label, "count": value}
        for label, value in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]


def _row_to_run(row: RunRow) -> Run:
    return Run(
        id=row.id,
        name=row.name,
        date=str(row.date),
        scenario=row.scenario,
        model="",
        shamanIProcessor=row.shamani,
        shamanIIProcessor=row.shamanii,
        duration=row.duration,
        status=row.status,
    )


@router.get("")
def list_runs(db: Session = Depends(get_db)):
    """List all available simulation runs."""
    rows = db.query(RunRow).order_by(RunRow.date.desc()).all()
    return {"runs": [_row_to_run(r) for r in rows]}


@router.get("/{run_id}/status")
def get_run_status(run_id: int, db: Session = Depends(get_db)):
    """Lightweight status poll for fire-and-poll background audio processing."""
    row = db.query(RunRow).filter(RunRow.id == run_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"id": row.id, "status": row.status}


@router.get("/{run_id}")
def get_run_detail(run_id: int, db: Session = Depends(get_db)) -> RunDetail:
    """Get detailed information for a specific run."""
    row = db.query(RunRow).filter(RunRow.id == run_id).first()

    if not row:
        return RunDetail(
            id=run_id, name="Unknown Run", model="Unknown",
            shamanIProcessor="Unknown", shamanIIProcessor="Unknown",
            duration="N/A", status="unknown", metrics={},
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
        id=row.id, name=row.name, model=row.scenario,
        duration=row.duration, status=row.status,
        shamanIProcessor=row.shamani, shamanIIProcessor=row.shamanii,
        metrics=metrics,
    )


@router.get("/{run_id}/export")
def export_run(
    run_id: int,
    include_nodes: bool = Query(True, description="Include node section"),
    include_edges: bool = Query(True, description="Include edge section"),
    export_service: RunExportService = Depends(get_run_export_service),
):
    run = export_service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    filename = export_service.build_filename(run_id)
    headers = {"Content-Disposition": f"attachment; filename=\"{filename}\""}

    return StreamingResponse(
        export_service.stream_run_export(
            run,
            include_nodes=include_nodes,
            include_edges=include_edges,
        ),
        media_type="text/csv",
        headers=headers,
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
            "scenario": row.scenario,
            "shamani": row.shamani, "shamanii": row.shamanii, "duration": row.duration, "status": row.status,
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
        "pipeline_stats": _pipeline_stats_for_run(db, run_id),
        "processing": _processing_stats_for_run(db, run_id),
        "ground_truth": _ground_truth_for_run(db, run_id),
    }


def _ground_truth_for_run(db: Session, run_id: int) -> Optional[Dict[str, Any]]:
    """Measured detection performance for this run, or None if no log supplied."""
    r = (
        db.query(GroundTruthEvalRow)
        .filter(GroundTruthEvalRow.run_id == run_id)
        .order_by(GroundTruthEvalRow.id.desc())
        .first()
    )
    if not r:
        return None
    try:
        by_type = json.loads(r.by_type_json or "[]")
    except (TypeError, ValueError):
        by_type = []
    return {
        "available": True,
        "total_events": r.total_events,
        "total_detections": r.total_detections,
        "matched_events": r.matched_events,
        "missed_events": r.missed_events,
        "true_positive_detections": r.true_positive_detections,
        "false_positive_detections": r.false_positive_detections,
        "recall": r.recall,
        "precision": r.precision,
        "f1": r.f1,
        "detections_per_event": r.detections_per_event,
        "by_type": by_type,
    }


def _pipeline_stats_for_run(db: Session, run_id: int) -> Dict[str, Any]:
    """Real per-stage pass/fail stats keyed by UI stage id. Empty dict if none."""
    rows = (
        db.query(PipelineStageStatRow)
        .filter(PipelineStageStatRow.run_id == run_id)
        .order_by(PipelineStageStatRow.stage_id)
        .all()
    )
    stats: Dict[str, Any] = {}
    for r in rows:
        try:
            details = json.loads(r.details_json or "[]")
        except (TypeError, ValueError):
            details = []
        stats[r.stage_id] = {
            "label": r.stage_label,
            "entered": r.entered,
            "passed": r.passed,
            "failed": r.failed,
            "mean_ms": round(r.mean_ms, 2),
            "total_ms": round(r.total_ms, 1),
            "details": details,
        }
    return stats


def _processing_stats_for_run(db: Session, run_id: int) -> Optional[Dict[str, Any]]:
    """AED model provenance + run-level processing measurements. None if absent."""
    r = (
        db.query(AudioProcessingStatRow)
        .filter(AudioProcessingStatRow.run_id == run_id)
        .order_by(AudioProcessingStatRow.id.desc())
        .first()
    )
    if not r:
        return None
    try:
        histogram = json.loads(r.confidence_histogram_json or "[]")
    except (TypeError, ValueError):
        histogram = []
    return {
        "model_status": r.model_status,
        "checkpoint_file": r.checkpoint_file,
        "model_version": r.model_version,
        "threshold": r.threshold,
        "device": r.device,
        "clips_scored": r.clips_scored,
        "clips_skipped": r.clips_skipped,
        "mean_confidence": r.mean_confidence,
        "confidence_histogram": histogram,
        "audio_seconds": r.audio_seconds,
        "wall_ms": r.wall_ms,
        "throughput_cps": r.throughput_cps,
        # Held-out validation-set figures for the checkpoint used — model card
        # material, NOT this run's measured accuracy.
        "validation": {
            "val_acc": r.val_acc,
            "not_meaningful_precision": r.val_precision,
            "not_meaningful_recall": r.val_recall,
            "not_meaningful_f1": r.val_f1,
        },
    }


@router.post("/create", response_model=CreateRunResponse)
def create_run(req: CreateRunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    scenario = req.scenario or "MVP Simulation"
    shamani = req.shamani or req.shamanIProcessor or "ESP32"
    shamanii = req.shamanii or req.shamanIIProcessor or "Radxa Zero"
    duration = req.duration or "24h"

    node_audio_map = _extract_node_audio_map(req)
    initial_status = "processing" if node_audio_map else (req.status or "pass")

    # Create run record
    run = RunRow(
        name=req.name,
        date=date.today(),
        scenario=scenario,
        shamani=shamani,
        shamanii=shamanii,
        duration=duration,
        status=initial_status,
        calibration_data=req.calibrationData,
    )
    db.add(run)
    db.flush()  # Get the run ID

    known_node_ids = {str(node.get("id")) for node in req.nodes if node.get("id")}
    unknown_audio_nodes = [node_id for node_id in node_audio_map if node_id not in known_node_ids]
    if unknown_audio_nodes:
        raise HTTPException(status_code=400, detail=f"Audio files attached to unknown node(s): {', '.join(unknown_audio_nodes)}")
    
    role_by_node_id = {
        str(node.get("id")): str(node.get("role"))
        for node in req.nodes
        if node.get("id") and node.get("role")
    }

    parent_by_sensor: Dict[str, str] = {}
    node_child_pairs = set()
    
    # Create network nodes using provided fields or safe defaults
    for node in req.nodes:
        power_breakdown = node.get("powerBreakdown") or {}
        real_x = node.get("realX")
        real_y = node.get("realY")
        db_node = NetworkNodeRow(
            run_id=run.id,
            node_id=node["id"],
            label=node["label"],
            role=node["role"],
            pos_x=node.get("x", 0.5),
            pos_y=node.get("y", 0.5),
            lat=node.get("lat", real_x),
            lon=node.get("lon", real_y),
            battery=_safe_int(node.get("battery")),
            drain=_safe_float(node.get("drain")),
            traffic=_safe_int(node.get("traffic")),
            health=str(node.get("health") or "good"),
            packets_in=_safe_int(node.get("packets_in") or node.get("packetsIn")),
            packets_out=_safe_int(node.get("packets_out") or node.get("packetsOut")),
            retries=_safe_int(node.get("retries")),
            collisions=_safe_int(node.get("collisions")),
            ai_det=_safe_int(node.get("ai_det") or node.get("aiDet")),
            power_radio=_safe_int(node.get("power_radio") or power_breakdown.get("radio")),
            power_processor=_safe_int(node.get("power_processor") or power_breakdown.get("processor")),
            power_mic=_safe_int(node.get("power_mic") or power_breakdown.get("mic")),
        )
        db.add(db_node)
    
    # Create network edges using provided fields or safe defaults
    for edge in req.edges:
        from_node = edge["from"]
        to_node = edge["to"]
        db_edge = NetworkEdgeRow(
            run_id=run.id,
            from_node=from_node,
            to_node=to_node,
            congestion=_safe_int(edge.get("congestion")),
            packet_loss=_safe_float(edge.get("packet_loss") or edge.get("packetLoss")),
            retries=_safe_int(edge.get("retries")),
            collisions=_safe_int(edge.get("collisions")),
            avg_delay=_safe_int(edge.get("avg_delay") or edge.get("avgDelay")),
            reroutes=_safe_int(edge.get("reroutes")),
            latency=_safe_int(edge.get("latency")),
        )
        db.add(db_edge)

        from_role = role_by_node_id.get(str(from_node))
        to_role = role_by_node_id.get(str(to_node))

        if from_role == "relay" and to_role == "sensor":
            node_child_pairs.add((from_node, to_node))
            parent_by_sensor[to_node] = from_node
        elif from_role == "sensor" and to_role == "relay":
            node_child_pairs.add((to_node, from_node))
            parent_by_sensor[from_node] = to_node

    for parent_node_id, child_node_id in node_child_pairs:
        db.add(
            NodeChildRow(
                run_id=run.id,
                parent_node_id=parent_node_id,
                child_node_id=child_node_id,
            )
        )

    for sensor_node_id, parent_node_id in parent_by_sensor.items():
        db.query(NetworkNodeRow).filter(
            NetworkNodeRow.run_id == run.id,
            NetworkNodeRow.node_id == sensor_node_id,
        ).update({"parent_node_id": parent_node_id})

    finalized_audio_map: Dict[str, str] = {}
    if node_audio_map:
        finalized_audio_map = _finalize_audio_uploads(run.id, node_audio_map)
        for node_id, audio_path in finalized_audio_map.items():
            db.add(NodeAudioRow(run_id=run.id, node_id=node_id, audio_path=audio_path))
    
    db.commit()

    # Fire-and-poll: spawn background audio processing AFTER commit so the
    # background task sees the persisted RunRow on its own session.
    if finalized_audio_map:
        config = {**(req.stage1Config or {}), **(req.stage4Config or {}), **(req.shamanIIConfig or {})}
        # The UI's Confidence Threshold is the AED gate threshold. Without this
        # the gate silently fell back to its default and the field did nothing.
        if req.confidenceThreshold is not None and "tinycnn_threshold" not in config:
            config["tinycnn_threshold"] = float(req.confidenceThreshold)
        background_tasks.add_task(
            _process_audio_background,
            run.id,
            finalized_audio_map,
            config,
            req.shamanConfig or {},
            req.groundTruth,
        )
    else:
        # No audio: run the battery sim now with an empty event list and the
        # dropdown duration — still a meaningful idle-drain baseline.
        _run_battery_sim_safe(db, run.id, req.shamanConfig or {})
    
    return CreateRunResponse(
        id=run.id,
        name=run.name,
        created_at=datetime.now().isoformat(),
        status=run.status,
    )


@router.get("/{run_id}/netmap")
def get_netmap(run_id: int, db: Session = Depends(get_db)):
    """
    Get network topology (nodes and edges) for a specific run.
    
    Returns:
    - nodes: List of network nodes with their properties
    - edges: List of network edges with their properties
    - reroutes: List of reroute events (from, to pairs)
    """
    row = db.query(RunRow).filter(RunRow.id == run_id).first()
    if not row:
        return {"nodes": [], "edges": [], "reroutes": []}

    events_by_node: Dict[str, List[str]] = {}
    for event in row.node_events:
        events_by_node.setdefault(event.node_id, []).append(event.event_text)

    children_by_node: Dict[str, List[str]] = {}
    for child in row.node_children:
        children_by_node.setdefault(child.parent_node_id, []).append(child.child_node_id)

    nodes = []
    for n in row.nodes:
        node_events = events_by_node.get(n.node_id, [])
        nodes.append({
            "id": n.node_id,
            "label": n.label,
            "role": n.role,
            "x": n.pos_x,
            "y": n.pos_y,
            "lat": n.lat,
            "lon": n.lon,
            "realX": n.lat,
            "realY": n.lon,
            "battery": n.battery,
            "drain": n.drain,
            "traffic": n.traffic,
            "health": n.health,
            "packetsIn": n.packets_in,
            "packetsOut": n.packets_out,
            "retries": n.retries,
            "collisions": n.collisions,
            "aiDet": n.ai_det,
            "events": node_events,
            "children": children_by_node.get(n.node_id, []),
            "parent": n.parent_node_id,
            "detectionByType": _detections_from_events(node_events),
            "powerBreakdown": {
                "radio": n.power_radio,
                "processor": n.power_processor,
                "mic": n.power_mic,
            },
        })

    edges = []
    for e in row.edges:
        edges.append({
            "from": e.from_node,
            "to": e.to_node,
            "congestion": e.congestion,
            "packetLoss": e.packet_loss,
            "retries": e.retries,
            "collisions": e.collisions,
            "avgDelay": e.avg_delay,
            "reroutes": e.reroutes,
            "latency": e.latency,
        })

    reroutes = [{"from": r.from_node, "to": r.to_node} for r in row.reroutes]

    return {
        "nodes": nodes,
        "edges": edges,
        "reroutes": reroutes,
        "calibrationData": row.calibration_data,
    }