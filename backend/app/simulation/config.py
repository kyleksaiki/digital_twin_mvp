"""
Battery simulation configuration.

What this file defines:
  - `ComponentPower`: one component's power draw (current + voltage, or watts).
  - `NodeTypeConfig`: battery capacity + processor + all component states for
                      a single node type (Shaman I sensor or Shaman II relay).
  - `RadioConfig`:    LoRa radio parameters used for transmit-airtime math.
  - `EventTimings`:   how long each event-driven state lasts (inference burst,
                      relay routing, etc.).
  - `SimulationConfig`: the full bundle the engine consumes.

The GUI's Configure Run modal sends one payload per node type. This file reads
those payloads as-is, so whatever the user enters flows straight through.

Expected GUI payload shape (one per node type):

    {
      "batteryLife": 30.0,                  # Wh
      "processor":   "ESP32",
      "components": {
        "sleep":       {"current": 0.8,  "voltage": 3.3, "power": null},
        "working":     {"current": 160,  "voltage": 3.3, "power": null},
        "transmit":    {"current": 220,  "voltage": 3.3, "power": null},
        "receive":     {"current": 100,  "voltage": 3.3, "power": null},
        "cameraImage": {"current": null, "voltage": null, "power": null},
        "cameraSleep": {"current": null, "voltage": null, "power": null},
        "micListen":   {"current": 0.6,  "voltage": 3.3, "power": null},
        "micSleep":    {"current": 0.1,  "voltage": 3.3, "power": null}
      }
    }

Each component accepts EITHER (current mA + voltage V) OR an explicit power W.
Explicit power wins; otherwise watts = current_mA * voltage_V / 1000.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Any


# ---------------------------------------------------------------------------
# Component power (current/voltage/power) — mirrors CreateRun.jsx "CVP"
# ---------------------------------------------------------------------------

@dataclass
class ComponentPower:
    """A single component state's power draw.

    Accept current+voltage OR power. `watts` returns the resolved value.
    """
    current_ma: Optional[float] = None
    voltage_v:  Optional[float] = None
    power_w:    Optional[float] = None

    @property
    def watts(self) -> float:
        """Resolve to a single Watts value. Explicit power wins; else I*V."""
        if self.power_w is not None:
            return float(self.power_w)
        if self.current_ma is not None and self.voltage_v is not None:
            return (self.current_ma / 1000.0) * self.voltage_v
        return 0.0

    @classmethod
    def from_cvp_dict(cls, d: Optional[Dict[str, Any]]) -> "ComponentPower":
        """Parse GUI's {current, voltage, power} payload."""
        if not d:
            return cls()
        return cls(
            current_ma=d.get("current"),
            voltage_v=d.get("voltage"),
            power_w=d.get("power"),
        )


# ---------------------------------------------------------------------------
# Per-node-type config (Shaman I sensor, Shaman II relay)
# ---------------------------------------------------------------------------

# Component keys present in the GUI for each node type
SHAMAN_I_COMPONENTS  = ("sleep", "working", "transmit", "receive",
                        "cameraImage", "cameraSleep", "micListen", "micSleep")
SHAMAN_II_COMPONENTS = ("sleep", "working", "transmit", "receive")


@dataclass
class NodeTypeConfig:
    """Battery + component power config for a single node type.

    One instance for Shaman I, one for Shaman II. The Command/Gateway node
    is modeled with the Shaman II config (it's the same hardware class).
    """
    battery_wh: float = 22.0
    processor:  str   = "ESP32"
    components: Dict[str, ComponentPower] = field(default_factory=dict)

    # Sensible per-state fallbacks (W) if user leaves a field blank.
    # These are conservative best-guesses for ESP32-class hardware and are
    # used ONLY when the GUI sends nothing for that component.
    _DEFAULTS_SHAMAN_I  = {
        "sleep":       0.003,   # 0.8mA @ 3.3V, radio off
        "working":     0.528,   # 160mA @ 3.3V, MCU active
        "transmit":    0.726,   # 220mA @ 3.3V, WiFi/LoRa TX (overwritten if using LoRa)
        "receive":     0.330,   # 100mA @ 3.3V, RX
        "cameraImage": 0.000,   # off by default
        "cameraSleep": 0.000,
        "micListen":   0.002,   # 0.6mA @ 3.3V
        "micSleep":    0.0003,
    }
    _DEFAULTS_SHAMAN_II = {
        "sleep":    0.5,       # relay sleep ~500mW (bigger MCU)
        "working":  3.5,       # Radxa Zero active
        "transmit": 0.389,     # LoRa TX 118mA @ 3.3V
        "receive":  0.020,     # LoRa RX 6mA @ 3.3V
    }

    def watts(self, component: str) -> float:
        """Power draw for a named component, falling back to defaults."""
        c = self.components.get(component)
        if c is not None:
            w = c.watts
            if w > 0:
                return w
        # Fall through to defaults
        if component in self._DEFAULTS_SHAMAN_I and self._is_sensor_default():
            return self._DEFAULTS_SHAMAN_I[component]
        if component in self._DEFAULTS_SHAMAN_II:
            return self._DEFAULTS_SHAMAN_II[component]
        return 0.0

    def _is_sensor_default(self) -> bool:
        """Heuristic: Shaman I configs include camera/mic components."""
        return any(k in self.components for k in ("cameraImage", "micListen"))

    @classmethod
    def from_gui_payload(cls, payload: Optional[Dict[str, Any]],
                         is_sensor: bool) -> "NodeTypeConfig":
        """Build from the Configure Run modal payload.

        payload shape: {"batteryLife": float, "components": {name: {current,voltage,power}}}
        """
        if not payload:
            # Empty payload → pure defaults (useful for tests/mocks)
            keys = SHAMAN_I_COMPONENTS if is_sensor else SHAMAN_II_COMPONENTS
            return cls(
                battery_wh=22.0,
                components={k: ComponentPower() for k in keys},
            )

        battery_wh = float(payload.get("batteryLife") or 22.0)
        processor  = payload.get("processor") or ("ESP32" if is_sensor else "Radxa Zero")
        raw_comps  = payload.get("components") or {}
        components = {
            name: ComponentPower.from_cvp_dict(raw_comps.get(name))
            for name in (SHAMAN_I_COMPONENTS if is_sensor else SHAMAN_II_COMPONENTS)
        }
        return cls(battery_wh=battery_wh, processor=processor, components=components)


