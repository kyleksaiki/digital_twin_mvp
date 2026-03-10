"""
seed.py — Populate the DB with the same data currently in mock_data.py.
Run once: python -m app.seed
The UI will render identically — data just comes from DB now.
"""
import math
from datetime import date as Date
from app.database import SessionLocal, init_db
from app.db_models import (
    RunRow, RunMetricsRow, DetectionByTypeRow, LatencyByRankRow,
    AccuracyConfidenceCurveRow, NetworkNodeRow, NodeEventRow,
    NodeChildRow, NetworkEdgeRow, RerouteEventRow,
)

# ── helpers ──────────────────────────────────────────────────────────────────

def _metrics_for_status(status: str) -> dict:
    base = {
        "accuracy": 94.2, "fpr": 6.8, "latency_ms": 48,
        "detection_count": 127, "battery_health": 62.0,
        "throughput": 12.4, "congestion": 22, "conf_threshold": 0.65,
    }
    if status == "warning":
        base.update({"accuracy": 88.5, "battery_health": 35.0, "congestion": 65})
    elif status == "fail":
        base.update({"accuracy": 78.2, "battery_health": 15.0, "congestion": 92})
    return base


def _detection_counts_for_status(status: str) -> list[dict]:
    """Slightly vary detection counts by status so each run looks different."""
    if status == "pass":
        return [
            {"event_type": "Bird",     "count": 42},
            {"event_type": "Gunshot",  "count": 28},
            {"event_type": "Chainsaw", "count": 22},
            {"event_type": "Voice",    "count": 20},
            {"event_type": "Vehicle",  "count": 15},
        ]
    elif status == "warning":
        return [
            {"event_type": "Bird",     "count": 30},
            {"event_type": "Gunshot",  "count": 18},
            {"event_type": "Chainsaw", "count": 28},
            {"event_type": "Voice",    "count": 14},
            {"event_type": "Vehicle",  "count": 10},
        ]
    else:  # fail
        return [
            {"event_type": "Bird",     "count": 15},
            {"event_type": "Gunshot",  "count": 9},
            {"event_type": "Chainsaw", "count": 35},
            {"event_type": "Voice",    "count": 8},
            {"event_type": "Vehicle",  "count": 6},
        ]


def _latency_by_rank_for_status(status: str) -> list[dict]:
    if status == "pass":
        return [{"rank": 1, "latency_ms": 38}, {"rank": 2, "latency_ms": 95}, {"rank": 3, "latency_ms": 142}]
    elif status == "warning":
        return [{"rank": 1, "latency_ms": 55}, {"rank": 2, "latency_ms": 120}, {"rank": 3, "latency_ms": 198}]
    else:
        return [{"rank": 1, "latency_ms": 80}, {"rank": 2, "latency_ms": 165}, {"rank": 3, "latency_ms": 260}]


def _acc_curve(status: str) -> list[dict]:
    """Generate accuracy/FPR curve points from threshold 0.30 to 0.95."""
    rows = []
    acc_peak = {"pass": 97.0, "warning": 92.0, "fail": 82.0}[status]
    for i in range(14):
        t = round(0.30 + i * 0.05, 2)
        acc = acc_peak * (1 - 0.3 * max(0, t - 0.65))
        fpr = max(0, 18.0 * math.exp(-4 * t) + 1.5)
        rows.append({"threshold": t, "accuracy": round(acc, 1), "fpr": round(fpr, 1)})
    return rows


# ── raw mock node data (mirrors mock_data.py exactly) ────────────────────────

