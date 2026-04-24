"""
Battery simulation API endpoints.

What this file does:
  Exposes three HTTP endpoints that the frontend can call to run the battery
  simulator against a saved run.

    POST /api/battery/simulate             → run sim + return time-series per node
    GET  /api/battery/{run_id}/timeseries  → same, but with defaults (no body)
    GET  /api/battery/{run_id}/summary     → just the final battery % per node

The POST body accepts the Configure Run modal payload as-is, so whatever the
user enters in the UI flows straight through:

    {
      "run_id": 1,
      "duration_hours": 3.0,
      "shaman_i_config":  { "batteryLife": 30, "components": {...} },
      "shaman_ii_config": { "batteryLife": 22, "components": {...} },
      "radio_config":     { "packet_bytes": 128, "frames_per_hop": 3 },
      "ai_events_path":   "/path/to/event_timeline.json",   # optional
      "media_files":      { "S1": "node_001_....wav" }      # optional
    }

Event source is picked in priority order: ai_events_path → DB ai_events
table → synthetic mock timeline.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import AIEventRow, NetworkEdgeRow, NetworkNodeRow, RunRow
from app.simulation import BatterySimulator, SimulationConfig
from app.simulation.events import EventTimeline
from app.simulation.network import SimNetwork
from app.simulation.ai_event_loader import (
    infer_node_map_from_media_files,
    load_ai_events_with_stats,
)


router = APIRouter(prefix="/api/battery", tags=["battery"])


class BatterySimulationRequest(BaseModel):
    """Request body for `/api/battery/simulate`."""
    run_id: int
    duration_hours: Optional[float] = 3.0
    time_step_seconds: Optional[float] = 60.0

    # Configure Run modal payloads (verbatim).
    # Each is {"batteryLife": float, "processor": str,
    #          "components": {name: {"current": ..., "voltage": ..., "power": ...}}}
    shaman_i_config:  Optional[Dict[str, Any]] = None
    shaman_ii_config: Optional[Dict[str, Any]] = None

    # LoRa params — override defaults (SF10, 125 kHz, 128 B, 3 frames/hop).
    radio_config: Optional[Dict[str, Any]] = None

    # Optional: path to an AI event timeline JSON. If provided, it supersedes
    # any ai_events rows in the DB for this run.
    ai_events_path: Optional[str] = None

    # Optional: {"S1": "node_001_*.wav", ...} — maps each event's source_file
    # to a topology node_id. If absent we fall back to a node_NNN heuristic.
    media_files: Optional[Dict[str, str]] = None


def _load_timeline(req: BatterySimulationRequest,
                   db_events: List[AIEventRow],
                   sensor_ids: List[str]) -> tuple[EventTimeline, Dict[str, Any]]:
    """Pick an event source in priority order and return diagnostics."""
    if req.ai_events_path:
        p = Path(req.ai_events_path)
        if not p.exists():
            raise HTTPException(status_code=400,
                detail=f"ai_events_path not found: {p}")
        node_map = infer_node_map_from_media_files(req.media_files or {})
        timeline, stats = load_ai_events_with_stats(
            path=p,
            node_id_map=node_map,
            duration_hours=req.duration_hours,
        )
        return timeline, {"source": "ai_events_file", **stats}

    if db_events:
        timeline = EventTimeline.from_db_events(db_events, req.duration_hours or 3.0)
        return timeline, {"source": "db", "total": len(db_events)}

    timeline = EventTimeline.generate_mock(sensor_ids, req.duration_hours or 3.0)
    return timeline, {"source": "mock", "total": len(timeline.events)}


@router.post("/simulate")
def run_battery_simulation(req: BatterySimulationRequest,
                           db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Run a battery simulation and return time-series + summary."""
    run = db.query(RunRow).filter(RunRow.id == req.run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {req.run_id} not found")

    nodes = db.query(NetworkNodeRow).filter(NetworkNodeRow.run_id == req.run_id).all()
    edges = db.query(NetworkEdgeRow).filter(NetworkEdgeRow.run_id == req.run_id).all()
    if not nodes:
        raise HTTPException(status_code=400,
            detail=f"No nodes found for run {req.run_id}")

    config = SimulationConfig.from_run_config(
        shaman_i_config  = req.shaman_i_config,
        shaman_ii_config = req.shaman_ii_config,
        radio_config     = req.radio_config,
    )
    if req.time_step_seconds:
        config.time_step_seconds = req.time_step_seconds

    network = SimNetwork.from_db_nodes(nodes, edges)

    db_events = db.query(AIEventRow).filter(AIEventRow.run_id == req.run_id).all()
    sensor_ids = [n.node_id for n in nodes if n.role == "sensor"]
    timeline, event_source = _load_timeline(req, db_events, sensor_ids)

    simulator = BatterySimulator(config, network, timeline,
                                 duration_hours=req.duration_hours or 3.0)
    result = simulator.run()
    result["event_source"] = event_source
    return result


@router.get("/{run_id}/timeseries")
def get_battery_timeseries(run_id: int, db: Session = Depends(get_db)):
    """Run the simulation with defaults and return time-series data."""
    req = BatterySimulationRequest(run_id=run_id)
    return run_battery_simulation(req, db)


@router.get("/{run_id}/summary")
def get_battery_summary(run_id: int, db: Session = Depends(get_db)):
    """Final-state battery summary per node (no full time-series)."""
    result = get_battery_timeseries(run_id, db)

    summary_nodes: Dict[str, Any] = {}
    for node_id, node_data in result["nodes"].items():
        summary_nodes[node_id] = {
            "node_id": node_id,
            "role":    node_data["role"],
            "final_battery_percent": node_data["summary"]["final_battery_percent"],
            "energy_consumed_wh":    node_data["summary"]["energy_consumed_wh"],
            "events_detected":       node_data["summary"]["events_detected"],
        }

    return {
        "run_id":          run_id,
        "duration_hours":  result["duration_hours"],
        "total_events":    result["total_events"],
        "confirmed_events": result.get("confirmed_events"),
        "radio":           result.get("radio"),
        "nodes":           summary_nodes,
        "summary":         result["summary"],
        "event_source":    result.get("event_source"),
    }
