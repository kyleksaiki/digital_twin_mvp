"""Network map API endpoints — DB-backed version."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import re
from typing import Dict
from app.database import get_db
from app.db_models import NetworkNodeRow, NetworkEdgeRow, RerouteEventRow, NodeEventRow, NodeChildRow

router = APIRouter(prefix="/api", tags=["network"])


def _extract_detection_counts(events: list[str]) -> Dict[str, int]:
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
    return counts


def _merge_counts(base: Dict[str, int], other: Dict[str, int]) -> Dict[str, int]:
    merged = dict(base)
    for key, value in other.items():
        merged[key] = merged.get(key, 0) + value
    if "Gunshot" not in merged:
        merged["Gunshot"] = 0
    return merged


@router.get("/netmap")
def get_netmap(
    run_id: int = Query(default=1, description="Which run's network topology to load"),
    db: Session = Depends(get_db),
):
    """
    Get network topology and status for a given run.
    Defaults to run_id=1 so existing frontend works without changes.
    """
    # Load nodes
    node_rows = db.query(NetworkNodeRow).filter(NetworkNodeRow.run_id == run_id).all()
    event_rows = db.query(NodeEventRow).filter(NodeEventRow.run_id == run_id).all()
    child_rows = db.query(NodeChildRow).filter(NodeChildRow.run_id == run_id).all()

    # Build lookup maps
    events_by_node: dict[str, list[str]] = {}
    for ev in event_rows:
        events_by_node.setdefault(ev.node_id, []).append(ev.event_text)

    children_by_node: dict[str, list[str]] = {}
    for ch in child_rows:
        children_by_node.setdefault(ch.parent_node_id, []).append(ch.child_node_id)

    nodes = []
    for n in node_rows:
        node_events = events_by_node.get(n.node_id, [])
        detection_counts = _extract_detection_counts(node_events)

        if n.role == "relay":
            for child_id in children_by_node.get(n.node_id, []):
                detection_counts = _merge_counts(
                    detection_counts,
                    _extract_detection_counts(events_by_node.get(child_id, [])),
                )

        nodes.append({
            "id":            n.node_id,
            "label":         n.label,
            "role":          n.role,
            "x":             n.pos_x,
            "y":             n.pos_y,
            "lat":           n.lat,
            "lon":           n.lon,
            "realX":         n.lat,
            "realY":         n.lon,
            "battery":       n.battery,
            "drain":         n.drain,
            "traffic":       n.traffic,
            "health":        n.health,
            "packetsIn":     n.packets_in,
            "packetsOut":    n.packets_out,
            "retries":       n.retries,
            "collisions":    n.collisions,
            "aiDet":         n.ai_det,
            "events":        node_events,
            "detectionByType": [
                {"label": label, "count": value}
                for label, value in sorted(detection_counts.items(), key=lambda kv: kv[1], reverse=True)
            ],
            "powerBreakdown": {
                "radio":     n.power_radio,
                "processor": n.power_processor,
                "mic":       n.power_mic,
            },
            "children":      children_by_node.get(n.node_id, []),
            "parent":        n.parent_node_id,
        })

    # Load edges
    edge_rows = db.query(NetworkEdgeRow).filter(NetworkEdgeRow.run_id == run_id).all()
    edges = [
        {
            "from":       e.from_node,
            "to":         e.to_node,
            "congestion": e.congestion,
            "packetLoss": e.packet_loss,
            "retries":    e.retries,
            "collisions": e.collisions,
            "avgDelay":   e.avg_delay,
            "reroutes":   e.reroutes,
            "latency":    e.latency,
        }
        for e in edge_rows
    ]

    # Load reroutes
    reroute_rows = db.query(RerouteEventRow).filter(RerouteEventRow.run_id == run_id).all()
    reroutes = [{"from": r.from_node, "to": r.to_node} for r in reroute_rows]

    return JSONResponse(content={"nodes": nodes, "edges": edges, "reroutes": reroutes})