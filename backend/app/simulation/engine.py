"""
Battery simulation engine.

Implements the spec equations exactly. Per time-step:
  1. Every node accrues its constant baseline draw.
  2. Every AI event in this step is applied:
       sensor TX (WiFi) -> walk up the tree -> each relay does RX + process + TX.
  3. Each node snapshots its battery % into its time-series.

Spec equations (T = duration in hours):

    Shaman I:
        E_baseline = (P_proc_shaI_active + P_mic) * T
        E_tx       = n_local * P_wifi_tx * t_tx_wifi * frames_per_hop

    Shaman II:
        E_baseline = (P_controller_sleep + P_lora_rx + P_proc_shaII_sleep) * T
        E_rx_wifi  = n_received_wifi * P_wifi_rx * t_rx_wifi
        E_rx_lora  = n_received_lora * P_lora_rx * t_rx_lora
        E_tx       = n_forward      * P_lora_tx * t_tx_lora * frames_per_hop
        E_process  = n_received     * (P_proc_shaII_active - P_proc_shaII_sleep) * t_proc_shaII
"""
from __future__ import annotations
from typing import Any, Dict
from datetime import datetime

from .config import SimulationConfig
from .network import NodeRole, SimNetwork, SimNode
from .events import EventTimeline, SimEvent


SECONDS_PER_HOUR = 3600.0


