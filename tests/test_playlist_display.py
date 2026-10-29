"""Affichage des éléments de playlist : type (icône) et texte sur deux lignes."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from app.ui.playlist_tab import (
    ROLE_ID,
    ROLE_KIND,
    ROLE_REF,
    ROLE_TEXT,
    PlaylistTab,
    _two_lines,
    item_kind,
)


def test_stored_source_wins() -> None:
    assert item_kind("bible", "N'importe quoi") == "bible"
    assert item_kind("hymn", "") == "hymn"
    assert item_kind("media", "Affiche", "C:/a/affiche.png") == "image"
    assert item_kind("media", "Clip", "C:/a/clip.mp4") == "video"
    assert item_kind("media", "Cours", "C:/a/cours.pptx") == "powerpoint"


def test_old_custom_items_are_recognised_from_their_reference() -> None:
    assert item_kind("custom", "Jean 3:16") == "bible"
    assert item_kind("custom", "1 Corinthiens 13:4-7") == "bible"
    assert item_kind("custom", "Cantique 12 - Strophe 2") == "hymn"
    assert item_kind("custom", "65-0725M La Voix de Dieu - §42") == "sermon"
    assert item_kind("custom", "49-0718 - Titre - E-11 (3/7)") == "sermon"
    assert item_kind("custom", "Le Tabernacle · Page 3 §2") == "expose"
    assert item_kind("custom", "Bienvenue") == "custom"
    assert item_kind("", "") == "custom"


def test_two_lines_wraps_then_elides() -> None:
    QApplication.instance() or QApplication([])
    metrics = QFontMetrics(QFont("Arial", 10))
    text = "Car Dieu a tant aimé le monde qu'il a donné son Fils unique " * 4
    lines = _two_lines(text, metrics, 200)
    assert len(lines) == 2
    assert all(metrics.horizontalAdvance(line) <= 200 for line in lines)
    assert lines[1].endswith("…")
    assert _two_lines("Court", metrics, 200) == ["Court"]
    assert _two_lines("", metrics, 200) == []


def test_items_carry_reference_text_and_kind_in_the_right_roles() -> None:
    QApplication.instance() or QApplication([])
    tab = PlaylistTab()
    tab.resize(600, 400)
    tab.set_items([
        {"id": 7, "source": "custom", "reference": "Jean 3:16", "text": "Car Dieu…"},
        {"id": 8, "source": "media", "reference": "Clip", "text": "", "background": "c.mp4"},
    ])
    first, second = tab.items_list.item(0), tab.items_list.item(1)
    assert first.data(ROLE_ID) == 7
    assert first.data(ROLE_REF) == "Jean 3:16"
    assert first.data(ROLE_TEXT) == "Car Dieu…"
    assert first.data(ROLE_KIND) == "bible"
    assert second.data(ROLE_KIND) == "video"
    # La carte affiche bien la référence et le texte (et non l'identifiant).
    delegate = tab.items_list.itemDelegate()
    index = tab.items_list.model().index(0, 0, QModelIndex())
    assert delegate._lines(index) == ("Jean 3:16", "Car Dieu…")
    option = QStyleOptionViewItem()
    option.rect = tab.items_list.visualItemRect(first)
    assert delegate.sizeHint(option, index).height() >= 40
