"""
Battery simulation configuration — aligned to the Energy State / Variables /
Equations spec.

What this file defines:
  - `ComponentPower`: one state's power draw (current + voltage, or watts).
  - `ShamanIConfig`:  Shaman I (sensor) variables per the spec:
                      P_mic, P_mic_off, P_proc_shaI_active, P_proc_shaI_sleep,
                      P_wifi_tx, t_proc_shaI, t_tx_wifi.
  - `ShamanIIConfig`: Shaman II (relay/gateway) variables per the spec:
                      two processors (main + ESP32 controller), LoRa + WiFi RX,
                      LoRa TX, CSMA backoff.
  - `RadioConfig`:    LoRa packet-level params (SF, BW, CR, packet_bytes,
                      frames_per_hop) + WiFi durations + CSMA retry model.
  - `SimulationConfig`: the full bundle the engine consumes.

GUI backward compatibility:
  Configure Run (`CreateRun.jsx`) uses the older `components.{sleep,working,
  transmit,receive,micListen,micSleep,...}` schema. We map those to the new
  spec variables automatically:

      Shaman I          GUI `components` key        Spec variable
      ---------         ------------------          ----------------------
      sensor MCU idle   `sleep`                     P_proc_shaI_sleep
      sensor MCU active `working`                   P_proc_shaI_active
      sensor WiFi TX    `transmit`                  P_wifi_tx
      mic listening     `micListen`                 P_mic
      mic off           `micSleep`                  P_mic_off

      Shaman II         GUI `components` key        Spec variable
      ---------         ------------------          ----------------------
      main proc idle    `sleep`                     P_proc_shaII_sleep
      main proc active  `working`                   P_proc_shaII_active
      LoRa TX           `transmit`                  P_lora_tx
      LoRa RX (listen)  `receive`                   P_lora_rx

  Spec variables that have NO GUI equivalent (controller sub-chip on Shaman II,
  WiFi RX on Shaman II, CSMA backoff) fall back to sensible defaults until the
  GUI exposes them. Documented in BATTERY_MATH.md §5.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
import math


# ---------------------------------------------------------------------------
# ComponentPower — helper that resolves (current_mA, voltage_V, power_W) → W
# ---------------------------------------------------------------------------

@dataclass
class ComponentPower:
    """A single state's power draw. Accept current+voltage OR power; watts resolves."""
    current_ma: Optional[float] = None
    voltage_v:  Optional[float] = None
    power_w:    Optional[float] = None

    @property
    def watts(self) -> float:
        if self.power_w is not None:
            return float(self.power_w)
        if self.current_ma is not None and self.voltage_v is not None:
            return (self.current_ma / 1000.0) * self.voltage_v
        return 0.0

    @classmethod
    def from_cvp_dict(cls, d: Optional[Dict[str, Any]]) -> "ComponentPower":
        """Parse GUI's `{current, voltage, power}` payload."""
        if not d:
            return cls()
        return cls(
            current_ma=d.get("current"),
            voltage_v=d.get("voltage"),
            power_w=d.get("power"),
        )


# ---------------------------------------------------------------------------
# Shaman I — sensor node (mic + ESP32 + WiFi-TX to parent Shaman II)
# ---------------------------------------------------------------------------

@dataclass
class ShamanIConfig:
    """Shaman I sensor-node power and timing variables.

    Defaults are ESP32-class values and typical MEMS-mic current; the user's
    Configure Run payload overrides whichever fields are provided.
    """
    # Battery
    battery_wh: float = 22.0

    # Power variables (Watts)
    P_mic:               float = 0.00198   # 0.6  mA @ 3.3V — MEMS mic listening
    P_mic_off:           float = 0.00033   # 0.1  mA @ 3.3V — mic deep sleep
    P_proc_shaI_active:  float = 0.528     # 160  mA @ 3.3V — ESP32 running AI filter
    P_proc_shaI_sleep:   float = 0.00264   # 0.8  mA @ 3.3V — ESP32 deep sleep
    P_wifi_tx:           float = 0.726     # 220  mA @ 3.3V — ESP32 WiFi TX

    # Timing variables (seconds)
    t_proc_shaI: float = 0.03              # per-event AI inference burst (30 ms default)
    t_tx_wifi:   float = 0.005             # per-frame WiFi airtime (5 ms typical small packet)

    @classmethod
    def from_gui_payload(cls, payload: Optional[Dict[str, Any]]) -> "ShamanIConfig":
        """Map the Configure Run payload onto spec variables."""
        inst = cls()
        if not payload:
            return inst
        inst.battery_wh = float(payload.get("batteryLife") or inst.battery_wh)
        comps = payload.get("components") or {}

        def w(name: str, default: float) -> float:
            cp = ComponentPower.from_cvp_dict(comps.get(name))
            return cp.watts if cp.watts > 0 else default

        inst.P_proc_shaI_sleep  = w("sleep",     inst.P_proc_shaI_sleep)
        inst.P_proc_shaI_active = w("working",   inst.P_proc_shaI_active)
        inst.P_wifi_tx          = w("transmit",  inst.P_wifi_tx)
        inst.P_mic              = w("micListen", inst.P_mic)
        inst.P_mic_off          = w("micSleep",  inst.P_mic_off)
        return inst


# ---------------------------------------------------------------------------
# Shaman II — relay/gateway (main proc + ESP32 controller + LoRa + WiFi-RX)
# ---------------------------------------------------------------------------