RAW_NODES = [
    dict(node_id="CMD", label="Command Center", role="command", pos_x=0.50, pos_y=0.10,
         battery=100, drain=0.1, traffic=95, health="good", packets_in=4820, packets_out=312,
         retries=24, collisions=8, ai_det=127, parent_node_id=None,
         power_radio=15, power_processor=5, power_mic=0,
         events=["System boot", "All nodes online", "12 reroutes"], children=[]),
    dict(node_id="R1", label="Shaman II-1", role="relay", pos_x=0.28, pos_y=0.30,
         battery=23, drain=3.2, traffic=89, health="critical", packets_in=2640, packets_out=2580,
         retries=186, collisions=42, ai_det=0, parent_node_id=None,
         power_radio=55, power_processor=30, power_mic=15,
         events=["High relay load", "Battery warning"], children=["S1","S2","S3","S4"]),
    dict(node_id="R2", label="Shaman II-2", role="relay", pos_x=0.72, pos_y=0.28,
         battery=34, drain=2.8, traffic=82, health="warning", packets_in=2180, packets_out=2120,
         retries=148, collisions=35, ai_det=0, parent_node_id=None,
         power_radio=50, power_processor=32, power_mic=18,
         events=["Relay congestion", "Packet loss spike"], children=["S5","S6","S7"]),
    dict(node_id="R3", label="Shaman II-3", role="relay", pos_x=0.50, pos_y=0.48,
         battery=61, drain=1.4, traffic=45, health="good", packets_in=980, packets_out=940,
         retries=52, collisions=11, ai_det=0, parent_node_id=None,
         power_radio=40, power_processor=35, power_mic=25,
         events=["Normal operation"], children=["S8","S9","S10"]),
    dict(node_id="R4", label="Shaman II-4", role="relay", pos_x=0.16, pos_y=0.55,
         battery=55, drain=1.6, traffic=52, health="warning", packets_in=1120, packets_out=1080,
         retries=68, collisions=15, ai_det=0, parent_node_id=None,
         power_radio=45, power_processor=33, power_mic=22,
         events=["Moderate load"], children=["S11"]),
    dict(node_id="S1",  label="Shaman I-01", role="sensor", pos_x=0.10, pos_y=0.36,
         battery=72, drain=0.8, traffic=15, health="good", packets_in=42, packets_out=280,
         retries=12, collisions=3, ai_det=18, parent_node_id="R1",
         power_radio=30, power_processor=25, power_mic=45,
         events=["8 gunshot","6 bird"], children=[]),
    dict(node_id="S2",  label="Shaman I-02", role="sensor", pos_x=0.14, pos_y=0.20,
         battery=68, drain=0.9, traffic=18, health="good", packets_in=38, packets_out=310,
         retries=15, collisions=4, ai_det=22, parent_node_id="R1",
         power_radio=28, power_processor=27, power_mic=45,
         events=["12 bird","6 chainsaw"], children=[]),
    dict(node_id="S3",  label="Shaman I-03", role="sensor", pos_x=0.08, pos_y=0.50,
         battery=45, drain=1.1, traffic=22, health="warning", packets_in=52, packets_out=340,
         retries=28, collisions=8, ai_det=14, parent_node_id="R1",
         power_radio=35, power_processor=22, power_mic=43,
         events=["High retries","9 bird"], children=[]),
    dict(node_id="S4",  label="Shaman I-04", role="sensor", pos_x=0.22, pos_y=0.42,
         battery=78, drain=0.7, traffic=12, health="good", packets_in=36, packets_out=260,
         retries=8, collisions=2, ai_det=11, parent_node_id="R1",
         power_radio=26, power_processor=24, power_mic=50,
         events=["Normal","7 bird"], children=[]),
    dict(node_id="S5",  label="Shaman I-05", role="sensor", pos_x=0.86, pos_y=0.17,
         battery=70, drain=0.8, traffic=16, health="good", packets_in=40, packets_out=290,
         retries=14, collisions=3, ai_det=19, parent_node_id="R2",
         power_radio=30, power_processor=25, power_mic=45,
         events=["10 bird","5 gunshot"], children=[]),
    dict(node_id="S6",  label="Shaman I-06", role="sensor", pos_x=0.88, pos_y=0.38,
         battery=64, drain=0.9, traffic=20, health="good", packets_in=48, packets_out=320,
         retries=18, collisions=5, ai_det=16, parent_node_id="R2",
         power_radio=32, power_processor=23, power_mic=45,
         events=["8 bird","5 voice"], children=[]),
    dict(node_id="S7",  label="Shaman I-07", role="sensor", pos_x=0.78, pos_y=0.44,
         battery=58, drain=1.0, traffic=24, health="warning", packets_in=55, packets_out=350,
         retries=22, collisions=7, ai_det=13, parent_node_id="R2",
         power_radio=34, power_processor=24, power_mic=42,
         events=["Moderate retries","8 bird"], children=[]),
    dict(node_id="S8",  label="Shaman I-08", role="sensor", pos_x=0.38, pos_y=0.65,
         battery=80, drain=0.6, traffic=10, health="good", packets_in=30, packets_out=240,
         retries=6, collisions=1, ai_det=8, parent_node_id="R3",
         power_radio=25, power_processor=25, power_mic=50,
         events=["Low traffic","5 bird"], children=[]),
    dict(node_id="S9",  label="Shaman I-09", role="sensor", pos_x=0.56, pos_y=0.66,
         battery=75, drain=0.7, traffic=14, health="good", packets_in=35, packets_out=270,
         retries=10, collisions=2, ai_det=10, parent_node_id="R3",
         power_radio=28, power_processor=24, power_mic=48,
         events=["Normal","6 bird"], children=[]),
    dict(node_id="S10", label="Shaman I-10", role="sensor", pos_x=0.62, pos_y=0.56,
         battery=82, drain=0.6, traffic=9,  health="good", packets_in=28, packets_out=230,
         retries=5, collisions=1, ai_det=6, parent_node_id="R3",
         power_radio=24, power_processor=26, power_mic=50,
         events=["Low load","4 bird"], children=[]),
    dict(node_id="S11", label="Shaman I-11", role="sensor", pos_x=0.24, pos_y=0.70,
         battery=42, drain=1.2, traffic=28, health="warning", packets_in=60, packets_out=380,
         retries=32, collisions=10, ai_det=20, parent_node_id="R4",
         power_radio=36, power_processor=22, power_mic=42,
         events=["High detection"], children=[]),
]

