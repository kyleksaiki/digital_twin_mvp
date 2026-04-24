"""
Standalone battery-simulation CLI.

What this script does:
  Runs the same `BatterySimulator` the API uses, but without needing the
  database or the frontend. Pass in a topology (or a mock spec), optional
  power config, and an optional AI event timeline JSON, and it writes
  the battery-over-time data to CSV / JSON.

Usage examples
==============

# 1) Quick smoke test with a synthetic network + mock events
python scripts/run_battery_sim.py \
    --mock-topology 3S-1R-1C \
    --duration-hours 12 \
    --events-per-node 25 \
    --out-csv /tmp/battery.csv

# 2) Real run — AI event log + GUI-exported config JSON
python scripts/run_battery_sim.py \
    --topology topology.json \
    --config configs.json \
    --ai-events combined_ai_event_timeline.json \
    --media-files media_files.json \
    --duration-hours 12 \
    --out-csv battery.csv --out-json battery.json


Input file formats
==================

topology.json (same shape as the POST /api/runs/create body):
{
  "nodes": [
    {"id": "CMD1", "role": "command"},
    {"id": "R1",   "role": "relay"},
    {"id": "S1",   "role": "sensor"},
    {"id": "S2",   "role": "sensor"}
  ],
  "edges": [
    {"from": "R1", "to": "CMD1"},
    {"from": "S1", "to": "R1"},
    {"from": "S2", "to": "R1"}
  ]
}

configs.json:
{
  "shaman_i":  {"batteryLife": 30, "components": { ... }},
  "shaman_ii": {"batteryLife": 50, "components": { ... }},
  "radio":     {"packet_bytes": 128, "spreading_factor": 10}
}

media_files.json:  {"S1": "node_001_....wav", ...}
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.simulation.config import SimulationConfig
from app.simulation.engine import BatterySimulator
from app.simulation.events import EventTimeline
from app.simulation.network import NodeRole, SimNetwork, SimNode
from app.simulation.ai_event_loader import (
    infer_node_map_from_media_files,
    load_ai_events_with_stats,
)


def load_topology(path: Path) -> SimNetwork:
    with open(path, "r") as f:
        data = json.load(f)
    net = SimNetwork()
    for n in data.get("nodes", []):
        net.add_node(SimNode(
            node_id=n["id"],
            role=NodeRole(n["role"]),
        ))
    for e in data.get("edges", []):
        frm = e["from"]
        to  = e["to"]
        child  = net.get_node(frm)
        parent = net.get_node(to)
        if child and parent:
            child.parent_id = to
            if frm not in parent.children_ids:
                parent.children_ids.append(frm)
    return net


def build_mock_topology(spec: str) -> SimNetwork:
    """e.g. '3S-1R-1C' → 3 sensors under 1 relay under 1 command."""
    parts = spec.upper().split("-")
    counts = {"S": 0, "R": 0, "C": 0}
    for p in parts:
        if p and p[-1] in counts and p[:-1].isdigit():
            counts[p[-1]] = int(p[:-1])
    counts.setdefault("C", 1)
    if counts["C"] < 1:
        counts["C"] = 1

    net = SimNetwork()
    cmd_ids = [f"CMD{i+1}" for i in range(counts["C"])]
    for cid in cmd_ids:
        net.add_node(SimNode(node_id=cid, role=NodeRole.COMMAND))

    relay_ids = [f"R{i+1}" for i in range(counts["R"])]
    for i, rid in enumerate(relay_ids):
        parent = cmd_ids[i % len(cmd_ids)]
        net.add_node(SimNode(node_id=rid, role=NodeRole.RELAY, parent_id=parent))
        net.get_node(parent).children_ids.append(rid)

    parent_pool = relay_ids or cmd_ids
    for i in range(counts["S"]):
        sid = f"S{i+1}"
        parent = parent_pool[i % len(parent_pool)]
        net.add_node(SimNode(node_id=sid, role=NodeRole.SENSOR, parent_id=parent))
        net.get_node(parent).children_ids.append(sid)

    return net


def write_csv(result: dict, path: Path) -> None:
    """Long-format CSV: one row per (node, timestep)."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "role", "capacity_wh",
                    "time_seconds", "time_hours",
                    "battery_percent", "battery_wh"])
        for node_id, nd in result["nodes"].items():
            role = nd["role"]
            cap  = nd["capacity_wh"]
            for pt in nd["time_series"]:
                w.writerow([node_id, role, cap,
                            pt["time_seconds"], pt["time_hours"],
                            pt["battery_percent"], pt["battery_wh"]])


