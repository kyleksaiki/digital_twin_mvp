"""
SQLAlchemy ORM models — mirror of schema.sql.
Drop-in alongside existing models.py (Pydantic) without touching it.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Date, Enum, BigInteger,
    ForeignKey, UniqueConstraint, Index, TIMESTAMP, func, JSON,
    Boolean, Text,
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
    status     = Column(Enum("pass", "warning", "fail", "processing", "complete", "failed"), nullable=False, default="pass")
    created_at = Column(TIMESTAMP, server_default=func.now())
    calibration_data = Column(JSON, nullable=True)

    # Relationships
    metrics            = relationship("RunMetricsRow",            back_populates="run", uselist=False, cascade="all, delete-orphan")
    detections         = relationship("DetectionByTypeRow",       back_populates="run", cascade="all, delete-orphan")
    latency_by_rank    = relationship("LatencyByRankRow",         back_populates="run", cascade="all, delete-orphan")
    acc_curve          = relationship("AccuracyConfidenceCurveRow", back_populates="run", cascade="all, delete-orphan")
    nodes              = relationship("NetworkNodeRow",           back_populates="run", cascade="all, delete-orphan")
    audio_files        = relationship("NodeAudioRow",            back_populates="run", cascade="all, delete-orphan")
    node_events        = relationship("NodeEventRow",             back_populates="run", cascade="all, delete-orphan")
    node_children      = relationship("NodeChildRow",             back_populates="run", cascade="all, delete-orphan")
    edges              = relationship("NetworkEdgeRow",           back_populates="run", cascade="all, delete-orphan")
    reroutes           = relationship("RerouteEventRow",          back_populates="run", cascade="all, delete-orphan")
    ai_events          = relationship("AIEventRow",               back_populates="run", cascade="all, delete-orphan")
    battery_sim        = relationship("BatterySimResultRow",      back_populates="run", uselist=False, cascade="all, delete-orphan")
    pipeline_stages    = relationship("PipelineStageStatRow",     back_populates="run", cascade="all, delete-orphan")
    processing_stats   = relationship("AudioProcessingStatRow",   back_populates="run", uselist=False, cascade="all, delete-orphan")
    ground_truth_eval  = relationship("GroundTruthEvalRow",       back_populates="run", uselist=False, cascade="all, delete-orphan")


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


class NodeAudioRow(Base):
    __tablename__ = "node_audio_files"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    run_id     = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id    = Column(String(20), nullable=False)
    audio_path = Column(String(512), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    run = relationship("RunRow", back_populates="audio_files")


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


class BatterySimResultRow(Base):
    """Full single-node battery simulator output for a run — one row per run.

    The existing NetworkNodeRow battery/power columns are Integer and truncate
    the simulator's sub-watt values to 0, so the full-precision output lives
    here. NetworkNodeRow.battery/drain still receive rounded mirrors for
    legacy consumers, but this table is the source of truth for the Battery
    Statistics page.
    """
    __tablename__ = "battery_sim_results"

    id                          = Column(Integer, primary_key=True, autoincrement=True)
    run_id                      = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id                     = Column(String(20), nullable=False)
    battery_wh                  = Column(Float, nullable=False)
    energy_consumed_wh          = Column(Float, nullable=False)
    energy_remaining_wh         = Column(Float, nullable=False)
    final_battery_percent       = Column(Float, nullable=False)
    average_power_w             = Column(Float, nullable=False)
    avg_drain_percent_per_hour  = Column(Float, nullable=False)
    projected_total_life_hours  = Column(Float, nullable=True)
    duration_hours              = Column(Float, nullable=False)
    duration_source             = Column(String(20), nullable=False, default="dropdown")
    total_detections            = Column(Integer, nullable=False, default=0)
    alive                       = Column(Boolean, nullable=False, default=True)
    series_json                 = Column(Text, nullable=False)      # battery_over_time array
    breakdown_json              = Column(Text, nullable=False)      # per-component Wh breakdown
    created_at                  = Column(TIMESTAMP, server_default=func.now())

    run = relationship("RunRow", back_populates="battery_sim")


class PipelineStageStatRow(Base):
    """Real per-stage pass/fail/timing for the 5-stage audio pipeline.

    One row per run per UI stage (stage1..stage5), derived from actual
    workflow timelines by services/aed/stage_stats.py. Never seeded with
    mock values — absent rows simply mean no audio was processed.
    """
    __tablename__ = "pipeline_stage_stats"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    run_id       = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id     = Column(String(20), nullable=False)     # stage1..stage5
    stage_label  = Column(String(80), nullable=False)
    entered      = Column(Integer, nullable=False, default=0)
    passed       = Column(Integer, nullable=False, default=0)
    failed       = Column(Integer, nullable=False, default=0)
    mean_ms      = Column(Float, nullable=False, default=0.0)
    total_ms     = Column(Float, nullable=False, default=0.0)
    details_json = Column(Text, nullable=False, default="[]")
    created_at   = Column(TIMESTAMP, server_default=func.now())

    run = relationship("RunRow", back_populates="pipeline_stages")


class AudioProcessingStatRow(Base):
    """Per-run AED processing measurements and model provenance.

    val_* columns are the checkpoint's held-out validation metrics — model
    card material, NOT this run's accuracy. They are stored per run so a
    reviewer can always tell which model produced a given run's numbers.
    """
    __tablename__ = "audio_processing_stats"

    id                        = Column(Integer, primary_key=True, autoincrement=True)
    run_id                    = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    model_status              = Column(String(120), nullable=False, default="unknown")
    checkpoint_file           = Column(String(120), nullable=True)
    model_version             = Column(String(255), nullable=True)
    threshold                 = Column(Float, nullable=False, default=0.0)
    device                    = Column(String(20), nullable=True)
    clips_scored              = Column(Integer, nullable=False, default=0)
    clips_skipped             = Column(Integer, nullable=False, default=0)
    mean_confidence           = Column(Float, nullable=False, default=0.0)
    confidence_histogram_json = Column(Text, nullable=False, default="[]")
    audio_seconds             = Column(Float, nullable=False, default=0.0)
    wall_ms                   = Column(Float, nullable=False, default=0.0)
    throughput_cps            = Column(Float, nullable=False, default=0.0)
    val_acc                   = Column(Float, nullable=True)
    val_precision             = Column(Float, nullable=True)
    val_recall                = Column(Float, nullable=True)
    val_f1                    = Column(Float, nullable=True)
    created_at                = Column(TIMESTAMP, server_default=func.now())

    run = relationship("RunRow", back_populates="processing_stats")


class GroundTruthEvalRow(Base):
    """Measured detection performance for this run against a supplied ground-truth log.

    Unlike the val_* columns on AudioProcessingStatRow (which describe the
    model's held-out validation set), every number here is measured on the
    audio the user actually uploaded.
    """
    __tablename__ = "ground_truth_eval"

    id                        = Column(Integer, primary_key=True, autoincrement=True)
    run_id                    = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    total_events              = Column(Integer, nullable=False, default=0)
    total_detections          = Column(Integer, nullable=False, default=0)
    matched_events            = Column(Integer, nullable=False, default=0)
    missed_events             = Column(Integer, nullable=False, default=0)
    true_positive_detections  = Column(Integer, nullable=False, default=0)
    false_positive_detections = Column(Integer, nullable=False, default=0)
    recall                    = Column(Float, nullable=False, default=0.0)
    precision                 = Column(Float, nullable=False, default=0.0)
    f1                        = Column(Float, nullable=False, default=0.0)
    detections_per_event      = Column(Float, nullable=False, default=0.0)
    by_type_json              = Column(Text, nullable=False, default="[]")
    created_at                = Column(TIMESTAMP, server_default=func.now())

    run = relationship("RunRow", back_populates="ground_truth_eval")