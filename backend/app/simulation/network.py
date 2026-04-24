"""
Network topology handling for the battery simulation.

What this file defines:
  - `NodeRole`: COMMAND (gateway) / RELAY (Shaman II) / SENSOR (Shaman I).
  - `SimNode`: one node with role, parent/children, battery state, event
               counters, and a `battery_history` list the engine appends to.
  - `SimNetwork`: a collection of `SimNode`s keyed by node_id, plus a
               constructor that builds the graph from DB rows.

The graph is rooted at the command/gateway node. Each sensor sends events up
through its parent relay(s) toward the gateway, and the engine uses this
parent/child chain to propagate confirmed events during transmission.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class NodeRole(Enum):
    COMMAND = "command"    # Gateway
    RELAY = "relay"        # Shaman II
    SENSOR = "sensor"      # Shaman I


@dataclass
class SimNode:
    """Node for battery simulation."""
    node_id: str
    role: NodeRole
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    # Battery state
    energy_wh: float = 22.0
    energy_consumed_wh: float = 0.0

    # Event counts
    events_detected: int = 0
    events_received: int = 0
    events_forwarded: int = 0

    # Time series output
    battery_history: List[Dict] = field(default_factory=list)

    def record_state(self, time_seconds: float, capacity_wh: float):
        """Record battery state at current time."""
        remaining = max(0, capacity_wh - self.energy_consumed_wh)
        percent = (remaining / capacity_wh) * 100 if capacity_wh > 0 else 0
        self.battery_history.append({
            "time_seconds": time_seconds,
            "time_hours": time_seconds / 3600,
            "battery_percent": round(percent, 2),
            "battery_wh": round(remaining, 4)
        })


@dataclass
class SimNetwork:
    """Network topology for simulation."""
    nodes: Dict[str, SimNode] = field(default_factory=dict)

    def add_node(self, node: SimNode):
        self.nodes[node.node_id] = node

    def get_node(self, node_id: str) -> Optional[SimNode]:
        return self.nodes.get(node_id)

    def get_sensors(self) -> List[SimNode]:
        return [n for n in self.nodes.values() if n.role == NodeRole.SENSOR]

    def get_relays(self) -> List[SimNode]:
        return [n for n in self.nodes.values() if n.role == NodeRole.RELAY]

    def get_gateway(self) -> Optional[SimNode]:
        for n in self.nodes.values():
            if n.role == NodeRole.COMMAND:
                return n
        return None

    @classmethod
    def from_db_nodes(cls, db_nodes: List, db_edges: List) -> "SimNetwork":
        """Build network from database node/edge rows.

        Edge direction in the DB is not standardized (the frontend stores
        CMD→R→S; some plans store S→R→CMD). We therefore derive the
        parent/child relationship from the node roles, not the edge order.

        Role hierarchy (closer to gateway = higher):
            SENSOR (0)  <  RELAY (1)  <  COMMAND (2)

        For each edge, the endpoint with the higher role is treated as the
        parent. Edges between two nodes of the same role (e.g. relay-relay
        backhaul) keep whichever direction is stored.
        """
        rank = {NodeRole.SENSOR: 0, NodeRole.RELAY: 1, NodeRole.COMMAND: 2}
        network = cls()

        for n in db_nodes:
            role = NodeRole(n.role) if hasattr(n, 'role') else NodeRole(n['role'])
            node_id = n.node_id if hasattr(n, 'node_id') else n['id']
            network.add_node(SimNode(node_id=node_id, role=role))

        for e in db_edges:
            from_id = e.from_node if hasattr(e, 'from_node') else e['from']
            to_id   = e.to_node   if hasattr(e, 'to_node')   else e['to']

            a = network.get_node(from_id)
            b = network.get_node(to_id)
            if a is None or b is None:
                continue

            # Figure out which end is the parent (higher rank).
            if rank[a.role] < rank[b.role]:
                child, parent = a, b
            elif rank[a.role] > rank[b.role]:
                child, parent = b, a
            else:
                # same rank — keep stored direction (a → b means a is child).
                child, parent = a, b

            if child.parent_id is None:
                child.parent_id = parent.node_id
            if child.node_id not in parent.children_ids:
                parent.children_ids.append(child.node_id)

        return network
