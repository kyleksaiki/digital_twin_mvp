"""
Battery simulation engine — aligned to the Energy State / Variables /
Equations spec.

Physical model
==============
Shaman I (sensor)
    - Mic always listening (P_mic) + processor always running AI filter
      (P_proc_shaI_active). These form the continuous baseline.
    - Every detected event transmits one packet via WiFi to its parent
      Shaman II (E_tx = n_local * P_wifi_tx * t_tx_wifi * frames_per_hop).

Shaman II (relay / gateway)
    - Continuous baseline: controller-sleep + LoRa-listening + main-proc-sleep
      (P_controller_sleep + P_lora_rx + P_proc_shaII_sleep).
    - For each packet received from a Shaman I child → RX burst (WiFi).
    - For each packet received from a Shaman II child → RX burst (LoRa).
    - For each received packet → main-processor burst (P_process - P_sleep).
    - Forwards every packet (own + received) upward via LoRa unless it is
      the gateway/command (terminal).
    - CSMA retries add extra TX + backoff energy.

Spec equations implemented (§3 of the brief)
============================================
E_ShaI      = E_baseline + E_tx
E_baseline  = (P_proc_shaI_active + P_mic) * T
E_tx        = n_local * P_wifi_tx * t_tx_wifi * frames_per_hop

E_ShaII     = E_baseline + E_rx_wifi + E_rx_lora + E_tx + E_process + E_retry
E_baseline  = (P_controller_sleep + P_lora_rx + P_proc_shaII_sleep) * T
E_rx_wifi   = n_received_wifi * P_wifi_rx * t_rx_wifi
E_rx_lora   = n_received_lora * P_lora_rx * t_rx_lora
E_tx        = n_forward * P_lora_tx * t_tx_lora * frames_per_hop
E_process   = n_received * (P_proc_shaII_active - P_proc_shaII_sleep) * t_proc_shaII
E_retry     = n_retries * (P_lora_tx * t_tx_lora * frames_per_hop
                         +  P_backoff * t_backoff)

All energies accumulate into `node.energy_consumed_wh` and all times are
converted from seconds to hours by dividing by 3600 so the output is in Wh.
"""
from __future__ import annotations
from typing import Any, Dict
from datetime import datetime

from .config import SimulationConfig, ShamanIConfig, ShamanIIConfig
from .network import NodeRole, SimNetwork, SimNode
from .events import EventTimeline, SimEvent


SECONDS_PER_HOUR = 3600.0