# ---------------------------------------------------------------------------
# Radio/airtime parameters (LoRa — configurable, sensible defaults per project docs)
# ---------------------------------------------------------------------------

@dataclass
class RadioConfig:
    """LoRa radio parameters used to compute packet airtime.

    Defaults match the team's Mesh Network Planning doc (§6.2 "semantic
    transmission") and the Example Output slide (SF10). Packet size default
    128 B is the "summary only" payload; if the hardware actually transmits
    4128 B (as shown on one slide), flip `packet_bytes` and re-run.
    """
    packet_bytes:   int   = 128         # summary-only semantic packet
    spreading_factor: int = 10          # SF10 per slide
    bandwidth_hz:   int   = 125_000     # 125 kHz (LoRaWAN default)
    coding_rate:    int   = 5           # 4/5 (standard)
    preamble_symbols: int = 8
    frames_per_hop: int   = 3           # per task spec

    def airtime_per_frame_s(self) -> float:
        """Semtech LoRa time-on-air formula (seconds) for one frame.

        Reference: Semtech AN1200.13 / SX1276 datasheet §4.1.1.6
        """
        sf   = self.spreading_factor
        bw   = self.bandwidth_hz
        cr   = self.coding_rate            # 4/5..4/8 → integer 5..8
        pl   = self.packet_bytes
        n_preamble = self.preamble_symbols

        t_sym = (2 ** sf) / bw             # symbol time (s)
        t_preamble = (n_preamble + 4.25) * t_sym

        # Payload symbol count (explicit header, no low-data-rate optimization,
        # CRC on — typical LoRaWAN uplink).
        # Formula: n_payload = 8 + max(ceil((8*PL - 4*SF + 28 + 16) / (4*SF)) * (CR), 0)
        import math
        numerator = 8 * pl - 4 * sf + 28 + 16
        denom     = 4 * sf
        n_payload = 8 + max(math.ceil(numerator / denom) * cr, 0)
        t_payload = n_payload * t_sym

        return t_preamble + t_payload


# ---------------------------------------------------------------------------
# Event-processing timings (durations per event, not in GUI — proposed additions)
# ---------------------------------------------------------------------------

@dataclass
class EventTimings:
    """How long each state lasts per event.

    These values are NOT in the Configure Run GUI today. We suggest adding
    them as a follow-up (see BATTERY_MATH.md §5). Meanwhile the defaults are
    grounded in the AI pipeline's `inference_ms` field.
    """
    # Stage 1 (acoustic prefilter) is continuous at low power — rolled into
    # the sensor's baseline `micListen`+`sleep` draw. Set >0 if you want an
    # extra burst per candidate.
    stage1_extra_working_s: float = 0.0

    # Stage 2 (confirmation model) burst per candidate. When an AI event
    # carries `inference_ms` we use that; this is the fallback.
    stage2_default_working_s: float = 0.03   # 30ms — typical BirdNET-style inference

    # Relay per-hop processing (routing decision). Small.
    relay_routing_working_s: float = 0.005


# ---------------------------------------------------------------------------
# Top-level simulation config
# ---------------------------------------------------------------------------

@dataclass
class SimulationConfig:
    """Complete config bundle consumed by `BatterySimulator`."""
    shaman_i:  NodeTypeConfig = field(default_factory=lambda: NodeTypeConfig.from_gui_payload(None, is_sensor=True))
    shaman_ii: NodeTypeConfig = field(default_factory=lambda: NodeTypeConfig.from_gui_payload(None, is_sensor=False))
    radio:     RadioConfig    = field(default_factory=RadioConfig)
    timings:   EventTimings   = field(default_factory=EventTimings)
    time_step_seconds: float  = 60.0   # time-series sampling resolution

    @classmethod
    def from_run_config(cls,
                        shaman_i_config:  Optional[Dict[str, Any]] = None,
                        shaman_ii_config: Optional[Dict[str, Any]] = None,
                        radio_config:     Optional[Dict[str, Any]] = None,
                        ) -> "SimulationConfig":
        """Build a SimulationConfig from the Configure Run modal payloads."""
        cfg = cls(
            shaman_i  = NodeTypeConfig.from_gui_payload(shaman_i_config,  is_sensor=True),
            shaman_ii = NodeTypeConfig.from_gui_payload(shaman_ii_config, is_sensor=False),
        )
        if radio_config:
            for k, v in radio_config.items():
                if hasattr(cfg.radio, k) and v is not None:
                    setattr(cfg.radio, k, v)
        return cfg