@dataclass
class ShamanIIConfig:
    """Shaman II relay/gateway power and timing variables."""
    # Battery
    battery_wh: float = 22.0

    # Power variables (Watts) — main processor (e.g. Radxa-class SBC)
    P_proc_shaII_active: float = 3.5
    P_proc_shaII_sleep:  float = 0.5

    # Power variables (Watts) — ESP32 controller handling the radio
    P_controller_active: float = 0.528     # 160 mA @ 3.3V
    P_controller_sleep:  float = 0.00264   # 0.8 mA @ 3.3V

    # Power variables (Watts) — radios
    P_lora_tx:  float = 0.389              # 118 mA @ 3.3V — SX1276 PA @ +14 dBm
    P_lora_rx:  float = 0.0198             # 6   mA @ 3.3V — SX1276 RX mode
    P_wifi_rx:  float = 0.330              # 100 mA @ 3.3V — ESP32 WiFi RX

    # CSMA backoff power (during retry wait)
    P_backoff:  float = 0.0198             # same as lora_rx (radio listens while waiting)

    # Timing variables (seconds)
    t_proc_shaII: float = 0.010            # per-received-event processing burst (10 ms)
    t_rx_wifi:    float = 0.005            # per-frame WiFi RX airtime (matches t_tx_wifi)
    t_backoff:    float = 0.100            # typical CSMA backoff wait (100 ms)

    # t_tx_lora / t_rx_lora are derived from RadioConfig (per-frame LoRa airtime)

    @classmethod
    def from_gui_payload(cls, payload: Optional[Dict[str, Any]]) -> "ShamanIIConfig":
        """Map the Configure Run payload onto spec variables."""
        inst = cls()
        if not payload:
            return inst
        inst.battery_wh = float(payload.get("batteryLife") or inst.battery_wh)
        comps = payload.get("components") or {}

        def w(name: str, default: float) -> float:
            cp = ComponentPower.from_cvp_dict(comps.get(name))
            return cp.watts if cp.watts > 0 else default

        inst.P_proc_shaII_sleep  = w("sleep",    inst.P_proc_shaII_sleep)
        inst.P_proc_shaII_active = w("working",  inst.P_proc_shaII_active)
        inst.P_lora_tx           = w("transmit", inst.P_lora_tx)
        inst.P_lora_rx           = w("receive",  inst.P_lora_rx)
        # Controller + WiFi RX + backoff: no GUI fields → keep defaults.
        return inst


# ---------------------------------------------------------------------------
# Radio (LoRa packet-level params + WiFi durations + CSMA retry model)
# ---------------------------------------------------------------------------

@dataclass
class RadioConfig:
    """LoRa + WiFi protocol parameters used to compute airtimes and retries."""
    # LoRa
    packet_bytes:     int = 128            # semantic transmission payload
    spreading_factor: int = 10             # SF10 per project docs
    bandwidth_hz:     int = 125_000        # 125 kHz (LoRaWAN default)
    coding_rate:      int = 5              # 4/5
    preamble_symbols: int = 8
    frames_per_hop:   int = 3              # data + ACK + handshake per Kyle's spec

    # CSMA retry model (no GUI input today — approximation)
    # Average retries per TX. 0 = best-case. Set >0 to model contention.
    avg_retries_per_tx: float = 0.0

    def airtime_per_frame_s(self) -> float:
        """Semtech SX1276 §4.1.1.6 LoRa time-on-air for one frame."""
        sf = self.spreading_factor
        bw = self.bandwidth_hz
        cr = self.coding_rate
        pl = self.packet_bytes

        t_sym      = (2 ** sf) / bw
        t_preamble = (self.preamble_symbols + 4.25) * t_sym
        numerator  = 8 * pl - 4 * sf + 28 + 16
        denom      = 4 * sf
        n_payload  = 8 + max(math.ceil(numerator / denom) * cr, 0)
        t_payload  = n_payload * t_sym
        return t_preamble + t_payload

    # Spec helper names
    @property
    def t_tx_lora(self) -> float:
        """Per-frame LoRa TX airtime (seconds)."""
        return self.airtime_per_frame_s()

    @property
    def t_rx_lora(self) -> float:
        """Per-frame LoRa RX airtime (seconds) — equals TX airtime."""
        return self.airtime_per_frame_s()

    @property
    def t_hop_lora(self) -> float:
        """Total LoRa hop time = t_tx_lora × frames_per_hop."""
        return self.t_tx_lora * self.frames_per_hop


# ---------------------------------------------------------------------------
# Top-level simulation config
# ---------------------------------------------------------------------------

@dataclass
class SimulationConfig:
    """Complete config bundle consumed by `BatterySimulator`."""
    shaman_i:  ShamanIConfig  = field(default_factory=ShamanIConfig)
    shaman_ii: ShamanIIConfig = field(default_factory=ShamanIIConfig)
    radio:     RadioConfig    = field(default_factory=RadioConfig)
    time_step_seconds: float  = 60.0

    @classmethod
    def from_run_config(cls,
                        shaman_i_config:  Optional[Dict[str, Any]] = None,
                        shaman_ii_config: Optional[Dict[str, Any]] = None,
                        radio_config:     Optional[Dict[str, Any]] = None,
                        ) -> "SimulationConfig":
        """Build a SimulationConfig from the Configure Run modal payloads."""
        cfg = cls(
            shaman_i  = ShamanIConfig.from_gui_payload(shaman_i_config),
            shaman_ii = ShamanIIConfig.from_gui_payload(shaman_ii_config),
        )
        if radio_config:
            for k, v in radio_config.items():
                if hasattr(cfg.radio, k) and v is not None:
                    setattr(cfg.radio, k, v)
        return cfg