class BatterySimulator:
    """Run the spec-aligned battery simulation and produce a time-series result."""

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
    # Node type + capacity helpers
    # ------------------------------------------------------------------

    def _capacity_wh(self, node: SimNode) -> float:
        if node.role == NodeRole.SENSOR:
            return self.config.shaman_i.battery_wh
        return self.config.shaman_ii.battery_wh

    def _baseline_power_w(self, node: SimNode) -> float:
        """Continuous draw (W) per spec §3.1 / §3.2."""
        if node.role == NodeRole.SENSOR:
            s1 = self.config.shaman_i
            # E_baseline = (P_proc_shaI_active + P_mic) * T
            return s1.P_proc_shaI_active + s1.P_mic

        s2 = self.config.shaman_ii
        # E_baseline = (P_controller_sleep + P_lora_rx + P_proc_shaII_sleep) * T
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
            node.n_retries = 0
            node.record_state(0.0, self._capacity_wh(node))

        events = sorted(self.timeline.events, key=lambda e: e.timestamp_s)
        event_idx = 0
        time_step = self.config.time_step_seconds
        current_time = 0.0

        while current_time < self.duration_seconds:
            next_time = min(current_time + time_step, self.duration_seconds)
            dt = next_time - current_time

            # 1. Continuous baseline
            self._apply_baseline(dt)

            # 2. Events that fire within [current_time, next_time)
            while event_idx < len(events) and events[event_idx].timestamp_s < next_time:
                self._process_event(events[event_idx])
                event_idx += 1

            # 3. Record per-node battery state
            for node in self.network.nodes.values():
                node.record_state(next_time, self._capacity_wh(node))

            current_time = next_time

        # Straggler events after the window (defensive, shouldn't normally hit)
        while event_idx < len(events):
            self._process_event(events[event_idx])
            event_idx += 1

        return self._build_output()

    # ------------------------------------------------------------------
    # Baseline + event application
    # ------------------------------------------------------------------

    def _apply_baseline(self, dt_seconds: float):
        dt_hours = dt_seconds / SECONDS_PER_HOUR
        for node in self.network.nodes.values():
            node.energy_consumed_wh += self._baseline_power_w(node) * dt_hours

    def _process_event(self, event: SimEvent):
        """A single AI-detected event originating on a sensor."""
        source = self.network.get_node(event.node_id)
        if source is None or source.role != NodeRole.SENSOR:
            return

        # n_local += 1 on the detecting sensor.
        source.n_local += 1

        # Sensor-side TX energy (one hop, WiFi) per spec §3.1.
        self._sensor_tx(source)

        # Walk up the tree: each hop = RX on the parent + TX from the parent
        # (unless the parent is the gateway, which only RX's).
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
    # Per-hop energy helpers (spec §3.1, §3.2, §3.3)
    # ------------------------------------------------------------------

    def _sensor_tx(self, sensor: SimNode):
        """Shaman I → Shaman II via WiFi (E_tx from §3.1)."""
        s1 = self.config.shaman_i
        frames = self._frames
        on_time_s = s1.t_tx_wifi * frames
        energy_wh = s1.P_wifi_tx * (on_time_s / SECONDS_PER_HOUR)
        sensor.energy_consumed_wh += energy_wh

        # CSMA retries on the WiFi hop are not modelled for Shaman I in the
        # spec (retries live on Shaman II's LoRa TX). Left intentionally.

    def _relay_receive(self, relay: SimNode, child: SimNode):
        """Shaman II RX burst, either WiFi (from Shaman I) or LoRa (from Shaman II)."""
        s2 = self.config.shaman_ii
        if child.role == NodeRole.SENSOR:
            # E_rx_wifi term
            relay.n_received_wifi += 1
            energy_wh = s2.P_wifi_rx * (s2.t_rx_wifi / SECONDS_PER_HOUR)
        else:
            # E_rx_lora term — one frame of LoRa airtime per received packet
            relay.n_received_lora += 1
            energy_wh = s2.P_lora_rx * (self._t_lora / SECONDS_PER_HOUR)
        relay.energy_consumed_wh += energy_wh

    def _relay_process(self, relay: SimNode):
        """Main-processor burst per received packet (E_process from §3.2)."""
        s2 = self.config.shaman_ii
        delta_w = max(0.0, s2.P_proc_shaII_active - s2.P_proc_shaII_sleep)
        energy_wh = delta_w * (s2.t_proc_shaII / SECONDS_PER_HOUR)
        relay.energy_consumed_wh += energy_wh

    def _relay_transmit(self, relay: SimNode):
        """LoRa TX for one forwarded packet (E_tx + E_retry from §3.2)."""
        s2 = self.config.shaman_ii
        r  = self.config.radio
        frames = self._frames
        on_time_s = self._t_lora * frames

        # Primary TX
        energy_wh = s2.P_lora_tx * (on_time_s / SECONDS_PER_HOUR)

        # CSMA retries (average): each retry = one more TX + backoff wait.
        avg_retries = max(0.0, float(r.avg_retries_per_tx))
        if avg_retries > 0:
            retry_tx_wh      = s2.P_lora_tx * (on_time_s / SECONDS_PER_HOUR)
            retry_backoff_wh = s2.P_backoff * (s2.t_backoff / SECONDS_PER_HOUR)
            energy_wh += avg_retries * (retry_tx_wh + retry_backoff_wh)
            # Round to nearest integer for the counter (for reporting only).
            relay.n_retries += int(round(avg_retries))

        relay.energy_consumed_wh += energy_wh

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

            # Projected battery life: T_life = E_battery / P_average
            # Derive P_average from the finished run's (E_consumed / elapsed).
            p_avg_w = (node.energy_consumed_wh / self.duration_hours
                       if self.duration_hours > 0 else 0.0)
            t_life_hours = (cap / p_avg_w) if p_avg_w > 0 else float("inf")

            nodes_out[node_id] = {
                "node_id": node_id,
                "role":    node.role.value,
                "capacity_wh": round(cap, 4),
                "time_series": node.battery_history,
                "summary": {
                    "final_battery_percent":     round(percent, 2),
                    "energy_consumed_wh":        round(node.energy_consumed_wh, 4),
                    "average_power_w":           round(p_avg_w, 4),
                    "projected_life_hours":      (round(t_life_hours, 2)
                                                   if t_life_hours != float("inf") else None),
                    # Spec counters (§2.5)
                    "n_local":                   node.n_local,
                    "n_received_wifi":           node.n_received_wifi,
                    "n_received_lora":           node.n_received_lora,
                    "n_received":                node.n_received,
                    "n_forward":                 node.n_forward if node.role == NodeRole.RELAY else 0,
                    "n_retries":                 node.n_retries,
                    # Legacy aliases (kept so existing consumers don't break)
                    "events_detected":           node.events_detected,
                    "events_received":           node.events_received,
                    "events_forwarded":          node.events_forwarded,
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
                "packet_bytes":         self.config.radio.packet_bytes,
                "spreading_factor":     self.config.radio.spreading_factor,
                "bandwidth_hz":         self.config.radio.bandwidth_hz,
                "airtime_per_frame_ms": round(self._t_lora * 1000, 2),
                "frames_per_hop":       self._frames,
                "avg_retries_per_tx":   self.config.radio.avg_retries_per_tx,
            },
            "nodes":  nodes_out,
            "summary": {
                "worst_node_id":         worst_node_id,
                "worst_battery_percent": round(worst_percent, 2),
                "total_nodes":           len(self.network.nodes),
            },
        }
