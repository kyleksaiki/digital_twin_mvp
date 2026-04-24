"""
Minimal end-to-end test of the battery simulator.

What this script does:
  1. Builds a tiny test network entirely in memory:
        S1 (sensor)  --WiFi-->  R1 (relay)  --LoRa-->  CMD1 (gateway)
  2. Generates a fixed list of test AI events on S1.
  3. Runs the BatterySimulator for 1 hour.
  4. Prints the math by hand alongside the simulator's numbers, so the
     values can be verified term by term.

Run it:
    cd backend
    source .venv/bin/activate
    python scripts/test_battery_sim.py
"""
from __future__ import annotations
import sys
from pathlib import Path

SCRIPT_DIR  = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.simulation.config  import SimulationConfig
from app.simulation.engine  import BatterySimulator
from app.simulation.events  import EventTimeline, SimEvent
from app.simulation.network import NodeRole, SimNetwork, SimNode


def build_test_network() -> SimNetwork:
    """S1 (sensor) -> R1 (relay) -> CMD1 (gateway)."""
    net = SimNetwork()
    net.add_node(SimNode(node_id="CMD1", role=NodeRole.COMMAND))
    net.add_node(SimNode(node_id="R1",   role=NodeRole.RELAY,  parent_id="CMD1"))
    net.add_node(SimNode(node_id="S1",   role=NodeRole.SENSOR, parent_id="R1"))
    net.get_node("CMD1").children_ids = ["R1"]
    net.get_node("R1").children_ids   = ["S1"]
    return net


def build_test_events() -> EventTimeline:
    """5 detections on S1, evenly spaced across the run."""
    return EventTimeline(events=[
        SimEvent(node_id="S1", timestamp_s=t, event_type="bird_confirmed",
                 confirmed=True)
        for t in (300, 900, 1500, 2100, 2700)   # at 5/15/25/35/45 minutes
    ])


def predicted_energy(cfg: SimulationConfig,
                     duration_h: float,
                     n_events: int) -> dict:
    """Re-derive the expected energy values purely from the equations,
    independently of the engine, so we can compare the two."""
    s1, s2, r = cfg.shaman_i, cfg.shaman_ii, cfg.radio
    frames = r.frames_per_hop
    t_lora = r.airtime_per_frame_s()
    SEC_PER_HR = 3600.0

    # Shaman I
    e_baseline_s1 = (s1.P_proc_shaI_active + s1.P_mic) * duration_h
    e_tx_s1       = n_events * s1.P_wifi_tx * (s1.t_tx_wifi * frames) / SEC_PER_HR
    e_total_s1    = e_baseline_s1 + e_tx_s1

    # Shaman II (R1) — receives n_events from S1, processes them, forwards via LoRa
    e_baseline_r1 = (s2.P_controller_sleep + s2.P_lora_rx + s2.P_proc_shaII_sleep) * duration_h
    e_rx_wifi_r1  = n_events * s2.P_wifi_rx * (s2.t_rx_wifi / SEC_PER_HR)
    e_process_r1  = n_events * (s2.P_proc_shaII_active - s2.P_proc_shaII_sleep) \
                              * (s2.t_proc_shaII / SEC_PER_HR)
    e_tx_lora_r1  = n_events * s2.P_lora_tx * (t_lora * frames) / SEC_PER_HR
    e_total_r1    = e_baseline_r1 + e_rx_wifi_r1 + e_process_r1 + e_tx_lora_r1

    # CMD1 — gateway: same baseline as relay, receives from R1 (LoRa), no forward
    e_baseline_cmd = (s2.P_controller_sleep + s2.P_lora_rx + s2.P_proc_shaII_sleep) * duration_h
    e_rx_lora_cmd  = n_events * s2.P_lora_rx * (t_lora / SEC_PER_HR)
    e_process_cmd  = n_events * (s2.P_proc_shaII_active - s2.P_proc_shaII_sleep) \
                              * (s2.t_proc_shaII / SEC_PER_HR)
    e_total_cmd    = e_baseline_cmd + e_rx_lora_cmd + e_process_cmd

    return {
        "S1":   {"baseline": e_baseline_s1, "tx": e_tx_s1, "total": e_total_s1},
        "R1":   {"baseline": e_baseline_r1, "rx_wifi": e_rx_wifi_r1,
                 "process": e_process_r1, "tx_lora": e_tx_lora_r1,
                 "total":   e_total_r1},
        "CMD1": {"baseline": e_baseline_cmd, "rx_lora": e_rx_lora_cmd,
                 "process": e_process_cmd, "total": e_total_cmd},
    }