RAW_EDGES = [
    dict(from_node="CMD", to_node="R1",  congestion=88, packet_loss=6.2, retries=86,  collisions=22, avg_delay=68, reroutes=4, latency=52),
    dict(from_node="CMD", to_node="R2",  congestion=80, packet_loss=5.1, retries=72,  collisions=18, avg_delay=55, reroutes=3, latency=48),
    dict(from_node="CMD", to_node="R3",  congestion=35, packet_loss=1.8, retries=22,  collisions=5,  avg_delay=28, reroutes=1, latency=32),
    dict(from_node="R1",  to_node="S1",  congestion=42, packet_loss=2.4, retries=18,  collisions=5,  avg_delay=32, reroutes=1, latency=28),
    dict(from_node="R1",  to_node="S2",  congestion=48, packet_loss=2.8, retries=22,  collisions=6,  avg_delay=35, reroutes=1, latency=30),
    dict(from_node="R1",  to_node="S3",  congestion=55, packet_loss=3.5, retries=30,  collisions=9,  avg_delay=42, reroutes=2, latency=38),
    dict(from_node="R1",  to_node="S4",  congestion=38, packet_loss=1.9, retries=14,  collisions=3,  avg_delay=25, reroutes=0, latency=22),
    dict(from_node="R1",  to_node="R4",  congestion=52, packet_loss=3.0, retries=28,  collisions=7,  avg_delay=38, reroutes=2, latency=35),
    dict(from_node="R2",  to_node="S5",  congestion=44, packet_loss=2.5, retries=20,  collisions=5,  avg_delay=30, reroutes=1, latency=26),
    dict(from_node="R2",  to_node="S6",  congestion=50, packet_loss=3.0, retries=24,  collisions=6,  avg_delay=36, reroutes=1, latency=32),
    dict(from_node="R2",  to_node="S7",  congestion=58, packet_loss=3.8, retries=28,  collisions=8,  avg_delay=44, reroutes=2, latency=40),
    dict(from_node="R3",  to_node="S8",  congestion=18, packet_loss=0.8, retries=6,   collisions=1,  avg_delay=15, reroutes=0, latency=14),
    dict(from_node="R3",  to_node="S9",  congestion=22, packet_loss=1.0, retries=8,   collisions=2,  avg_delay=18, reroutes=0, latency=16),
    dict(from_node="R3",  to_node="S10", congestion=15, packet_loss=0.6, retries=4,   collisions=1,  avg_delay=12, reroutes=0, latency=12),
    dict(from_node="R4",  to_node="S11", congestion=60, packet_loss=4.2, retries=34,  collisions=10, avg_delay=48, reroutes=3, latency=42),
    dict(from_node="R4",  to_node="S3",  congestion=30, packet_loss=1.5, retries=12,  collisions=3,  avg_delay=22, reroutes=1, latency=20),
    dict(from_node="R3",  to_node="R2",  congestion=28, packet_loss=1.2, retries=10,  collisions=2,  avg_delay=20, reroutes=0, latency=18),
    dict(from_node="R3",  to_node="R1",  congestion=32, packet_loss=1.6, retries=14,  collisions=3,  avg_delay=24, reroutes=1, latency=22),
]

