"""KPI bell schedule: pair number → start/end time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class Slot:
    number: int
    start: time
    end: time

    @property
    def label(self) -> str:
        return f"{self.start:%H:%M}–{self.end:%H:%M}"


SLOTS: dict[int, Slot] = {
    1: Slot(1, time(8, 30), time(10, 5)),
    2: Slot(2, time(10, 25), time(12, 0)),
    3: Slot(3, time(12, 20), time(13, 55)),
    4: Slot(4, time(14, 15), time(15, 50)),
    5: Slot(5, time(16, 10), time(17, 45)),
    6: Slot(6, time(18, 30), time(20, 5)),
    7: Slot(7, time(20, 20), time(21, 55)),
}
MAX_SLOT = max(SLOTS)


def slot_for_start(value: str | time) -> int | None:
    """The pair whose start matches ``value`` (``"10:25"``, ``"10:25:00"`` or a ``time``)."""
    if isinstance(value, str):
        parts = value.strip().split(":")
        try:
            value = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return None
    for slot in SLOTS.values():
        if slot.start == value:
            return slot.number
    return None
