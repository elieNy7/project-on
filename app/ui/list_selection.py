"""Select a QListWidget row by content (used to reveal global search hits)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem


def select_first(
    list_widget: QListWidget, predicate: Callable[[QListWidgetItem], bool]
) -> bool:
    """Select, unhide and scroll to the first matching row; False if none."""
    for row in range(list_widget.count()):
        item = list_widget.item(row)
        try:
            matches = predicate(item)
        except (TypeError, ValueError):
            matches = False
        if matches:
            item.setHidden(False)
            list_widget.setCurrentRow(row)
            list_widget.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
            return True
    return False
