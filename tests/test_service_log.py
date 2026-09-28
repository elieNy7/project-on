"""Historique du culte, sous-titres SRT et images de montage."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils.service_log import ServiceLog, slide_segments, to_csv, to_report, to_srt


def _t(h: int, m: int, s: int = 0) -> datetime:
    return datetime(2026, 9, 27, h, m, s)


def _log(tmp_path: Path) -> ServiceLog:
    log = ServiceLog(tmp_path / "history")
    log.record("section", reference="Louange", now=_t(9, 30))
    log.record("slide", reference="Cantique 12 - Strophe 1", text="À toi la gloire",
               source="hymn", program="Cantique 12", now=_t(9, 30, 5))
    log.record("slide", reference="Cantique 12 - Strophe 1", text="À toi la gloire",
               source="hymn", now=_t(9, 30, 9))  # doublon ignoré
    log.record("slide", reference="Jean 3:16", text="Car Dieu a tant aimé le monde",
               source="bible", now=_t(9, 31))
    log.record("hide", now=_t(9, 32))
    log.record("show", now=_t(9, 33))
    log.record("slide", reference="Romains 8:28", text="Toutes choses concourent",
               source="bible", now=_t(9, 34))
    return log


def test_record_and_read_back(tmp_path: Path) -> None:
    log = _log(tmp_path)
    assert log.days() == [date(2026, 9, 27)]
    events = log.events(date(2026, 9, 27))
    assert [e.event for e in events] == ["section", "slide", "slide", "hide", "show", "slide"]
    # Une ligne tronquée (coupure de courant) n'empêche pas la relecture.
    with log.path_for(date(2026, 9, 27)).open("a", encoding="utf-8") as handle:
        handle.write('{"t": "2026-09-27T09:3')
    assert len(log.events(date(2026, 9, 27))) == 6


def test_segments_respect_hiding(tmp_path: Path) -> None:
    events = _log(tmp_path).events(date(2026, 9, 27))
    segments = slide_segments(events, end=_t(9, 36))
    assert [(s.strftime("%H:%M:%S"), t.strftime("%H:%M:%S"), e.reference) for s, t, e in segments] == [
        ("09:30:05", "09:31:00", "Cantique 12 - Strophe 1"),
        ("09:31:00", "09:32:00", "Jean 3:16"),
        ("09:33:00", "09:34:00", "Jean 3:16"),
        ("09:34:00", "09:36:00", "Romains 8:28"),
    ]


def test_exports(tmp_path: Path) -> None:
    events = _log(tmp_path).events(date(2026, 9, 27))
    csv_text = to_csv(events)
    assert csv_text.splitlines()[0] == "Heure;Type;Programme;Référence;Texte"
    assert "09:31:00;Slide;;Jean 3:16;Car Dieu a tant aimé le monde" in csv_text
    report = to_report(events)
    assert "■ Louange" in report and "Jean 3:16" in report

    srt = to_srt(events, origin=_t(9, 30))
    first = srt.split("\n\n")[0].splitlines()
    assert first == ["1", "00:00:05,000 --> 00:01:00,000", "À toi la gloire",
                     "— Cantique 12 - Strophe 1"]
    assert "00:04:00,000 --> 00:14:00,000" in srt  # dernier slide plafonné à 10 min


def test_montage_export_writes_transparent_pngs(tmp_path: Path) -> None:
    from PIL import Image

    from app.utils.montage_export import export_montage

    events = _log(tmp_path).events(date(2026, 9, 27))
    report = export_montage(events, tmp_path / "montage", {"font_family": "Arial"},
                            origin=_t(9, 30), width=640, height=360)
    folder = tmp_path / "montage"
    assert report["images"] == 3 and report["segments"] == 4
    pngs = sorted(folder.glob("*.png"))
    assert len(pngs) == 3
    image = Image.open(pngs[0])
    assert image.mode == "RGBA" and image.getpixel((5, 5))[3] == 0  # fond transparent
    assert (folder / "sous-titres.srt").read_text("utf-8").startswith("1\n00:00:05,000")
    assert "Jean-3-16" in (folder / "minutage.csv").read_text("utf-8")


def test_history_dialog_lists_events(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.history_dialog import HistoryDialog

    dialog = HistoryDialog(_log(tmp_path))
    try:
        assert dialog.table.rowCount() == 6
        assert "3 slide(s)" in dialog.summary.text()
    finally:
        dialog.close()
