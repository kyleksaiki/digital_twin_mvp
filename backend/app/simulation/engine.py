"""
Battery Simulation Engine — two-tier event model.

Physical model
==============
Shaman I (sensor): ESP32-class MCU + microphone. Always-on acoustic prefilter
  (Stage 1) triggers per-clip confirmation inference (Stage 2). ONLY confirmed
  events trigger a LoRa transmission up the mesh.
Shaman II (relay): LoRa router. Receives confirmed packets from its
  children, forwards them up the tree.
Command (gateway): Terminal node. Receives and acts on packets; does not
  forward further.

Per-event energy additions
==========================
For each event `e` on sensor node `s`:
  1. Stage-2 inference burst on `s`:
        ΔE = (P_working - P_sleep) * stage2_duration_s
     Stage 1 is lumped into the baseline `sleep + micListen` continuous
     draw, so no extra term is added unless `stage1_duration_s > 0`.
  2. If `e.confirmed`:
        TX burst on `s`:      ΔE = P_transmit_sensor * airtime * frames_per_hop
        For each ancestor `a` up to the gateway:
           RX burst on `a`:   ΔE = P_receive_a     * airtime * frames_per_hop
           If a has a parent:
               TX burst on `a`: ΔE = P_transmit_a * airtime * frames_per_hop

Baseline draw (applied continuously every time step)
====================================================
  Sensor:  P_sleep + P_micListen
  Relay:   P_sleep
  Gateway: P_sleep (treated as always-powered by convention; adjust in config
           if your gateway is mains-powered and you want it excluded.)

Energy bookkeeping
==================
All energies accumulate into `node.energy_consumed_wh`. Battery percent is
tracked against per-node capacity (sensors → `shaman_i.battery_wh`;
relays/gateway → `shaman_ii.battery_wh`).
"""
from __future__ import annotations
from typing import Any, Dict, List
from datetime import datetime

from .config import SimulationConfig, NodeTypeConfig
from .network import NodeRole, SimNetwork, SimNode
from .events import EventTimeline, SimEvent


SECONDS_PER_HOUR = 3600.0


