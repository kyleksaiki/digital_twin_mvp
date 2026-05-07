"""Local audio-processing endpoints for node-level AI timelines."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import AIEventRow, DetectionByTypeRow, NetworkNodeRow, NodeEventRow, RunMetricsRow, RunRow


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from node_audio_workflow import run_node_audio_workflow
except ImportError:
    run_node_audio_workflow = None


router = APIRouter(prefix="/api/audio", tags=["audio-processing"])


class NodeAudioInput(BaseModel):
    """One long audio file to process for one node."""

    node_id: str = Field(..., description="Digital Twin node id, e.g. node_001.")
    audio_path: str = Field(..., description="Local path to the node's long audio file.")
    metadata_json: Optional[str] = Field(None, description="Optional local metadata JSON for this node/audio.")


class AudioWorkflowRequest(BaseModel):
    """Request for running the staged audio workflow."""

    run_id: str = Field(..., description="String run id used in output manifests.")
    db_run_id: Optional[int] = Field(None, description="Existing numeric runs.id to attach events to.")
    nodes: List[NodeAudioInput]
    out_root: str = "audio_workflow_outputs"
    tinycnn_weights: Optional[str] = None
    tinycnn_threshold: float = 0.3
    birdnet_threshold: float = 0.5
    human_presence_threshold: float = 0.5
    sr: int = 48000
    clip_s: float = 3.0
    block_seconds: float = 60.0
    skip_birdnet: bool = False
    persist_to_db: bool = True


class AudioWorkflowNodeResult(BaseModel):
    node_id: str
    audio_path: str
    out_dir: str
    simplified_results_dir: str
    summary: Dict[str, Any]


class AudioWorkflowResponse(BaseModel):
    run_id: str
    db_run_id: Optional[int]
    nodes_processed: int
    results: List[AudioWorkflowNodeResult]


def _validate_local_path(path: Optional[str], label: str) -> None:
    if path and not Path(path).exists():
        raise HTTPException(status_code=400, detail=f"{label} does not exist: {path}")


def _confidence_from_event(event: Dict[str, Any]) -> float:
    shaman_ii = event.get("shaman_ii") or {}
    try:
        return float(shaman_ii.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _latency_from_event(event: Dict[str, Any]) -> int:
    shaman_ii = event.get("shaman_ii") or {}
    try:
        return int(round(float(shaman_ii.get("inference_ms", 0.0))))
    except (TypeError, ValueError):
        return 0


def _event_label(event: Dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "ai_event"))
    shaman_ii = event.get("shaman_ii") or {}
    species = shaman_ii.get("species")
    label = shaman_ii.get("label")

    if event_type == "bird_confirmed":
        return str(species or "Bird")
    if event_type == "human_presence_confirmed":
        return "Human Presence"
    if event_type == "birdnet_skipped":
        return "Bird"
    return str(label or event_type).replace("_", " ").title()


def _is_dashboard_event(event: Dict[str, Any]) -> bool:
    return str(event.get("event_type")) in {
        "bird_confirmed",
        "birdnet_skipped",
        "human_presence_confirmed",
    }


def _persist_workflow_result(db: Session, db_run_id: int, node_id: str, payload: Dict[str, Any]) -> None:
    run = db.query(RunRow).filter(RunRow.id == db_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {db_run_id}")

    combined = payload.get("combined_timeline") or []
    dashboard_events = [event for event in combined if _is_dashboard_event(event)]

    db.query(AIEventRow).filter(
        AIEventRow.run_id == db_run_id,
        AIEventRow.node_id == node_id,
    ).delete()
    db.query(NodeEventRow).filter(
        NodeEventRow.run_id == db_run_id,
        NodeEventRow.node_id == node_id,
    ).delete()

    counts: Dict[str, int] = {}
    total_latency = 0
    for event in dashboard_events:
        label = _event_label(event)
        confidence = _confidence_from_event(event)
        latency_ms = _latency_from_event(event)
        total_latency += latency_ms
        counts[label] = counts.get(label, 0) + 1
        timestamp_ms = int(round(float(event.get("trigger_time_s", 0.0)) * 1000.0))

        db.add(
            AIEventRow(
                run_id=db_run_id,
                node_id=node_id,
                timestamp_ms=timestamp_ms,
                event_type=label,
                confidence=confidence,
                latency_ms=latency_ms,
                energy_mj=0.0,
            )
        )

    for label, count in counts.items():
        db.add(NodeEventRow(run_id=db_run_id, node_id=node_id, event_text=f"{count} {label}"))

    node = db.query(NetworkNodeRow).filter(
        NetworkNodeRow.run_id == db_run_id,
        NetworkNodeRow.node_id == node_id,
    ).first()
    if node:
        node.ai_det = len(dashboard_events)

    db.flush()
    db.query(DetectionByTypeRow).filter(DetectionByTypeRow.run_id == db_run_id).delete()
    all_ai_events = db.query(AIEventRow).filter(AIEventRow.run_id == db_run_id).all()
    aggregate_counts: Dict[str, int] = {}
    for event in all_ai_events:
        aggregate_counts[event.event_type] = aggregate_counts.get(event.event_type, 0) + 1
    for label, count in aggregate_counts.items():
        db.add(DetectionByTypeRow(run_id=db_run_id, event_type=label, count=count))

    metrics = db.query(RunMetricsRow).filter(RunMetricsRow.run_id == db_run_id).first()
    if metrics:
        metrics.detection_count = len(all_ai_events)
        if all_ai_events:
            metrics.latency_ms = int(round(sum(e.latency_ms for e in all_ai_events) / len(all_ai_events)))
    elif all_ai_events:
        db.add(
            RunMetricsRow(
                run_id=db_run_id,
                accuracy=0.0,
                fpr=0.0,
                latency_ms=int(round(total_latency / max(1, len(dashboard_events)))),
                detection_count=len(all_ai_events),
                battery_health=0.0,
                congestion=0,
                throughput=0.0,
                conf_threshold=0.0,
            )
        )
    db.commit()


@router.post("/workflow/run", response_model=AudioWorkflowResponse)
def run_audio_workflow(req: AudioWorkflowRequest, db: Session = Depends(get_db)) -> AudioWorkflowResponse:
    """Run local AI processing for one or more node audio files."""
    if not run_node_audio_workflow:
        raise HTTPException(status_code=501, detail="Audio workflow not available. Install node_audio_workflow.")
    
    if not req.nodes:
        raise HTTPException(status_code=400, detail="At least one node audio file is required.")

    _validate_local_path(req.tinycnn_weights, "TinyCNN weights")
    if req.db_run_id is not None and not db.query(RunRow).filter(RunRow.id == req.db_run_id).first():
        raise HTTPException(status_code=404, detail=f"Run not found: {req.db_run_id}")

    out_root = Path(req.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    results: List[AudioWorkflowNodeResult] = []
    for node in req.nodes:
        _validate_local_path(node.audio_path, "Audio path")
        _validate_local_path(node.metadata_json, "Metadata JSON")

        node_out_dir = out_root / req.run_id / node.node_id
        try:
            result = run_node_audio_workflow(
                input_audio=node.audio_path,
                out_dir=str(node_out_dir),
                node_id=node.node_id,
                run_id=req.run_id,
                tinycnn_weights=req.tinycnn_weights,
                tinycnn_threshold=req.tinycnn_threshold,
                birdnet_threshold=req.birdnet_threshold,
                human_presence_threshold=req.human_presence_threshold,
                sr=req.sr,
                clip_s=req.clip_s,
                block_seconds=req.block_seconds,
                metadata_json=node.metadata_json,
                skip_birdnet=req.skip_birdnet,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        payload = result["backend_payload"]
        if req.persist_to_db and req.db_run_id is not None:
            _persist_workflow_result(db, req.db_run_id, node.node_id, payload)

        results.append(
            AudioWorkflowNodeResult(
                node_id=node.node_id,
                audio_path=node.audio_path,
                out_dir=str(node_out_dir),
                simplified_results_dir=str(node_out_dir / "simplified_results"),
                summary=result["summary"],
            )
        )

    return AudioWorkflowResponse(
        run_id=req.run_id,
        db_run_id=req.db_run_id,
        nodes_processed=len(results),
        results=results,
    )


@router.get("/workflow/inputs")
def get_required_workflow_inputs() -> Dict[str, Any]:
    """Expose the UI field checklist derived from the current notebooks/docs."""
    required_inputs = PROJECT_ROOT / "REQUIRED_STAGE_INPUTS.md"
    if not required_inputs.exists():
        raise HTTPException(status_code=404, detail="Required input checklist is missing.")
    return {"markdown": required_inputs.read_text()}
