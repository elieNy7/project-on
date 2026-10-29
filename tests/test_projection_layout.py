"""Projection locale : zone de sécurité, remplissage, découpe, interligne,
fond gardé en cache et envoi immédiat des slides."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication

from app.ui.projection_window import ProjectionWindow
from app.ui.slide_canvas import SlideCanvas
from app.utils.models import Slide
from app.utils.settings import ProjectionSettings
from app.utils.slide_writer import SlideWriter

JOHN = (
    "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque "
    "croit en lui ne périsse point, mais qu'il ait la vie éternelle."
)
HYMN = (
    "Quel ami fidèle et tendre\nNous avons en Jésus-Christ,\n"
    "Toujours prêt à nous entendre,\nÀ répondre à notre cri !"
)


def _canvas(**settings) -> SlideCanvas:
    QApplication.instance() or QApplication([])
    canvas = SlideCanvas()
    canvas.resize(1920, 1080)
    canvas.apply_config(ProjectionSettings(**settings).to_presentation_config())
    return canvas


def _lines(canvas: SlideCanvas) -> list[str]:
    return canvas.text_label.text().split("\n")


def test_safe_area_keeps_five_percent_even_without_margin() -> None:
    canvas = _canvas(safe_margin=0)
    margins = canvas._main_layout.contentsMargins()
    assert margins.left() >= 96 and margins.right() >= 96  # 5 % de 1920
    assert margins.top() >= 54 and margins.bottom() >= 54  # 5 % de 1080
    wider = _canvas(safe_margin=200)  # une marge réglée plus grande l'emporte
    assert wider._main_layout.contentsMargins().left() == 200


def test_short_text_fills_the_screen() -> None:
    canvas = _canvas(text_size=45)
    canvas.set_slide({"text": "Jésus pleura.", "reference": "Jean 11:35"})
    size = canvas.text_label.font().pixelSize()
    assert size > 45 * 1.75  # l'ancien plafond
    assert size <= 45 * SlideCanvas.FILL_CEILING


def test_lines_are_balanced_without_a_lonely_last_word() -> None:
    canvas = _canvas(text_size=45)
    canvas.set_slide({"text": JOHN, "reference": "Jean 3:16"})
    lengths = [len(line) for line in _lines(canvas)]
    assert len(lengths) > 1
    assert min(lengths) >= 0.6 * max(lengths)


def test_hymn_verses_stay_on_their_own_line() -> None:
    canvas = _canvas(text_size=45)
    canvas.set_slide({"text": HYMN, "reference": "Cantique 12", "source": "hymn"})
    assert _lines(canvas) == HYMN.split("\n")


def test_line_height_setting_spaces_the_lines() -> None:
    tight = _canvas(text_size=45, line_height=1.0)
    tight.set_slide({"text": HYMN, "reference": ""})
    loose = _canvas(text_size=45, line_height=1.6)
    loose.set_slide({"text": HYMN, "reference": ""})
    assert tight.text_label._extra_leading() == 0
    assert loose.text_label._extra_leading() > 0
    # À taille égale, le bloc interligné est plus haut ; sinon il a dû rétrécir.
    tight_size = tight.text_label.font().pixelSize()
    loose_size = loose.text_label.font().pixelSize()
    if loose_size == tight_size:
        assert loose.text_label.sizeHint().height() > tight.text_label.sizeHint().height()
    else:
        assert loose_size < tight_size


def test_background_is_composed_once_while_nothing_changes(monkeypatch) -> None:
    canvas = _canvas()
    canvas.set_slide({"text": "Dieu est amour.", "reference": "1 Jean 4:8"})
    calls = []
    paint = canvas._paint_background
    monkeypatch.setattr(canvas, "_paint_background", lambda *a: calls.append(1) or paint(*a))
    canvas.grab()
    canvas.grab()
    assert len(calls) == 1
    canvas.apply_config(ProjectionSettings(bg_color="#203040").to_presentation_config())
    canvas.grab()
    assert len(calls) == 2  # un réglage changé redessine le fond


def test_slide_writer_notifies_listeners_and_survives_their_errors(tmp_path: Path) -> None:
    writer = SlideWriter(tmp_path)
    seen = []
    writer.add_listener(lambda: 1 / 0)
    writer.add_listener(lambda: seen.append((tmp_path / "slide.json").exists()))
    writer.write(Slide(reference="Jean 3:16", text=JOHN, source="bible"))
    assert seen == [True]


def test_projection_shows_a_written_slide_without_waiting_for_polling(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = ProjectionWindow(tmp_path)
    window._timer.stop()  # seule la notification peut faire avancer l'affichage
    ticks = []
    tick = window._tick
    window._tick = lambda: (ticks.append(timer.elapsed()), tick())
    writer = SlideWriter(tmp_path)
    writer.add_listener(window.notify_slide_written)
    timer = QElapsedTimer()
    timer.start()
    writer.write(Slide(reference="Jean 11:35", text="Jésus pleura.", source="bible"))
    while window._current_slide.get("text") != "Jésus pleura." and timer.elapsed() < 10000:
        app.processEvents()
    assert window._current_slide.get("text") == "Jésus pleura."
    # Lu au tour de boucle suivant, pas au prochain passage (250 ms) ; le
    # reste du délai est le premier dessin des lettres, hors écran.
    assert ticks and ticks[0] < 150
    writer.remove_listener(window.notify_slide_written)
    window.close()
    app.processEvents()


def test_french_punctuation_never_starts_a_line() -> None:
    canvas = _canvas(text_size=45)
    text = (
        "Ce qu'Il a dit au commencement, Il le dit encore aujourd'hui ; et ce qu'Il "
        "a fait autrefois, Il le fait encore ce soir : « Je suis le même » ! Pourquoi "
        "douter ? Regardez à la Parole."
    )
    for width in (700, 900, 1300, 1700):
        canvas.resize(width, 1080)
        canvas.apply_config(ProjectionSettings(text_size=45).to_presentation_config())
        canvas.set_slide({"text": text, "reference": ""})
        for line in _lines(canvas):
            assert line[:1] not in ";:!?»", line
            assert not line.endswith("«"), line
