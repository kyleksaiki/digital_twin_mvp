"""Run-related API endpoints — DB-backed version."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, date
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import re
from app.models import Run, RunDetail
from app.database import get_db
from app.db_models import (
    RunRow, RunMetricsRow, NetworkNodeRow, NetworkEdgeRow, 
    RerouteEventRow, DetectionByTypeRow, LatencyByRankRow, 
    AccuracyConfidenceCurveRow, NodeEventRow, NodeChildRow, AIEventRow
)
import random

router = APIRouter(prefix="/api/runs", tags=["runs"])


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
    shamanConfig: Optional[Dict[str, Any]] = {}
    calibrationData: Optional[Dict[str, Any]] = None
    shamanIConfig: Optional[Dict[str, Any]] = None
    shamanIIConfig: Optional[Dict[str, Any]] = None


class CreateRunResponse(BaseModel):
    """Response for run creation."""
    id: int
    name: str
    created_at: str


def _generate_mock_node_data(node_role: str) -> Dict[str, Any]:
    """Generate realistic mock data for a node."""
    return {
        "battery": random.randint(20, 100),
        "drain": round(random.uniform(0.1, 2.5), 2),
        "traffic": random.randint(10, 95),
        "health": random.choice(["good", "warning", "critical"]),
        "packets_in": random.randint(100, 5000),
        "packets_out": random.randint(100, 5000),
        "retries": random.randint(0, 50),
        "collisions": random.randint(0, 10),
        "ai_det": random.randint(0, 20),
        "power_radio": random.randint(100, 500),
        "power_processor": random.randint(50, 300),
        "power_mic": random.randint(10, 100),
    }


def _generate_mock_edge_data() -> Dict[str, Any]:
    """Generate realistic mock data for an edge."""
    return {
        "congestion": random.randint(10, 95),
        "packet_loss": round(random.uniform(0, 5), 2),
        "retries": random.randint(0, 20),
        "collisions": random.randint(0, 5),
        "avg_delay": random.randint(10, 500),
        "reroutes": random.randint(0, 3),
        "latency": random.randint(5, 200),
    }


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


@router.get("/{run_id}")
def get_run_detail(run_id: int, db: Session = Depends(get_db)) -> RunDetail:
    """Get detailed information for a specific run."""
    row = db.query(RunRow).filter(RunRow.id == run_id).first()

    if not row:
        return RunDetail(
            id=run_id, name="Unknown Run", 
            shamani="Unknown", shamanii="Unknown", 
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
        id=row.id, name=row.name,
        duration=row.duration, status=row.status,
        shamanIProcessor=row.shamani, shamanIIProcessor=row.shamanii,
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
    }


@router.post("/create", response_model=CreateRunResponse)
def create_run(req: CreateRunRequest, db: Session = Depends(get_db)):
    scenario = req.scenario or "MVP Simulation"
    shamani = req.shamani or req.shamanIProcessor or "ESP32"
    shamanii = req.shamanii or req.shamanIIProcessor or "Radxa Zero"
    duration = req.duration or "24h"

    # Create run record
    run = RunRow(
        name=req.name,
        date=date.today(),
        scenario=scenario,
        shamani=shamani,
        shamanii=shamanii,
        duration=duration,
        status=req.status or "pass",
        calibration_data=req.calibrationData,
    )
    db.add(run)
    db.flush()  # Get the run ID
    
    # Create mock metrics
    avg_latency = random.randint(10, 200)
    avg_congestion = random.randint(20, 80)
    
    metrics = RunMetricsRow(
        run_id=run.id,
        accuracy=round(random.uniform(0.75, 0.98), 4),
        fpr=round(random.uniform(0.01, 0.1), 4),
        latency_ms=avg_latency,
        detection_count=random.randint(5, 50),
        battery_health=round(random.uniform(60, 95), 2),
        congestion=avg_congestion,
        throughput=round(random.uniform(50, 500), 2),
        conf_threshold=round(random.uniform(0.5, 0.9), 2),
    )
    db.add(metrics)

    role_by_node_id = {
        str(node.get("id")): str(node.get("role"))
        for node in req.nodes
        if node.get("id") and node.get("role")
    }

    parent_by_sensor: Dict[str, str] = {}
    node_child_pairs = set()
    
    # Create network nodes with mock data
    for node in req.nodes:
        mock_data = _generate_mock_node_data(node["role"])
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
            **mock_data,
        )
        db.add(db_node)

        if node.get("role") == "sensor":
            sensor_categories = ["bird", "gunshot", "chainsaw", "howler monkey"]
            sampled = random.sample(sensor_categories, k=min(2, len(sensor_categories)))
            for category in sampled:
                event_count = random.randint(1, 8)
                db.add(
                    NodeEventRow(
                        run_id=run.id,
                        node_id=node["id"],
                        event_text=f"{event_count} {category}",
                    )
                )
    
    # Create network edges with mock data
    for edge in req.edges:
        from_node = edge["from"]
        to_node = edge["to"]
        mock_data = _generate_mock_edge_data()
        db_edge = NetworkEdgeRow(
            run_id=run.id,
            from_node=from_node,
            to_node=to_node,
            **mock_data,
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
    
    # Create sample detection events
    event_types = ["Bird", "Gunshot", "Chainsaw", "Howler Monkey", "Vehicle"]
    for i in range(min(5, len(req.nodes))):
        for _ in range(random.randint(1, 3)):
            det = DetectionByTypeRow(
                run_id=run.id,
                event_type=random.choice(event_types),
                count=random.randint(1, 10),
            )
            db.add(det)
    
    # Create sample latency points
    for rank in range(1, min(6, len(req.nodes) + 1)):
        lat_row = LatencyByRankRow(
            run_id=run.id,
            rank=rank,
            latency_ms=random.randint(5, avg_latency * 2),
        )
        db.add(lat_row)
    
    # Create accuracy-confidence curve
    for threshold in [0.5, 0.6, 0.7, 0.8, 0.9]:
        acc_row = AccuracyConfidenceCurveRow(
            run_id=run.id,
            threshold=threshold,
            accuracy=round(0.85 + (threshold / 10), 4),
            fpr=round(0.1 - (threshold / 20), 4),
        )
        db.add(acc_row)
    
    db.commit()
    
    return CreateRunResponse(
        id=run.id,
        name=run.name,
        created_at=datetime.now().isoformat(),
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