class BatterySimulator:
    """Run the spec-aligned battery simulation."""

    def __init__(self, config: SimulationConfig, network: SimNetwork,
                 timeline: EventTimeline, duration_hours: float = 3.0):
        self.config = config
        self.network = network
        self.timeline = timeline
        self.duration_hours = duration_hours
        self.duration_seconds = duration_hours * SECONDS_PER_HOUR

        self._t_lora = self.config.radio.airtime_per_frame_s()   # seconds/frame
        self._frames = self.config.radio.frames_per_hop

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _capacity_wh(self, node: SimNode) -> float:
        if node.role == NodeRole.SENSOR:
            return self.config.shaman_i.battery_wh
        return self.config.shaman_ii.battery_wh

    def _baseline_power_w(self, node: SimNode) -> float:
        """Continuous draw in Watts."""
        if node.role == NodeRole.SENSOR:
            s1 = self.config.shaman_i
            return s1.P_proc_shaI_active + s1.P_mic
        s2 = self.config.shaman_ii
        return s2.P_controller_sleep + s2.P_lora_rx + s2.P_proc_shaII_sleep

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        for node in self.network.nodes.values():
            node.energy_consumed_wh = 0.0
            node.battery_history = []
            node.n_local = 0
            node.n_received_wifi = 0
            node.n_received_lora = 0
            node.record_state(0.0, self._capacity_wh(node))

        events = sorted(self.timeline.events, key=lambda e: e.timestamp_s)
        event_idx = 0
        time_step = self.config.time_step_seconds
        current_time = 0.0

        while current_time < self.duration_seconds:
            next_time = min(current_time + time_step, self.duration_seconds)
            dt = next_time - current_time

            self._apply_baseline(dt)

            while event_idx < len(events) and events[event_idx].timestamp_s < next_time:
                self._process_event(events[event_idx])
                event_idx += 1

            for node in self.network.nodes.values():
                node.record_state(next_time, self._capacity_wh(node))

            current_time = next_time

        return self._build_output()

    # ------------------------------------------------------------------
    # Step pieces
    # ------------------------------------------------------------------

    def _apply_baseline(self, dt_seconds: float):
        dt_hours = dt_seconds / SECONDS_PER_HOUR
        for node in self.network.nodes.values():
            node.energy_consumed_wh += self._baseline_power_w(node) * dt_hours

    def _process_event(self, event: SimEvent):
        """A single AI detection on a sensor: TX up the tree."""
        source = self.network.get_node(event.node_id)
        if source is None or source.role != NodeRole.SENSOR:
            return

        source.n_local += 1
        self._sensor_tx(source)

        child = source
        parent = self.network.get_node(source.parent_id) if source.parent_id else None
        while parent is not None:
            self._relay_receive(parent, child)
            self._relay_process(parent)
            if parent.role != NodeRole.COMMAND and parent.parent_id is not None:
                self._relay_transmit(parent)
            child = parent
            parent = self.network.get_node(parent.parent_id) if parent.parent_id else None

    # ------------------------------------------------------------------
    # Per-hop energy terms
    # ------------------------------------------------------------------

    def _sensor_tx(self, sensor: SimNode):
        """Shaman I -> Shaman II via WiFi."""
        s1 = self.config.shaman_i
        on_time_s = s1.t_tx_wifi * self._frames
        sensor.energy_consumed_wh += s1.P_wifi_tx * (on_time_s / SECONDS_PER_HOUR)

    def _relay_receive(self, relay: SimNode, child: SimNode):
        """Shaman II RX burst (WiFi if child is Shaman I, else LoRa)."""
        s2 = self.config.shaman_ii
        if child.role == NodeRole.SENSOR:
            relay.n_received_wifi += 1
            relay.energy_consumed_wh += s2.P_wifi_rx * (s2.t_rx_wifi / SECONDS_PER_HOUR)
        else:
            relay.n_received_lora += 1
            relay.energy_consumed_wh += s2.P_lora_rx * (self._t_lora / SECONDS_PER_HOUR)

    def _relay_process(self, relay: SimNode):
        """Main-processor burst per received packet."""
        s2 = self.config.shaman_ii
        delta_w = max(0.0, s2.P_proc_shaII_active - s2.P_proc_shaII_sleep)
        relay.energy_consumed_wh += delta_w * (s2.t_proc_shaII / SECONDS_PER_HOUR)

    def _relay_transmit(self, relay: SimNode):
        """LoRa TX of one forwarded packet."""
        s2 = self.config.shaman_ii
        on_time_s = self._t_lora * self._frames
        relay.energy_consumed_wh += s2.P_lora_tx * (on_time_s / SECONDS_PER_HOUR)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _build_output(self) -> Dict[str, Any]:
        nodes_out: Dict[str, Any] = {}
        worst_percent = 101.0
        worst_node_id = ""

        for node_id, node in self.network.nodes.items():
            cap = self._capacity_wh(node)
            remaining = max(0.0, cap - node.energy_consumed_wh)
            percent = (remaining / cap * 100.0) if cap > 0 else 0.0

            p_avg_w = (node.energy_consumed_wh / self.duration_hours
                       if self.duration_hours > 0 else 0.0)
            t_life_hours = (cap / p_avg_w) if p_avg_w > 0 else None

            nodes_out[node_id] = {
                "node_id": node_id,
                "role":    node.role.value,
                "capacity_wh": round(cap, 4),
                "time_series": node.battery_history,
                "summary": {
                    "final_battery_percent":  round(percent, 2),
                    "energy_consumed_wh":     round(node.energy_consumed_wh, 4),
                    "average_power_w":        round(p_avg_w, 4),
                    "projected_life_hours":   (round(t_life_hours, 2)
                                               if t_life_hours is not None else None),
                    "n_local":                node.n_local,
                    "n_received_wifi":        node.n_received_wifi,
                    "n_received_lora":        node.n_received_lora,
                    "n_received":             node.n_received,
                    "n_forward":              (node.n_forward
                                               if node.role == NodeRole.RELAY else 0),
                },
            }
            if percent < worst_percent:
                worst_percent = percent
                worst_node_id = node_id

        return {
            "simulation_id":  f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "duration_hours": self.duration_hours,
            "total_events":   len(self.timeline.events),
            "radio": {
                "spreading_factor":     self.config.radio.spreading_factor,
                "bandwidth_hz":         self.config.radio.bandwidth_hz,
                "packet_bytes":         self.config.radio.packet_bytes,
                "airtime_per_frame_ms": round(self._t_lora * 1000, 2),
                "frames_per_hop":       self._frames,
            },
            "nodes":  nodes_out,
            "summary": {
                "worst_node_id":         worst_node_id,
                "worst_battery_percent": round(worst_percent, 2),
                "total_nodes":           len(self.network.nodes),
            },
        }
