"""Historique du culte : journal horodaté de tout ce qui passe en direct.

Un fichier JSON Lines par jour (``data/history/AAAA-MM-JJ.jsonl``), une ligne
par événement : slide projeté, texte masqué/réaffiché, section du déroulé.
Le journal sert au rapport de culte (CSV, texte), aux sous-titres SRT et aux
images transparentes pour le montage vidéo.
"""

from __future__ import annotations

import csv
import io
import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

EVENT_LABELS = {
    "slide": "Slide",
    "hide": "Masqué",
    "show": "Réaffiché",
    "section": "Section",
}


@dataclass(frozen=True)
class LogEvent:
    time: datetime
    event: str
    reference: str = ""
    text: str = ""
    source: str = ""
    program: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "t": self.time.isoformat(timespec="seconds"),
            "event": self.event,
            "reference": self.reference,
            "text": self.text,
            "source": self.source,
            "program": self.program,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> LogEvent:
        return cls(
            time=datetime.fromisoformat(str(data["t"])),
            event=str(data.get("event") or "slide"),
            reference=str(data.get("reference") or ""),
            text=str(data.get("text") or ""),
            source=str(data.get("source") or ""),
            program=str(data.get("program") or ""),
        )


class ServiceLog:
    """Écrit et relit l'historique (sûr entre threads, append-only)."""

    def __init__(self, folder: Path) -> None:
        self._folder = Path(folder)
        self._lock = threading.Lock()
        self._last_key: tuple[str, str, str] | None = None

    @property
    def folder(self) -> Path:
        return self._folder

    def path_for(self, day: date) -> Path:
        return self._folder / f"{day.isoformat()}.jsonl"

    def record(self, event: str, *, reference: str = "", text: str = "",
               source: str = "", program: str = "", now: datetime | None = None) -> bool:
        """Ajoute un événement ; un slide identique au précédent est ignoré."""
        key = (event, reference, text)
        if event == "slide" and key == self._last_key:
            return False
        if event in ("slide", "section"):
            self._last_key = key if event == "slide" else None
        entry = LogEvent(now or datetime.now(), event, reference, text, source, program)
        try:
            with self._lock:
                self._folder.mkdir(parents=True, exist_ok=True)
                with self.path_for(entry.time.date()).open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry.to_json(), ensure_ascii=False) + "\n")
        except OSError:
            return False
        return True

    def days(self) -> list[date]:
        """Jours enregistrés, du plus récent au plus ancien."""
        out = []
        for path in self._folder.glob("*.jsonl"):
            try:
                out.append(date.fromisoformat(path.stem))
            except ValueError:
                continue
        return sorted(out, reverse=True)

    def events(self, day: date) -> list[LogEvent]:
        path = self.path_for(day)
        if not path.is_file():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(LogEvent.from_json(json.loads(line)))
            except (ValueError, KeyError):
                continue  # ligne tronquée (coupure de courant)
        return out


# ── Exports ────────────────────────────────────────────────────────────────


def to_csv(events: Iterable[LogEvent]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Heure", "Type", "Programme", "Référence", "Texte"])
    for e in events:
        writer.writerow([
            e.time.strftime("%H:%M:%S"), EVENT_LABELS.get(e.event, e.event),
            e.program, e.reference.replace("\n", " "), e.text.replace("\n", " / "),
        ])
    return buffer.getvalue()


def to_report(events: list[LogEvent], title: str = "") -> str:
    """Rapport lisible : sections, versets, cantiques et textes projetés."""
    lines = [title or "Historique du culte"]
    if events:
        lines.append(
            f"{events[0].time:%d/%m/%Y} · {events[0].time:%H:%M} → {events[-1].time:%H:%M}"
        )
    lines.append("")
    for e in events:
        stamp = e.time.strftime("%H:%M")
        if e.event == "section":
            lines.append(f"\n{stamp}  ■ {e.reference}")
        elif e.event == "slide":
            label = e.reference.replace("\n", " — ") or e.text.split("\n", 1)[0][:60]
            lines.append(f"{stamp}  {label}")
        elif e.event in ("hide", "show"):
            lines.append(f"{stamp}  ({EVENT_LABELS[e.event].lower()})")
    return "\n".join(lines).strip() + "\n"


def slide_segments(events: list[LogEvent], end: datetime | None = None,
                   max_duration: timedelta = timedelta(minutes=10)
                   ) -> list[tuple[datetime, datetime, LogEvent]]:
    """Intervalles d'affichage de chaque slide (masquage compris).

    Un slide reste affiché jusqu'au slide suivant ou au masquage ; le
    dernier dure jusqu'à ``end`` (plafonné à ``max_duration``).
    """
    segments: list[tuple[datetime, datetime, LogEvent]] = []
    current: LogEvent | None = None
    start: datetime | None = None
    visible = True
    for e in events:
        if e.event == "slide":
            if current is not None and start is not None and visible:
                segments.append((start, e.time, current))
            current, start = e, e.time
        elif e.event == "hide":
            if current is not None and start is not None and visible:
                segments.append((start, e.time, current))
            visible = False
        elif e.event == "show":
            visible = True
            start = e.time
    if current is not None and start is not None and visible:
        stop = end or (start + max_duration)
        segments.append((start, min(stop, start + max_duration), current))
    return [(s, t, e) for s, t, e in segments if t > s and (e.text or e.reference)]


def _srt_time(delta: timedelta) -> str:
    total_ms = max(0, int(delta.total_seconds() * 1000))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def to_srt(events: list[LogEvent], origin: datetime | None = None) -> str:
    """Sous-titres SRT calés sur l'heure de début de l'enregistrement vidéo."""
    segments = slide_segments(events)
    if not segments:
        return ""
    origin = origin or segments[0][0]
    blocks = []
    index = 0
    for start, stop, event in segments:
        if stop <= origin:
            continue
        index += 1
        text = event.text.strip()
        reference = event.reference.replace("\n", " — ").strip()
        body = f"{text}\n— {reference}" if text and reference else (text or reference)
        blocks.append(
            f"{index}\n{_srt_time(max(start, origin) - origin)} --> "
            f"{_srt_time(stop - origin)}\n{body}\n"
        )
    return "\n".join(blocks)
