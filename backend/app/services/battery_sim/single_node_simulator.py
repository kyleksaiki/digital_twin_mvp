"""Single-node Shaman battery simulator.

VENDORED from the battery-simulator repo (single_node_simulator.py).
To re-sync with upstream: copy the upstream file over this one, then re-apply
the two local modifications (both marked with "LOCAL MODIFICATION" comments):
  1. _step_energy() accepts unconfirmed_in_step — unconfirmed events cost
     t_proc only (no transmit). Defaults keep upstream behavior identical.
  2. run() counts unconfirmed events per step and passes them through.

Models one Shaman device with:
  - microphone (always on)
  - low-power processor (always on, idle monitoring)
  - high-power processor (wakes on detection)
  - transmitter (fires once per detection, after processing)

No mesh networking, no relay hops, no topology.

Public API: run_from_dict(payload) -> dict
Energy unit: Wh = P[W] * t[s] / 3600
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SECONDS_PER_HOUR = 3600.0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class NodeConfig:
    battery_wh: float = 22.0

    # Idle components (always on)
    P_mic: float = 0.00198          # microphone listening power (W)
    P_proc_lp: float = 0.00264      # low-power processor sleep power (W)

    # Per-detection burst components
    P_proc_hp: float = 0.528        # high-power processor active power (W)
    t_proc: float = 0.030           # high-power processing duration per detection (s)

    P_tx: float = 0.726             # transmitter power (W)
    t_tx: float = 0.005             # transmitter on-time per detection (s)

    @classmethod
    def from_payload(cls, payload: Optional[Dict[str, Any]]) -> "NodeConfig":
        inst = cls()
        if not payload:
            return inst
        for key in (
            "battery_wh", "P_mic", "P_proc_lp", "P_proc_hp",
            "t_proc", "P_tx", "t_tx",
        ):
            if payload.get(key) is not None:
                setattr(inst, key, float(payload[key]))
        # Accept battery_wh aliases from the old schema
        if payload.get("batteryLife") is not None:
            inst.battery_wh = float(payload["batteryLife"])
        return inst


@dataclass
class SimulationConfig:
    node: NodeConfig = field(default_factory=NodeConfig)
    duration_hours: float = 72.0
    time_step_seconds: float = 3600.0


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@dataclass
class DetectionEvent:
    timestamp_s: float
    event_type: str = "detection"
    confirmed: bool = True


_TIMESTAMP_RE = re.compile(
    r"(?:Human presence detected.*?)"       # optional label prefix
    r"(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?",  # HH:MM:SS[.ms]
    re.IGNORECASE,
)


def parse_timestamp_text(text: str) -> List[DetectionEvent]:
    """Parse human-presence lines like 'Human presence detected at time 00:09:03.100'."""
    events: List[DetectionEvent] = []
    for line in text.splitlines():
        m = _TIMESTAMP_RE.search(line)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            frac = float("0." + m.group(4)) if m.group(4) else 0.0
            ts = h * 3600 + mi * 60 + s + frac
            events.append(DetectionEvent(timestamp_s=ts))
    return events


def events_from_payload(payload_events: List[Dict[str, Any]]) -> List[DetectionEvent]:
    """Parse events from the JSON list format [{time, confirmed?, event_type?}, ...]."""
    out: List[DetectionEvent] = []
    for e in payload_events:
        ts = float(e.get("time") or e.get("timestamp_s") or 0.0)
        out.append(DetectionEvent(
            timestamp_s=ts,
            event_type=e.get("event_type", "detection"),
            confirmed=bool(e.get("confirmed", True)),
        ))
    return sorted(out, key=lambda e: e.timestamp_s)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class SingleNodeSimulator:
    def __init__(
        self,
        config: SimulationConfig,
        events: List[DetectionEvent],
    ):
        self.cfg = config
        self.events = sorted(events, key=lambda e: e.timestamp_s)
        self.duration_s = config.duration_hours * SECONDS_PER_HOUR

    # ---- energy helpers ----

    @staticmethod
    def _wh(p_watts: float, seconds: float) -> float:
        return p_watts * (seconds / SECONDS_PER_HOUR)

    # ---- main run ----

    def _step_energy(self, node: NodeConfig, dt: float, events_in_step: int, unconfirmed_in_step: int = 0):
        """Compute per-component energy for one timestep using the state machine.

        Each detection drives: idle → processing (t_proc) → transmission (t_tx) → idle.
        During processing: HP proc replaces LP proc; mic stays on.
        During transmission: TX active; both processors off; mic stays on.
        Remaining time in the step is pure idle (mic + LP proc).

        LOCAL MODIFICATION: unconfirmed events (confirmed=False) wake the HP
        processor but never fire the radio — they cost t_proc only, while
        confirmed events cost t_proc + t_tx. Defaults to 0 unconfirmed so
        upstream callers and existing scenario JSON behave identically.

        Returns (e_mic, e_proc_lp, e_proc_hp, e_tx) in Wh.
        """
        confirmed_in_step = max(0, events_in_step - unconfirmed_in_step)
        burst_s = events_in_step * node.t_proc + confirmed_in_step * node.t_tx
        # Cap burst time to the step duration — if detections cluster, they can't
        # exceed the available wall-clock time in the step.
        burst_s = min(burst_s, dt)

        proc_s = min(events_in_step * node.t_proc, dt)
        tx_s   = min(burst_s - proc_s, 0.0 + confirmed_in_step * node.t_tx)
        # proc_s + tx_s <= burst_s <= dt
        idle_s = dt - proc_s - tx_s

        # Mic is on for the full step regardless of state
        e_mic     = self._wh(node.P_mic, dt)
        # LP proc is on only during idle time (displaced by HP during proc+tx)
        e_proc_lp = self._wh(node.P_proc_lp, idle_s)
        # HP proc fires during processing windows
        e_proc_hp = self._wh(node.P_proc_hp, proc_s)
        # Transmitter fires during tx windows
        e_tx      = self._wh(node.P_tx, tx_s)

        return e_mic, e_proc_lp, e_proc_hp, e_tx

    def run(self) -> Dict[str, Any]:
        cfg = self.cfg
        node = cfg.node

        # Accumulated energy by component (Wh)
        e_mic = 0.0
        e_proc_lp = 0.0
        e_proc_hp = 0.0
        e_tx = 0.0

        battery_over_time: List[Dict[str, Any]] = []

        event_idx = 0
        current_time = 0.0
        time_step = cfg.time_step_seconds
        battery_wh = node.battery_wh
        alive = True

        # Record initial state
        battery_over_time.append({
            "time_seconds": 0,
            "battery_percent": 100.0,
        })

        while current_time < self.duration_s:
            next_time = min(current_time + time_step, self.duration_s)
            dt = next_time - current_time

            if not alive:
                battery_over_time.append({
                    "time_seconds": round(next_time),
                    "battery_percent": 0.0,
                })
                current_time = next_time
                continue

            # Count detections that fall inside this timestep
            # LOCAL MODIFICATION: also count how many are unconfirmed.
            events_in_step = 0
            unconfirmed_in_step = 0
            while event_idx < len(self.events) and self.events[event_idx].timestamp_s < next_time:
                events_in_step += 1
                if not self.events[event_idx].confirmed:
                    unconfirmed_in_step += 1
                event_idx += 1

            # Run state machine for this step
            de_mic, de_lp, de_hp, de_tx = self._step_energy(node, dt, events_in_step, unconfirmed_in_step)

            # --- Accumulate ---
            e_mic     += de_mic
            e_proc_lp += de_lp
            e_proc_hp += de_hp
            e_tx      += de_tx

            total_consumed = e_mic + e_proc_lp + e_proc_hp + e_tx
            remaining = max(0.0, battery_wh - total_consumed)
            pct = round((remaining / battery_wh) * 100.0, 4) if battery_wh > 0 else 0.0

            if remaining <= 0 and alive:
                alive = False
                pct = 0.0

            battery_over_time.append({
                "time_seconds": round(next_time),
                "battery_percent": pct,
            })

            current_time = next_time

        total_consumed = e_mic + e_proc_lp + e_proc_hp + e_tx
        remaining = max(0.0, battery_wh - total_consumed)
        avg_power_w = total_consumed / cfg.duration_hours if cfg.duration_hours > 0 else 0.0
        projected_life_h = (battery_wh / avg_power_w) if avg_power_w > 0 else None

        return {
            "battery_over_time": battery_over_time,
            "component_energy_breakdown": {
                "microphone": round(e_mic, 6),
                "processor_lp": round(e_proc_lp, 6),
                "processor_hp": round(e_proc_hp, 6),
                "transmitter": round(e_tx, 6),
            },
            "summary": {
                "battery_wh": battery_wh,
                "energy_consumed_wh": round(total_consumed, 6),
                "energy_remaining_wh": round(remaining, 6),
                "final_battery_percent": round((remaining / battery_wh * 100.0), 2) if battery_wh > 0 else 0.0,
                "average_power_w": round(avg_power_w, 6),
                "projected_total_life_hours": round(projected_life_h, 2) if projected_life_h else None,
                "total_detections": len(self.events),
                "alive": alive,
            },
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_from_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run the single-node simulator from a plain JSON-compatible dict.

    Accepted payload keys:
        node            — NodeConfig fields (battery_wh, P_mic, P_proc_lp, P_proc_hp,
                          t_proc, P_tx, t_tx, batteryLife)
        duration_hours  — simulation horizon (default 72)
        time_step_seconds — SOC sample interval (default 3600)
        events          — list of {time, confirmed?, event_type?}
        timestamp_text  — raw human-presence text lines (alternative to events)
    """
    node_cfg = NodeConfig.from_payload(payload.get("node") or payload)

    duration_hours = float(
        payload.get("duration_hours")
        or payload.get("total_time_hours")
        or 72.0
    )
    time_step = float(payload.get("time_step_seconds") or payload.get("time_step") or 3600.0)

    cfg = SimulationConfig(
        node=node_cfg,
        duration_hours=duration_hours,
        time_step_seconds=time_step,
    )

    # Events can come as structured list or raw timestamp text
    if payload.get("timestamp_text"):
        events = parse_timestamp_text(payload["timestamp_text"])
    else:
        events = events_from_payload(payload.get("events") or [])

    sim = SingleNodeSimulator(cfg, events)
    return sim.run()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_DEFAULT_SCENARIO = Path(__file__).parent / "single_node_scenario.json"


def main() -> None:
    ap = argparse.ArgumentParser(description="Single-node Shaman battery simulator")
    ap.add_argument("--scenario", type=Path, default=_DEFAULT_SCENARIO)
    ap.add_argument("--out", type=Path, default=None, help="Write JSON result to file")
    args = ap.parse_args()

    if not args.scenario.is_file():
        sys.exit(f"Scenario not found: {args.scenario}")

    payload = json.loads(args.scenario.read_text(encoding="utf-8"))
    result = run_from_dict(payload)

    if args.out:
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Result written to {args.out}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
