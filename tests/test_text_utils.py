"""Tests unitaires pour app/utils/text_utils.py"""

from __future__ import annotations

import pytest
from app.utils.text_utils import (
    clean_text,
    format_hymn_for_obs_lower_third,
    format_hymn_reference_for_obs,
    strip_hymn_projection_label,
    unaccent,
)


class TestCleanText:
    def test_strips_html_tags(self):
        assert clean_text("<b>Bonjour</b>") == "Bonjour"

    def test_replaces_br_with_newline(self):
        result = clean_text("Ligne 1<br/>Ligne 2")
        assert "Ligne 1\nLigne 2" == result

    def test_unescapes_html_entities(self):
        assert clean_text("Dieu &amp; Seigneur") == "Dieu & Seigneur"

    def test_strips_bom_and_zero_width(self):
        assert clean_text("﻿Texte​") == "Texte"

    def test_removes_pilcrow(self):
        assert clean_text("¶ Paragraph text") == "Paragraph text"

    def test_collapses_whitespace(self):
        assert clean_text("Trop   d'espaces") == "Trop d'espaces"

    def test_strips_control_chars(self):
        assert clean_text("Texte\x01\x08propre") == "Textepropre"

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_none_value(self):
        assert clean_text(None) == ""

    def test_nbsp_replaced(self):
        assert clean_text("mot autre") == "mot autre"


class TestStripHymnLabel:
    def test_removes_refrain_prefix(self):
        assert strip_hymn_projection_label("Refrain: Gloire à Dieu") == "Gloire à Dieu"

    def test_removes_choeur_prefix(self):
        assert strip_hymn_projection_label("Chœur: Il est vivant") == "Il est vivant"

    def test_removes_chorus_prefix(self):
        assert strip_hymn_projection_label("Chorus - Alléluia") == "Alléluia"

    def test_no_label_unchanged(self):
        text = "Je veux chanter la grâce"
        assert strip_hymn_projection_label(text) == text

    def test_case_insensitive(self):
        assert strip_hymn_projection_label("REFRAIN :\nTexte du refrain") == "Texte du refrain"


class TestFormatHymnForObs:
    def test_flattens_multiline(self):
        result = format_hymn_for_obs_lower_third("Ligne un\nLigne deux")
        assert result == "Ligne un Ligne deux"

    def test_removes_leading_label(self):
        result = format_hymn_for_obs_lower_third("Refrain:\nGloire à Dieu")
        assert result == "Gloire à Dieu"

    def test_collapses_spaces(self):
        result = format_hymn_for_obs_lower_third("Mot   espacé")
        assert result == "Mot espacé"


class TestFormatHymnReference:
    def test_flattens_multiline_reference(self):
        result = format_hymn_reference_for_obs("Cantique 42\nStrophe 1")
        assert result == "Cantique 42 - Strophe 1"

    def test_empty_reference(self):
        assert format_hymn_reference_for_obs("") == ""


class TestUnaccent:
    def test_removes_accents(self):
        assert unaccent("Éléphant") == "elephant"

    def test_empty_string(self):
        assert unaccent("") == ""

    def test_already_ascii(self):
        assert unaccent("bonjour") == "bonjour"

    def test_cedille(self):
        assert unaccent("façon") == "facon"
