"""
Battery simulation configuration.

Holds every number the math needs:
  - ShamanIConfig:  power vars used by the Shaman I equation (sensor)
  - ShamanIIConfig: power vars used by the Shaman II equation (relay/gateway)
  - RadioConfig:    LoRa packet params + Semtech airtime formula
  - SimulationConfig: bundle of all three + the time-step size

Equations these feed (see docs/BATTERY_MATH.md for the full write-up):

    Shaman I:
        E_baseline = (P_proc_shaI_active + P_mic) * T
        E_tx       = n_local * P_wifi_tx * t_tx_wifi * frames_per_hop

    Shaman II:
        E_baseline = (P_controller_sleep + P_lora_rx + P_proc_shaII_sleep) * T
        E_rx_wifi  = n_received_wifi * P_wifi_rx * t_rx_wifi
        E_rx_lora  = n_received_lora * P_lora_rx * t_rx_lora
        E_tx       = n_forward      * P_lora_tx * t_tx_lora * frames_per_hop
        E_process  = n_received     * (P_proc_shaII_active - P_proc_shaII_sleep) * t_proc_shaII

GUI mapping (Configure Run modal -> spec variables):

    Shaman I  components.{sleep|working|transmit|micListen}
        sleep      -> (unused; sensor proc is always-active per spec)
        working    -> P_proc_shaI_active
        transmit   -> P_wifi_tx
        micListen  -> P_mic

    Shaman II components.{sleep|working|transmit|receive}
        sleep      -> P_proc_shaII_sleep
        working    -> P_proc_shaII_active
        transmit   -> P_lora_tx
        receive    -> P_lora_rx
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
import math


@dataclass
class ComponentPower:
    """One state's power draw. Accept current+voltage OR explicit watts."""
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
        if not d:
            return cls()
        return cls(
            current_ma=d.get("current"),
            voltage_v=d.get("voltage"),
            power_w=d.get("power"),
        )


# ---------------------------------------------------------------------------
# Shaman I — sensor (mic + ESP32 + WiFi uplink)
# ---------------------------------------------------------------------------

@dataclass
class ShamanIConfig:
    battery_wh: float = 22.0

    # Power (Watts)
    P_mic:               float = 0.00198   # 0.6 mA @ 3.3V (MEMS mic listening)
    P_proc_shaI_active:  float = 0.528     # 160 mA @ 3.3V (ESP32 running AI filter)
    P_wifi_tx:           float = 0.726     # 220 mA @ 3.3V (ESP32 WiFi TX)

    # Timing (seconds)
    t_tx_wifi: float = 0.005               # per-frame WiFi airtime

    @classmethod
    def from_gui_payload(cls, payload: Optional[Dict[str, Any]]) -> "ShamanIConfig":
        inst = cls()
        if not payload:
            return inst
        inst.battery_wh = float(payload.get("batteryLife") or inst.battery_wh)
        comps = payload.get("components") or {}

        def w(name: str, default: float) -> float:
            cp = ComponentPower.from_cvp_dict(comps.get(name))
            return cp.watts if cp.watts > 0 else default

        inst.P_proc_shaI_active = w("working",   inst.P_proc_shaI_active)
        inst.P_wifi_tx          = w("transmit",  inst.P_wifi_tx)
        inst.P_mic              = w("micListen", inst.P_mic)
        return inst


# ---------------------------------------------------------------------------
# Shaman II — relay / gateway (main proc + ESP32 controller + LoRa + WiFi-RX)
# ---------------------------------------------------------------------------

@dataclass
class ShamanIIConfig:
    battery_wh: float = 22.0

    # Power (Watts) — main processor
    P_proc_shaII_active: float = 3.5
    P_proc_shaII_sleep:  float = 0.5

    # Power (Watts) — ESP32 controller (only sleep figure used in baseline)
    P_controller_sleep:  float = 0.00264

    # Power (Watts) — radios
    P_lora_tx: float = 0.389              # 118 mA @ 3.3V (SX1276 +14 dBm)
    P_lora_rx: float = 0.0198             # 6   mA @ 3.3V (SX1276 RX)
    P_wifi_rx: float = 0.330              # 100 mA @ 3.3V (ESP32 WiFi RX)

    # Timing (seconds)
    t_proc_shaII: float = 0.010           # per-event main-proc burst
    t_rx_wifi:    float = 0.005           # per-frame WiFi RX airtime

    @classmethod
    def from_gui_payload(cls, payload: Optional[Dict[str, Any]]) -> "ShamanIIConfig":
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
        return inst


# ---------------------------------------------------------------------------
# Radio (LoRa packet params + WiFi durations + Semtech airtime formula)
# ---------------------------------------------------------------------------

@dataclass
class RadioConfig:
    packet_bytes:     int = 128
    spreading_factor: int = 10
    bandwidth_hz:     int = 125_000
    coding_rate:      int = 5
    preamble_symbols: int = 8
    frames_per_hop:   int = 3

    def airtime_per_frame_s(self) -> float:
        """Semtech SX1276 §4.1.1.6 LoRa time-on-air for one frame."""
        sf = self.spreading_factor
        bw = self.bandwidth_hz
        cr = self.coding_rate
        pl = self.packet_bytes

        t_sym      = (2 ** sf) / bw
        t_preamble = (self.preamble_symbols + 4.25) * t_sym
        n_payload  = 8 + max(math.ceil((8 * pl - 4 * sf + 28 + 16) / (4 * sf)) * cr, 0)
        t_payload  = n_payload * t_sym
        return t_preamble + t_payload

    @property
    def t_tx_lora(self) -> float:
        return self.airtime_per_frame_s()

    @property
    def t_rx_lora(self) -> float:
        return self.airtime_per_frame_s()


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------

@dataclass
class SimulationConfig:
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
        cfg = cls(
            shaman_i  = ShamanIConfig.from_gui_payload(shaman_i_config),
            shaman_ii = ShamanIIConfig.from_gui_payload(shaman_ii_config),
        )
        if radio_config:
            for k, v in radio_config.items():
                if hasattr(cfg.radio, k) and v is not None:
                    setattr(cfg.radio, k, v)
        return cfg