def print_summary(result: dict) -> None:
    print(f"\nSimulation {result['simulation_id']}")
    print(f"  duration:   {result['duration_hours']:.2f} h")
    print(f"  events:     {result['total_events']}")
    r = result.get("radio", {})
    print(f"  radio:      SF{r.get('spreading_factor')} "
          f"BW{r.get('bandwidth_hz', 0)//1000}kHz "
          f"{r.get('packet_bytes')}B × {r.get('frames_per_hop')} frames "
          f"@ {r.get('airtime_per_frame_ms')} ms each")
    s = result["summary"]
    print(f"  worst:      {s['worst_node_id']} @ {s['worst_battery_percent']}%")
    print(f"\n  {'node_id':<8}{'role':<9}{'cap_Wh':>8}"
          f"{'final%':>9}{'drawn_Wh':>11}{'detected':>10}{'fwded':>8}")
    for nid, nd in result["nodes"].items():
        sm = nd["summary"]
        print(f"  {nid:<8}{nd['role']:<9}{nd['capacity_wh']:>8}"
              f"{sm['final_battery_percent']:>9}"
              f"{sm['energy_consumed_wh']:>11}"
              f"{sm['n_local']:>10}"
              f"{sm['n_forward']:>8}")


def main():
    p = argparse.ArgumentParser(
        description="Run the battery simulator and export time-series data.")
    topo = p.add_mutually_exclusive_group(required=True)
    topo.add_argument("--topology", type=Path,
                      help="Path to topology JSON (nodes + edges)")
    topo.add_argument("--mock-topology", type=str,
                      help="Synthetic topology spec, e.g. '3S-1R-1C'")

    p.add_argument("--config", type=Path,
                   help="Path to configs JSON with shaman_i/shaman_ii/radio blocks")
    p.add_argument("--ai-events", type=Path,
                   help="Path to the AI event timeline JSON")
    p.add_argument("--media-files", type=Path,
                   help="JSON: {node_id: source_filename} for event → node mapping")
    p.add_argument("--events-per-node", type=int, default=20,
                   help="Used with --mock-topology when no --ai-events given")

    p.add_argument("--duration-hours", type=float, default=12.0)
    p.add_argument("--time-step-seconds", type=float, default=60.0)

    p.add_argument("--out-csv", type=Path, help="Per-timestep CSV output path")
    p.add_argument("--out-json", type=Path, help="Full result JSON output path")

    args = p.parse_args()

    if args.topology:
        network = load_topology(args.topology)
    else:
        network = build_mock_topology(args.mock_topology)
    sensor_ids = [n.node_id for n in network.nodes.values()
                  if n.role == NodeRole.SENSOR]
    if not sensor_ids:
        raise SystemExit("Topology has no sensor nodes — nothing to simulate.")

    shaman_i_cfg = shaman_ii_cfg = radio_cfg = None
    if args.config:
        with open(args.config) as f:
            config_data = json.load(f)
        shaman_i_cfg  = config_data.get("shaman_i")
        shaman_ii_cfg = config_data.get("shaman_ii")
        radio_cfg     = config_data.get("radio")
    config = SimulationConfig.from_run_config(
        shaman_i_config=shaman_i_cfg,
        shaman_ii_config=shaman_ii_cfg,
        radio_config=radio_cfg,
    )
    config.time_step_seconds = args.time_step_seconds

    if args.ai_events:
        media_files = {}
        if args.media_files:
            with open(args.media_files) as f:
                media_files = json.load(f)
        node_map = infer_node_map_from_media_files(media_files)
        timeline, stats = load_ai_events_with_stats(
            path=args.ai_events,
            node_id_map=node_map,
            duration_hours=args.duration_hours,
        )
        print(f"[ai-events] mapped {stats['mapped_events']}/"
              f"{stats['total_entries']} entries  "
              f"(confirmed={stats['confirmed_events']}, "
              f"candidates={stats['candidate_events']})")
        if stats["unmatched_files"]:
            print(f"[ai-events] unmatched source_files: "
                  f"{len(stats['unmatched_files'])}")
            for fn, n in list(stats["unmatched_files"].items())[:5]:
                print(f"            - {fn}  ({n}x)")
    else:
        timeline = EventTimeline.generate_mock(
            sensor_ids,
            duration_hours=args.duration_hours,
            events_per_node=args.events_per_node,
        )
        print(f"[mock] generated {len(timeline.events)} events "
              f"(confirmed={timeline.confirmed_count()})")

    sim = BatterySimulator(config, network, timeline,
                           duration_hours=args.duration_hours)
    result = sim.run()

    print_summary(result)
    if args.out_csv:
        write_csv(result, args.out_csv)
        print(f"\nWrote CSV: {args.out_csv}")
    if args.out_json:
        with open(args.out_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote JSON: {args.out_json}")


if __name__ == "__main__":
    main()
