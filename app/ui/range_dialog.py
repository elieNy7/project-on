from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Colors, Spacing, Typography, get_input_style


class RangeDialog(QDialog):
    """Choix d'une plage « du N au M » pour l'ajout en série à une playlist.

    ``max_value`` est le nombre d'éléments disponibles ; les valeurs sont
    bornées et toujours renvoyées avec ``start <= end``.
    """

    def __init__(
        self,
        title: str,
        max_value: int,
        parent: QWidget | None = None,
        noun: str = "élément",
        default_span: int = 4,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(340)
        self._max_value = max(1, int(max_value))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.SM)

        summary = QLabel(f"{self._max_value} {noun}{'s' if self._max_value > 1 else ''} disponibles — ajouter de :", self)
        summary.setStyleSheet(
            f"font-size: {Typography.SIZE_BODY}px; color: {Colors.TEXT_PRIMARY};"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)

        start_label = QLabel("Du", self)
        start_label.setStyleSheet(
            f"font-size: {Typography.SIZE_BODY}px; color: {Colors.TEXT_SECONDARY};"
        )
        self.start_spin = QSpinBox(self)
        self.start_spin.setRange(1, self._max_value)
        self.start_spin.setValue(1)
        self.start_spin.setFixedHeight(34)
        self.start_spin.setStyleSheet(get_input_style())

        end_label = QLabel("au", self)
        end_label.setStyleSheet(
            f"font-size: {Typography.SIZE_BODY}px; color: {Colors.TEXT_SECONDARY};"
        )
        self.end_spin = QSpinBox(self)
        self.end_spin.setRange(1, self._max_value)
        self.end_spin.setValue(min(max(1, default_span), self._max_value))
        self.end_spin.setFixedHeight(34)
        self.end_spin.setStyleSheet(get_input_style())

        row.addWidget(start_label)
        row.addWidget(self.start_spin, 1)
        row.addWidget(end_label)
        row.addWidget(self.end_spin, 1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, int]:
        """Plage (premier, dernier), 1-based et toujours croissante."""
        start = int(self.start_spin.value())
        end = int(self.end_spin.value())
        if start > end:
            start, end = end, start
        return start, end
