"""
SQLAlchemy ORM models — mirror of schema.sql.
Drop-in alongside existing models.py (Pydantic) without touching it.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Date, Enum, BigInteger,
    ForeignKey, UniqueConstraint, Index, TIMESTAMP, func, JSON,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class RunRow(Base):
    __tablename__ = "runs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False)
    date       = Column(Date, nullable=False)
    scenario   = Column(String(100), nullable=False)
    shamani    = Column(String(50), nullable=False)
    shamanii   = Column(String(50), nullable=False)
    duration   = Column(String(20), nullable=False)
    status     = Column(Enum("pass", "warning", "fail"), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    calibration_data = Column(JSON, nullable=True)

    # Relationships
    metrics            = relationship("RunMetricsRow",            back_populates="run", uselist=False, cascade="all, delete-orphan")
    detections         = relationship("DetectionByTypeRow",       back_populates="run", cascade="all, delete-orphan")
    latency_by_rank    = relationship("LatencyByRankRow",         back_populates="run", cascade="all, delete-orphan")
    acc_curve          = relationship("AccuracyConfidenceCurveRow", back_populates="run", cascade="all, delete-orphan")
    nodes              = relationship("NetworkNodeRow",           back_populates="run", cascade="all, delete-orphan")
    node_events        = relationship("NodeEventRow",             back_populates="run", cascade="all, delete-orphan")
    node_children      = relationship("NodeChildRow",             back_populates="run", cascade="all, delete-orphan")
    edges              = relationship("NetworkEdgeRow",           back_populates="run", cascade="all, delete-orphan")
    reroutes           = relationship("RerouteEventRow",          back_populates="run", cascade="all, delete-orphan")
    ai_events          = relationship("AIEventRow",               back_populates="run", cascade="all, delete-orphan")


class RunMetricsRow(Base):
    __tablename__ = "run_metrics"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    run_id          = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    accuracy        = Column(Float, nullable=False)
    fpr             = Column(Float, nullable=False)
    latency_ms      = Column(Integer, nullable=False)
    detection_count = Column(Integer, nullable=False)
    battery_health  = Column(Float, nullable=False)
    congestion      = Column(Integer, nullable=False)
    throughput      = Column(Float, nullable=False)
    conf_threshold  = Column(Float, nullable=False)

    run = relationship("RunRow", back_populates="metrics")


class DetectionByTypeRow(Base):
    __tablename__ = "detections_by_type"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    run_id     = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    count      = Column(Integer, nullable=False)

    run = relationship("RunRow", back_populates="detections")


class LatencyByRankRow(Base):
    __tablename__ = "latency_by_rank"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    run_id     = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    rank       = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False)

    run = relationship("RunRow", back_populates="latency_by_rank")


class AccuracyConfidenceCurveRow(Base):
    __tablename__ = "accuracy_confidence_curve"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    run_id    = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    threshold = Column(Float, nullable=False)
    accuracy  = Column(Float, nullable=False)
    fpr       = Column(Float, nullable=False)

    run = relationship("RunRow", back_populates="acc_curve")


class NetworkNodeRow(Base):
    __tablename__ = "network_nodes"
    __table_args__ = (UniqueConstraint("run_id", "node_id", name="uq_run_node"),)

    id              = Column(Integer, primary_key=True, autoincrement=True)
    run_id          = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id         = Column(String(20), nullable=False)
    label           = Column(String(100), nullable=False)
    role            = Column(Enum("command", "relay", "sensor"), nullable=False)
    pos_x           = Column(Float, nullable=False)
    pos_y           = Column(Float, nullable=False)
    lat             = Column(Float, nullable=True)
    lon             = Column(Float, nullable=True)
    battery         = Column(Integer, nullable=False)
    drain           = Column(Float, nullable=False)
    traffic         = Column(Integer, nullable=False)
    health          = Column(Enum("good", "warning", "critical"), nullable=False)
    packets_in      = Column(Integer, nullable=False)
    packets_out     = Column(Integer, nullable=False)
    retries         = Column(Integer, nullable=False)
    collisions      = Column(Integer, nullable=False)
    ai_det          = Column(Integer, nullable=False)
    parent_node_id  = Column(String(20), nullable=True)
    power_radio     = Column(Integer, nullable=False)
    power_processor = Column(Integer, nullable=False)
    power_mic       = Column(Integer, nullable=False)

    run = relationship("RunRow", back_populates="nodes")


class NodeEventRow(Base):
    __tablename__ = "node_events"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    run_id     = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    node_id    = Column(String(20), nullable=False)
    event_text = Column(String(255), nullable=False)

    run = relationship("RunRow", back_populates="node_events")


class NodeChildRow(Base):
    __tablename__ = "node_children"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    run_id         = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    parent_node_id = Column(String(20), nullable=False)
    child_node_id  = Column(String(20), nullable=False)

    run = relationship("RunRow", back_populates="node_children")


class NetworkEdgeRow(Base):
    __tablename__ = "network_edges"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    run_id      = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    from_node   = Column(String(20), nullable=False)
    to_node     = Column(String(20), nullable=False)
    congestion  = Column(Integer, nullable=False)
    packet_loss = Column(Float, nullable=False)
    retries     = Column(Integer, nullable=False)
    collisions  = Column(Integer, nullable=False)
    avg_delay   = Column(Integer, nullable=False)
    reroutes    = Column(Integer, nullable=False)
    latency     = Column(Integer, nullable=False)

    run = relationship("RunRow", back_populates="edges")


class RerouteEventRow(Base):
    __tablename__ = "reroute_events"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    run_id    = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    from_node = Column(String(20), nullable=False)
    to_node   = Column(String(20), nullable=False)

    run = relationship("RunRow", back_populates="reroutes")


class AIEventRow(Base):
    __tablename__ = "ai_events"
    __table_args__ = (Index("idx_run_time", "run_id", "timestamp_ms"),)

    id           = Column(Integer, primary_key=True, autoincrement=True)
    run_id       = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    timestamp_ms = Column(BigInteger, nullable=False)
    node_id      = Column(String(20), nullable=False)
    event_type   = Column(String(50), nullable=False)
    confidence   = Column(Float, nullable=False)
    latency_ms   = Column(Integer, nullable=False)
    energy_mj    = Column(Float, nullable=False)

    run = relationship("RunRow", back_populates="ai_events")