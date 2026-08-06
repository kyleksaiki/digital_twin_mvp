"""
seed.py — Create a single empty template run so the UI has something to load.

Deliberately contains NO mock metrics: every value starts at zero and is
populated by real processing. Detection counts, latency, and detections-by-type
come from the audio pipeline; battery figures come from the battery simulation
when a run is created through Configure Run.

Run once: python -m app.seed  (or set SEED_MOCK_DATA=1 and start the backend)
"""
from datetime import date as Date
from app.database import SessionLocal, init_db
from app.db_models import (
    RunRow, RunMetricsRow, NetworkNodeRow, NodeEventRow,
    NodeChildRow, NetworkEdgeRow, RerouteEventRow,
)

def _zeroed_metrics() -> dict:
    """All metrics start at zero.

    Real values are computed by the audio pipeline
    (services/audio_processing.py fills detection_count and latency_ms) and by
    the battery simulation. Nothing here is fabricated.
    """
    return {
        "accuracy": 0.0, "fpr": 0.0, "latency_ms": 0,
        "detection_count": 0, "battery_health": 0.0,
        "throughput": 0.0, "congestion": 0, "conf_threshold": 0.0,
    }


RAW_NODES = [
    dict(node_id="CMD", label="Command Center", role="command", pos_x=0.50, pos_y=0.10,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id=None,
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="R1", label="Shaman II-1", role="relay", pos_x=0.28, pos_y=0.30,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id=None,
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=["S1","S2","S3","S4"]),
    dict(node_id="R2", label="Shaman II-2", role="relay", pos_x=0.72, pos_y=0.28,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id=None,
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=["S5","S6","S7"]),
    dict(node_id="R3", label="Shaman II-3", role="relay", pos_x=0.50, pos_y=0.48,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id=None,
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=["S8","S9","S10"]),
    dict(node_id="R4", label="Shaman II-4", role="relay", pos_x=0.16, pos_y=0.55,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id=None,
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=["S11"]),
    dict(node_id="S1",  label="Shaman I-01", role="sensor", pos_x=0.10, pos_y=0.36,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R1",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S2",  label="Shaman I-02", role="sensor", pos_x=0.14, pos_y=0.20,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R1",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S3",  label="Shaman I-03", role="sensor", pos_x=0.08, pos_y=0.50,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R1",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S4",  label="Shaman I-04", role="sensor", pos_x=0.22, pos_y=0.42,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R1",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S5",  label="Shaman I-05", role="sensor", pos_x=0.86, pos_y=0.17,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R2",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S6",  label="Shaman I-06", role="sensor", pos_x=0.88, pos_y=0.38,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R2",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S7",  label="Shaman I-07", role="sensor", pos_x=0.78, pos_y=0.44,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R2",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S8",  label="Shaman I-08", role="sensor", pos_x=0.38, pos_y=0.65,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R3",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S9",  label="Shaman I-09", role="sensor", pos_x=0.56, pos_y=0.66,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R3",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S10", label="Shaman I-10", role="sensor", pos_x=0.62, pos_y=0.56,
         battery=0, drain=0.0, traffic=0,  health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R3",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
    dict(node_id="S11", label="Shaman I-11", role="sensor", pos_x=0.24, pos_y=0.70,
         battery=0, drain=0.0, traffic=0, health="good", packets_in=0, packets_out=0,
         retries=0, collisions=0, ai_det=0, parent_node_id="R4",
         power_radio=0, power_processor=0, power_mic=0,
         events=[], children=[]),
]

RAW_EDGES = [
    dict(from_node="CMD", to_node="R1",  congestion=0, packet_loss=0, retries=0,  collisions=0, avg_delay=0, reroutes=0, latency=0),
    dict(from_node="CMD", to_node="R2",  congestion=0, packet_loss=0, retries=0,  collisions=0, avg_delay=0, reroutes=0, latency=0),
    dict(from_node="CMD", to_node="R3",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R1",  to_node="S1",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R1",  to_node="S2",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R1",  to_node="S3",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R1",  to_node="S4",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R1",  to_node="R4",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R2",  to_node="S5",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R2",  to_node="S6",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R2",  to_node="S7",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R3",  to_node="S8",  congestion=0, packet_loss=0, retries=0,   collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R3",  to_node="S9",  congestion=0, packet_loss=0, retries=0,   collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R3",  to_node="S10", congestion=0, packet_loss=0, retries=0,   collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R4",  to_node="S11", congestion=0, packet_loss=0, retries=0,  collisions=0, avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R4",  to_node="S3",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R3",  to_node="R2",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
    dict(from_node="R3",  to_node="R1",  congestion=0, packet_loss=0, retries=0,  collisions=0,  avg_delay=0, reroutes=0, latency=0),
]

RAW_REROUTES = [
    dict(from_node="S3",  to_node="R4"),
    dict(from_node="S7",  to_node="R3"),
    dict(from_node="S11", to_node="R3"),
]

RAW_RUNS = [
    dict(id=1, name="Template_Run_Demo", date="2025-02-17", scenario="Tropical Night", shamani="Radxa Zero", shamanii="Radxa Zero", duration="24h", status="pass"),
]

def seed():
    init_db()
    db = SessionLocal()
    try:
        # Skip if already seeded
        if db.query(RunRow).count() > 0:
            print("DB already seeded — skipping.")
            return
        
        for r in RAW_RUNS:
            run_date = r["date"]
            if isinstance(run_date, str):
                run_date = Date.fromisoformat(run_date)
            run = RunRow(
                id=r["id"], name=r["name"], date=run_date, scenario=r["scenario"], shamani=r["shamani"], shamanii=r["shamanii"], duration=r["duration"], status=r["status"],
            )
            db.add(run)
            db.flush()  # get run.id

            # Metrics — all zero until real audio is processed.
            db.add(RunMetricsRow(run_id=run.id, **_zeroed_metrics()))

            # No detections-by-type, latency-by-rank, or accuracy-curve rows are
            # seeded. The audio pipeline creates detections-by-type from real
            # AI events; the charts render empty until then.

            # Nodes (same topology for every run — realistic for MVP)
            for n in RAW_NODES:
                node = NetworkNodeRow(
                    run_id=run.id,
                    node_id=n["node_id"], label=n["label"], role=n["role"],
                    pos_x=n["pos_x"], pos_y=n["pos_y"],
                    battery=n["battery"], drain=n["drain"], traffic=n["traffic"],
                    health=n["health"], packets_in=n["packets_in"], packets_out=n["packets_out"],
                    retries=n["retries"], collisions=n["collisions"], ai_det=n["ai_det"],
                    parent_node_id=n["parent_node_id"],
                    power_radio=n["power_radio"], power_processor=n["power_processor"],
                    power_mic=n["power_mic"],
                )
                db.add(node)
                for ev in n["events"]:
                    db.add(NodeEventRow(run_id=run.id, node_id=n["node_id"], event_text=ev))
                for child in n["children"]:
                    db.add(NodeChildRow(run_id=run.id, parent_node_id=n["node_id"], child_node_id=child))

            # Edges
            for e in RAW_EDGES:
                db.add(NetworkEdgeRow(run_id=run.id, **e))

            # Reroutes
            for rr in RAW_REROUTES:
                db.add(RerouteEventRow(run_id=run.id, **rr))

        db.commit()
        print(f"Seeded {len(RAW_RUNS)} template run(s) with zeroed metrics — no mock data.")
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


if __name__ == "__main__":
    seed()