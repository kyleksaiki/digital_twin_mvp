"""Network map API endpoints — DB-backed version."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.db_models import NetworkNodeRow, NetworkEdgeRow, RerouteEventRow, NodeEventRow, NodeChildRow

router = APIRouter(prefix="/api", tags=["network"])


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
        nodes.append({
            "id":            n.node_id,
            "label":         n.label,
            "role":          n.role,
            "x":             n.pos_x,
            "y":             n.pos_y,
            "battery":       n.battery,
            "drain":         n.drain,
            "traffic":       n.traffic,
            "health":        n.health,
            "packetsIn":     n.packets_in,
            "packetsOut":    n.packets_out,
            "retries":       n.retries,
            "collisions":    n.collisions,
            "aiDet":         n.ai_det,
            "events":        events_by_node.get(n.node_id, []),
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