RAW_REROUTES = [
    dict(from_node="S3",  to_node="R4"),
    dict(from_node="S7",  to_node="R3"),
    dict(from_node="S11", to_node="R3"),
]

# Raw run data (mirrors MOCK_RUNS)
RAW_RUNS = [
    dict(id=1,  name="Forest_Night_01",    date="2025-02-17", scenario="Tropical Night",  model="BirdNET v2.4", hw="Radxa Zero", duration="24h", status="pass"),
    dict(id=2,  name="Forest_Dawn_03",     date="2025-02-16", scenario="Dawn Chorus",     model="BirdNET v2.3", hw="ESP32",      duration="12h", status="warning"),
    dict(id=3,  name="Urban_Park_07",      date="2025-02-15", scenario="Urban Noise",     model="BirdNET v2.4", hw="Radxa Zero", duration="8h",  status="pass"),
    dict(id=4,  name="Wetland_Rain_02",    date="2025-02-14", scenario="Wetland Rain",    model="BirdNET v2.3", hw="ESP32",      duration="24h", status="fail"),
    dict(id=5,  name="Mountain_Clear_05",  date="2025-02-13", scenario="Mountain Clear",  model="BirdNET v2.4", hw="Radxa Zero", duration="16h", status="pass"),
    dict(id=6,  name="Forest_Storm_04",    date="2025-02-12", scenario="Storm Event",     model="BirdNET v2.2", hw="ESP32",      duration="6h",  status="warning"),
    dict(id=7,  name="Coastal_Night_01",   date="2025-02-11", scenario="Coastal Night",   model="BirdNET v2.4", hw="Radxa Zero", duration="24h", status="pass"),
    dict(id=8,  name="Desert_Day_02",      date="2025-02-10", scenario="Desert Sparse",   model="BirdNET v2.3", hw="ESP32",      duration="12h", status="pass"),
    dict(id=9,  name="Jungle_Dense_06",    date="2025-02-09", scenario="Dense Canopy",    model="BirdNET v2.4", hw="Radxa Zero", duration="24h", status="warning"),
    dict(id=10, name="River_Valley_03",    date="2025-02-08", scenario="River Valley",    model="BirdNET v2.2", hw="ESP32",      duration="8h",  status="pass"),
]


# ── seed function ─────────────────────────────────────────────────────────────

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
                id=r["id"], name=r["name"], date=run_date,
                scenario=r["scenario"], model=r["model"],
                hw=r["hw"], duration=r["duration"], status=r["status"],
            )
            db.add(run)
            db.flush()  # get run.id

            # Metrics
            m = _metrics_for_status(r["status"])
            db.add(RunMetricsRow(run_id=run.id, **m))

            # Detections by type
            for det in _detection_counts_for_status(r["status"]):
                db.add(DetectionByTypeRow(run_id=run.id, **det))

            # Latency by rank
            for lr in _latency_by_rank_for_status(r["status"]):
                db.add(LatencyByRankRow(run_id=run.id, **lr))

            # Accuracy/confidence curve
            for pt in _acc_curve(r["status"]):
                db.add(AccuracyConfidenceCurveRow(run_id=run.id, **pt))

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
        print(f"Seeded {len(RAW_RUNS)} runs with full topology and metrics.")
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


if __name__ == "__main__":
    seed()