class BatterySimulator:
    """Run the battery simulation and produce a time-series result."""

    def __init__(self, config: SimulationConfig, network: SimNetwork,
                 timeline: EventTimeline, duration_hours: float = 3.0):
        self.config = config
        self.network = network
        self.timeline = timeline
        self.duration_hours = duration_hours
        self.duration_seconds = duration_hours * SECONDS_PER_HOUR

        # Pre-compute LoRa airtime per frame (constant across the run).
        self._airtime_s = self.config.radio.airtime_per_frame_s()
        self._frames = self.config.radio.frames_per_hop

    # ------------------------------------------------------------------
    # Helpers: per-node type resolution
    # ------------------------------------------------------------------

    def _type_config(self, node: SimNode) -> NodeTypeConfig:
        """Sensors use Shaman I config; relays and command use Shaman II."""
        if node.role == NodeRole.SENSOR:
            return self.config.shaman_i
        return self.config.shaman_ii

    def _capacity_wh(self, node: SimNode) -> float:
        return self._type_config(node).battery_wh

    def _baseline_power_w(self, node: SimNode) -> float:
        """Continuous draw (W) while the node is idle."""
        cfg = self._type_config(node)
        if node.role == NodeRole.SENSOR:
            # Sensor = sleep + always-listening mic. DSP prefilter is folded in.
            return cfg.watts("sleep") + cfg.watts("micListen")
        # Relay / gateway: just sleep. (RX happens on-demand per confirmed event.)
        return cfg.watts("sleep")

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        # Reset all nodes.
        for node in self.network.nodes.values():
            node.energy_consumed_wh = 0.0
            node.battery_history = []
            node.events_detected = 0
            node.events_received = 0
            node.events_forwarded = 0
            node.record_state(0.0, self._capacity_wh(node))

        events = sorted(self.timeline.events, key=lambda e: e.timestamp_s)
        event_idx = 0
        time_step = self.config.time_step_seconds
        current_time = 0.0

        while current_time < self.duration_seconds:
            next_time = min(current_time + time_step, self.duration_seconds)

            # 1. Apply continuous baseline for [current_time, next_time).
            dt = next_time - current_time
            self._apply_baseline(dt)

            # 2. Process events with timestamps in this window.
            while event_idx < len(events) and events[event_idx].timestamp_s < next_time:
                self._process_event(events[event_idx])
                event_idx += 1

            # 3. Record per-node battery state at end of window.
            for node in self.network.nodes.values():
                node.record_state(next_time, self._capacity_wh(node))

            current_time = next_time

        # Process any straggler events past the window (shouldn't happen, but defend).
        while event_idx < len(events):
            self._process_event(events[event_idx])
            event_idx += 1

        return self._build_output()

    # ------------------------------------------------------------------
    # Baseline & event application
    # ------------------------------------------------------------------

    def _apply_baseline(self, dt_seconds: float):
        dt_hours = dt_seconds / SECONDS_PER_HOUR
        for node in self.network.nodes.values():
            node.energy_consumed_wh += self._baseline_power_w(node) * dt_hours

    def _process_event(self, event: SimEvent):
        source = self.network.get_node(event.node_id)
        if source is None:
            return
        if source.role != NodeRole.SENSOR:
            # Only sensors originate AI events. Silently ignore mis-routed events.
            return

        source.events_detected += 1
        cfg = self._type_config(source)

        # --- Stage-1 prefilter burst (usually 0, rolled into baseline).
        if event.stage1_duration_s > 0:
            delta_w = max(0.0, cfg.watts("working") - cfg.watts("sleep"))
            source.energy_consumed_wh += delta_w * (event.stage1_duration_s / SECONDS_PER_HOUR)

        # --- Stage-2 inference burst on the sensor.
        if event.stage2_duration_s > 0:
            delta_w = max(0.0, cfg.watts("working") - cfg.watts("sleep"))
            source.energy_consumed_wh += delta_w * (event.stage2_duration_s / SECONDS_PER_HOUR)

        # --- Only confirmed events are transmitted.
        if event.confirmed:
            self._transmit_and_propagate(source)

    def _transmit_and_propagate(self, source: SimNode):
        """Sensor TX + every ancestor RX (and TX until the gateway)."""
        # Sensor TX
        tx_energy = self._tx_energy(source)
        source.energy_consumed_wh += tx_energy

        # Walk up the tree
        current = self.network.get_node(source.parent_id) if source.parent_id else None
        while current is not None:
            current.events_received += 1
            current.energy_consumed_wh += self._rx_energy(current)

            if current.role != NodeRole.COMMAND and current.parent_id:
                current.events_forwarded += 1
                current.energy_consumed_wh += self._tx_energy(current)

            current = self.network.get_node(current.parent_id) if current.parent_id else None

    # ------------------------------------------------------------------
    # Per-frame radio energy
    # ------------------------------------------------------------------

    def _tx_energy(self, node: SimNode) -> float:
        """Energy (Wh) to transmit one confirmed event from this node."""
        p_tx = self._type_config(node).watts("transmit")
        on_time_s = self._airtime_s * self._frames
        return p_tx * (on_time_s / SECONDS_PER_HOUR)

    def _rx_energy(self, node: SimNode) -> float:
        """Energy (Wh) to receive one confirmed event at this node."""
        p_rx = self._type_config(node).watts("receive")
        on_time_s = self._airtime_s * self._frames
        return p_rx * (on_time_s / SECONDS_PER_HOUR)

    # ------------------------------------------------------------------
    # Output assembly
    # ------------------------------------------------------------------

    def _build_output(self) -> Dict[str, Any]:
        nodes_out: Dict[str, Any] = {}
        worst_percent = 101.0
        worst_node_id = ""

        for node_id, node in self.network.nodes.items():
            cap = self._capacity_wh(node)
            remaining = max(0.0, cap - node.energy_consumed_wh)
            percent = (remaining / cap * 100.0) if cap > 0 else 0.0

            nodes_out[node_id] = {
                "node_id": node_id,
                "role": node.role.value,
                "capacity_wh": round(cap, 4),
                "time_series": node.battery_history,
                "summary": {
                    "final_battery_percent": round(percent, 2),
                    "energy_consumed_wh":    round(node.energy_consumed_wh, 4),
                    "events_detected":       node.events_detected,
                    "events_received":       node.events_received,
                    "events_forwarded":      node.events_forwarded,
                },
            }
            if percent < worst_percent:
                worst_percent = percent
                worst_node_id = node_id

        return {
            "simulation_id":  f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "duration_hours": self.duration_hours,
            "total_events":   len(self.timeline.events),
            "confirmed_events":  self.timeline.confirmed_count(),
            "candidate_events":  self.timeline.candidate_count(),
            "radio": {
                "packet_bytes":     self.config.radio.packet_bytes,
                "spreading_factor": self.config.radio.spreading_factor,
                "bandwidth_hz":     self.config.radio.bandwidth_hz,
                "airtime_per_frame_ms": round(self._airtime_s * 1000, 2),
                "frames_per_hop":   self._frames,
            },
            "nodes": nodes_out,
            "summary": {
                "worst_node_id":         worst_node_id,
                "worst_battery_percent": round(worst_percent, 2),
                "total_nodes":           len(self.network.nodes),
            },
        }
