"""Data models for Digital Twin API."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class Run(BaseModel):
    """Simulation run metadata."""
    id: int
    name: str
    date: str
    scenario: str
    model: str
    shamanIProcessor: str
    shamanIIProcessor: str
    duration: str
    status: str  # 'pass', 'warning', 'fail'


class RunDetail(BaseModel):
    """Detailed run information with metrics."""
    id: int
    name: str
    model: str
    shamanIProcessor:str
    shamanIIProcessor: str
    duration: str
    status: str
    metrics: Dict[str, Any]


class NetworkNode(BaseModel):
    """Network topology node."""
    id: str
    label: str
    role: str  # 'command', 'relay', 'sensor'
    x: float
    y: float
    battery: int
    drain: float
    traffic: int
    health: str  # 'good', 'warning', 'critical'
    packetsIn: int
    packetsOut: int
    retries: int
    collisions: int
    aiDet: int
    events: List[str]
    powerBreakdown: Dict[str, int]
    children: Optional[List[str]] = None
    parent: Optional[str] = None


class NetworkEdge(BaseModel):
    """Network link between nodes."""
    frm: str = Field(alias="from")
    to: str
    congestion: int
    packetLoss: float
    retries: int
    collisions: int
    avgDelay: int
    reroutes: int
    latency: int

    model_config = {"populate_by_name": True}


class Reroute(BaseModel):
    """Reroute event."""
    frm: str = Field(alias="from")
    to: str

    model_config = {"populate_by_name": True}


class NetworkMap(BaseModel):
    """Complete network topology."""
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]
    reroutes: List[Reroute]


class ChatQuery(BaseModel):
    """Chat message from user."""
    q: str
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Chat response."""
    answer: str
