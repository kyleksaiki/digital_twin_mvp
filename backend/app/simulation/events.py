"""
AI event timeline for the battery simulation.

What this file defines:
  - `SimEvent`: one detection event (node, timestamp, type, confirmed?, etc.)
  - `EventTimeline`: a sorted collection of `SimEvent`s plus constructors
                     for each supported event source.

Event sources supported (priority order, highest first):
  1. An AI event-timeline JSON file  → loaded via `ai_event_loader.py`.
  2. The `ai_events` DB table        → `EventTimeline.from_db_events(...)`.
  3. Synthetic mock events           → `EventTimeline.generate_mock(...)`.

Each event carries separate stage-1 and stage-2 durations because the sensor
hardware incurs different energy costs for each stage.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SimEvent:
    """A single detection event consumed by the battery simulator."""
    node_id: str
    timestamp_s: float
    event_type: str          # e.g. "bird_confirmed", "gunshot_candidate"
    confirmed: bool          # stage 2 accepted → triggers LoRa TX
    confidence: float = 1.0

    # Shaman I hardware does stage 1 + stage 2 locally. We record the
    # durations so the engine can convert them to energy.
    stage1_duration_s: float = 0.0      # DSP prefilter burst (usually 0 → baseline)
    stage2_duration_s: float = 0.03     # confirmation model inference
    clip_duration_s:   float = 3.0      # original audio clip length (for reference)

    @property
    def timestamp_ms(self) -> int:
        return int(self.timestamp_s * 1000)


@dataclass
class EventTimeline:
    """Sorted timeline of detection events across one or more nodes."""
    events: List[SimEvent] = field(default_factory=list)
    duration_seconds: float = 3 * 3600

    def __post_init__(self):
        self.events.sort(key=lambda e: e.timestamp_s)

    # ---- query helpers -----------------------------------------------------

    def for_node(self, node_id: str) -> List[SimEvent]:
        return [e for e in self.events if e.node_id == node_id]

    def confirmed_count(self) -> int:
        return sum(1 for e in self.events if e.confirmed)

    def candidate_count(self) -> int:
        return sum(1 for e in self.events if not e.confirmed)

    # ---- constructors ------------------------------------------------------

    @classmethod
    def from_db_events(cls, db_events: List, duration_hours: float = 3.0
                       ) -> "EventTimeline":
        """Build from the legacy `ai_events` DB rows.

        The old table has no candidate/confirmed distinction — we treat every
        row as confirmed (conservative: overestimates TX drain).
        """
        events: List[SimEvent] = []
        for e in db_events:
            ts_ms = e.timestamp_ms if hasattr(e, "timestamp_ms") else e["timestamp_ms"]
            events.append(SimEvent(
                node_id      = e.node_id    if hasattr(e, "node_id")    else e["node_id"],
                timestamp_s  = ts_ms / 1000.0,
                event_type   = e.event_type if hasattr(e, "event_type") else e["event_type"],
                confidence   = (e.confidence if hasattr(e, "confidence") else e.get("confidence", 1.0)),
                confirmed    = True,
            ))
        return cls(events=events, duration_seconds=duration_hours * 3600)

    @classmethod
    def generate_mock(cls, node_ids: List[str], duration_hours: float = 3.0,
                      events_per_node: int = 15) -> "EventTimeline":
        """Generate a random event timeline for testing."""
        import random
        events: List[SimEvent] = []
        duration_s = duration_hours * 3600
        for node_id in node_ids:
            n = random.randint(max(0, events_per_node - 5), events_per_node + 5)
            for _ in range(n):
                confirmed = random.random() > 0.4   # ~60% confirmed
                events.append(SimEvent(
                    node_id     = node_id,
                    timestamp_s = random.uniform(0, duration_s),
                    event_type  = random.choice(["bird_confirmed", "gunshot_confirmed",
                                                 "bird_candidate", "gunshot_candidate"]),
                    confidence  = random.uniform(0.7, 1.0),
                    confirmed   = confirmed,
                    stage2_duration_s = random.uniform(0.0005, 0.15),
                ))
        return cls(events=events, duration_seconds=duration_s)