def main() -> None:
    cfg = SimulationConfig()
    net = build_test_network()
    tl  = build_test_events()
    duration_h = 1.0

    print("="*68)
    print(" Battery simulator — minimal test")
    print("="*68)
    print(f"  topology:   S1 (sensor) -> R1 (relay) -> CMD1 (gateway)")
    print(f"  events:     {len(tl.events)} detections on S1")
    print(f"  duration:   {duration_h:.1f} h")
    print(f"  battery:    {cfg.shaman_i.battery_wh} Wh per node")
    print()

    print("Inputs (Watts / seconds)")
    print(f"  Shaman I :  P_proc_active={cfg.shaman_i.P_proc_shaI_active:.4f}  "
          f"P_mic={cfg.shaman_i.P_mic:.5f}  P_wifi_tx={cfg.shaman_i.P_wifi_tx:.3f}  "
          f"t_tx_wifi={cfg.shaman_i.t_tx_wifi}")
    print(f"  Shaman II:  P_controller_sleep={cfg.shaman_ii.P_controller_sleep:.5f}  "
          f"P_proc_sleep={cfg.shaman_ii.P_proc_shaII_sleep:.3f}  "
          f"P_proc_active={cfg.shaman_ii.P_proc_shaII_active:.3f}")
    print(f"              P_lora_rx={cfg.shaman_ii.P_lora_rx:.4f}  "
          f"P_lora_tx={cfg.shaman_ii.P_lora_tx:.4f}  "
          f"P_wifi_rx={cfg.shaman_ii.P_wifi_rx:.4f}  "
          f"t_proc={cfg.shaman_ii.t_proc_shaII}  t_rx_wifi={cfg.shaman_ii.t_rx_wifi}")
    print(f"  Radio:      SF={cfg.radio.spreading_factor}  "
          f"BW={cfg.radio.bandwidth_hz} Hz  PL={cfg.radio.packet_bytes} B  "
          f"frames_per_hop={cfg.radio.frames_per_hop}  "
          f"t_lora={cfg.radio.airtime_per_frame_s()*1000:.2f} ms/frame")
    print()

    expected = predicted_energy(cfg, duration_h, n_events=len(tl.events))
    result   = BatterySimulator(cfg, net, tl, duration_hours=duration_h).run()

    print("Per-node math vs simulator")
    print(f"{'node':<6} {'term':<14} {'expected (Wh)':>15} {'simulator (Wh)':>17}")
    print("-"*56)
    for nid in ("S1", "R1", "CMD1"):
        exp     = expected[nid]
        sim_wh  = result["nodes"][nid]["summary"]["energy_consumed_wh"]
        for term, value in exp.items():
            sim_value = sim_wh if term == "total" else ""
            print(f"{nid:<6} {term:<14} {value:>15.6f}   "
                  f"{sim_value if sim_value=='' else f'{sim_value:>14.6f}'}")
        print()

    print("Final battery percentage")
    for nid, nd in result["nodes"].items():
        s = nd["summary"]
        print(f"  {nid:<5} {nd['role']:<8} "
              f"final={s['final_battery_percent']:>6.2f}%  "
              f"drawn={s['energy_consumed_wh']:>7.4f} Wh  "
              f"P_avg={s['average_power_w']:.4f} W  "
              f"life={s['projected_life_hours']} h")
    print()
    print(f"Worst node: {result['summary']['worst_node_id']} "
          f"({result['summary']['worst_battery_percent']}%)")


if __name__ == "__main__":
    main()
