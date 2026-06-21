from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Radius, Typography
from app.utils.translations import tr


class SplashColors:
    BG_PRIMARY = "#0b0d12"
    BG_SECONDARY = "#11151d"
    TEXT_MUTED = "#827b70"
    TEXT_DISABLED = "#514d47"
    ACCENT_PRIMARY = "#d8aa5a"
    ACCENT_LIGHT = "#f0ce82"


class SplashScreen(QWidget):
    """Premium splash screen with cinematic fade and minimal design."""

    loadingFinished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setFixedSize(480, 320)

        # Opaque container
        self.container = QFrame(self)
        self.container.setObjectName("Container")
        self.container.setFixedSize(460, 300)
        self.container.move(10, 10)

        self.container.setStyleSheet(f"""
            QFrame#Container {{
                background: qlineargradient(x1:0, y1:0, x2:0.3, y2:1,
                    stop:0 #0c0c10, stop:0.5 {SplashColors.BG_SECONDARY}, stop:1 {SplashColors.BG_PRIMARY});
                border-radius: {Radius.LG}px;
                border: 1px solid rgba(255, 255, 255, 0.06);
            }}
        """)

        # Fade-in animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(180)
        self._fade_anim.setStartValue(0)
        self._fade_anim.setEndValue(1)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade_anim.start()

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = (screen_geo.width() - self.width()) // 2
            y = (screen_geo.height() - self.height()) // 2
            self.move(x, y)

        self._progress = 0
        self._status = tr("loading")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(44, 36, 44, 32)
        layout.setSpacing(12)

        layout.addStretch(1)

        # App name
        self.title = QLabel(tr("app_name"), self.container)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(f"""
            QLabel {{
                color: {SplashColors.ACCENT_PRIMARY};
                font-size: 38px;
                font-weight: 800;
                letter-spacing: 1px;
                background: transparent;
                font-family: {Typography.FAMILY};
            }}
        """)
        layout.addWidget(self.title)

        # Subtle accent line
        accent_line = QFrame(self.container)
        accent_line.setFixedHeight(2)
        accent_line.setFixedWidth(60)
        accent_line.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 transparent, stop:0.3 {SplashColors.ACCENT_PRIMARY},"
            f" stop:0.7 {SplashColors.ACCENT_PRIMARY}, stop:1 transparent);"
            f" border-radius: 1px;"
        )
        accent_container = QVBoxLayout()
        accent_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        accent_container.addWidget(accent_line, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(accent_container)

        # Subtitle
        self.subtitle = QLabel("Church Presentation", self.container)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setStyleSheet(f"""
            QLabel {{
                color: {SplashColors.TEXT_MUTED};
                font-size: 10px;
                letter-spacing: 5px;
                font-weight: 600;
                background: transparent;
                text-transform: uppercase;
                font-family: {Typography.FAMILY};
            }}
        """)
        layout.addWidget(self.subtitle)

        layout.addStretch(1)

        # Progress bar
        self.progress_bar = QProgressBar(self.container)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(255, 255, 255, 0.03);
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {SplashColors.ACCENT_PRIMARY}, stop:1 {SplashColors.ACCENT_LIGHT});
                border-radius: 1px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel(tr("loading"), self.container)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {SplashColors.TEXT_MUTED};
                font-size: 10px;
                font-weight: 500;
                background: transparent;
                font-family: {Typography.FAMILY};
            }}
        """)
        layout.addWidget(self.status_label)

        # Footer
        footer_layout = QVBoxLayout()
        footer_layout.setSpacing(2)

        self.version_label = QLabel("v1.0.0", self.container)
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setStyleSheet(f"""
            QLabel {{
                color: {SplashColors.TEXT_DISABLED};
                font-size: 9px;
                font-weight: 600;
                background: transparent;
                letter-spacing: 0.5px;
            }}
        """)
        footer_layout.addWidget(self.version_label)

        self.copyright_label = QLabel(
            "Onzième Heure Tab", self.container
        )
        self.copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.copyright_label.setStyleSheet(f"""
            QLabel {{
                color: {SplashColors.TEXT_DISABLED};
                font-size: 8px;
                background: transparent;
            }}
        """)
        footer_layout.addWidget(self.copyright_label)

        layout.addLayout(footer_layout)

    def set_progress(self, value: int, status: str = "") -> None:
        """Update progress bar and status message."""
        self._progress = min(100, max(0, value))
        self.progress_bar.setValue(self._progress)
        if status:
            self.status_label.setText(status)
        QApplication.processEvents()

    def finish(self, main_window: QWidget) -> None:
        """Finish splash and show main window."""
        self.set_progress(100, tr("ok"))
        QTimer.singleShot(80, lambda: self._show_main(main_window))

    def _show_main(self, main_window: QWidget) -> None:
        main_window.show()
        self.close()
        self.loadingFinished.emit()
