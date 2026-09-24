"""The keyboard help lists every operator shortcut, in both languages."""

from __future__ import annotations

from app.ui.shortcuts_dialog import _SHORTCUTS
from app.utils.translations import set_language, tr


def test_new_workflow_shortcuts_are_documented() -> None:
    keys = {key for _label, key in _SHORTCUTS}
    assert {"F2", "Ctrl+K", "Clic"} <= keys  # preview/live and global search


def test_every_shortcut_is_translated() -> None:
    try:
        for language in ("fr", "en"):
            set_language(language)
            for label_key, _key in _SHORTCUTS:
                assert tr(label_key) != label_key, (language, label_key)
    finally:
        set_language("fr")
