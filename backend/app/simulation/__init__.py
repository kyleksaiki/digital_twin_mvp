"""
Battery simulation package.

What lives here:
  config.py           — reads Configure Run GUI inputs (battery Wh, component
                        current/voltage, processor, radio params).
  network.py          — loads the node topology (sensors / relays / command)
                        from DB rows and wires up parent/child links.
  events.py           — `SimEvent` + `EventTimeline`; represents AI detections
                        the simulator consumes. Knows how to build itself from
                        mock data, from the DB, or from a loaded JSON.
  ai_event_loader.py  — reads the AI pipeline's event-timeline JSON and maps
                        each entry to a node_id.
  engine.py           — the simulator itself. Steps through time, drains each
                        node's battery using the config + events, and emits
                        per-node time-series data.

Top-level exports used by `routes/battery.py` and `scripts/run_battery_sim.py`.
"""
from .engine import BatterySimulator
from .config import SimulationConfig

__all__ = ["BatterySimulator", "SimulationConfig"]
