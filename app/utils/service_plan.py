"""Suivi du déroulé du culte : heures prévues, section en cours, avance/retard.

Logique pure (sans Qt) : le panneau Déroulé l'affiche, les tests la
vérifient avec des heures fixes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PlanSection:
    id: int
    name: str
    duration_min: int
    item_id: int | None = None


def parse_start_time(value: str) -> tuple[int, int] | None:
    """« 9h30 », « 09:30 », « 9 » → (9, 30) ; None si vide ou invalide."""
    match = re.fullmatch(r"\s*(\d{1,2})\s*(?:[:hH.]\s*(\d{1,2})?)?\s*", str(value or ""))
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2) or 0)
    if hours > 23 or minutes > 59:
        return None
    return hours, minutes


def format_duration(seconds: float) -> str:
    seconds = int(round(abs(seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


@dataclass
class ServiceTracker:
    """Section en cours et écart au programme.

    ``planned_offsets`` : minute de début prévue de chaque section depuis le
    début du culte. L'écart compare l'heure réelle d'entrée dans la section
    en cours à son heure prévue, puis tient compte du dépassement de sa
    durée : un retard grandit en direct quand la section déborde.
    """

    sections: list[PlanSection] = field(default_factory=list)
    started_at: datetime | None = None
    current: int = -1
    entered_at: datetime | None = None
    actual_starts: dict[int, datetime] = field(default_factory=dict)

    def planned_offset_min(self, index: int) -> int:
        return sum(s.duration_min for s in self.sections[:index])

    def planned_start(self, index: int, start: datetime) -> datetime:
        return start + timedelta(minutes=self.planned_offset_min(index))

    @property
    def total_min(self) -> int:
        return sum(s.duration_min for s in self.sections)

    @property
    def running(self) -> bool:
        return self.started_at is not None and 0 <= self.current < len(self.sections)

    def start(self, now: datetime) -> None:
        self.started_at = now
        self.actual_starts = {}
        self.current = -1
        if self.sections:
            self.enter(0, now)

    def stop(self) -> None:
        self.started_at = None
        self.current = -1
        self.entered_at = None

    def enter(self, index: int, now: datetime) -> bool:
        if not 0 <= index < len(self.sections):
            return False
        if self.started_at is None:
            self.started_at = now
        self.current = index
        self.entered_at = now
        self.actual_starts.setdefault(index, now)
        return True

    def next(self, now: datetime) -> bool:
        return self.enter(self.current + 1, now)

    def enter_item(self, item_id: int, now: datetime) -> bool:
        """Slide projeté : entre dans la section qui démarre par ce slide."""
        for index, section in enumerate(self.sections):
            if section.item_id is not None and int(section.item_id) == int(item_id):
                if index == self.current:
                    return False
                return self.enter(index, now)
        return False

    def status(self, now: datetime, reference_start: datetime | None = None) -> dict:
        """État lisible : section, temps écoulé/restant, écart (+ = retard)."""
        base = reference_start or self.started_at
        if not self.running or base is None or self.entered_at is None:
            return {"running": False}
        section = self.sections[self.current]
        elapsed = (now - self.entered_at).total_seconds()
        planned = section.duration_min * 60
        planned_entry = self.planned_start(self.current, base)
        late_entry = (self.entered_at - planned_entry).total_seconds()
        overrun = max(0.0, elapsed - planned)
        delay = late_entry + overrun
        end = self.planned_start(len(self.sections), base) + timedelta(seconds=max(0.0, delay))
        return {
            "running": True,
            "index": self.current,
            "name": section.name,
            "elapsed": elapsed,
            "remaining": planned - elapsed,
            "delay": delay,
            "expected_end": end,
        }


def describe_delay(delay_seconds: float) -> str:
    if abs(delay_seconds) < 60:
        return "à l'heure"
    text = format_duration(delay_seconds)
    return f"{text} de retard" if delay_seconds > 0 else f"{text} d'avance"
