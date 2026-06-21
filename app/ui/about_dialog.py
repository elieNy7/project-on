from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon
from app.ui.theme import Colors, Radius, Typography
from app.utils.translations import tr
from app.version import __version__


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("À propos de Project-On")
        self.setFixedSize(440, 520)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.BG_SECONDARY};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Top gradient section ──
        top_frame = QFrame(self)
        top_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(167, 139, 250, 0.08),
                    stop:0.5 rgba(96, 165, 250, 0.06),
                    stop:1 rgba(52, 211, 153, 0.05));
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            }}
        """)
        top_layout = QVBoxLayout(top_frame)
        top_layout.setContentsMargins(32, 32, 32, 24)
        top_layout.setSpacing(12)

        # Logo
        icon_label = QLabel(top_frame)
        icon_label.setPixmap(app_icon("monitor.svg", "#a78bfa").pixmap(56, 56))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        top_layout.addWidget(icon_label)

        # Title
        title = QLabel("Project-On", top_frame)
        title.setStyleSheet(f"""
            font-size: 26px;
            font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
            border: none;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(title)

        # Version badge
        version_frame = QFrame(top_frame)
        version_frame.setStyleSheet(f"""
            background: rgba(167, 139, 250, 0.12);
            border: 1px solid rgba(167, 139, 250, 0.25);
            border-radius: 12px;
            padding: 0;
        """)
        version_frame.setFixedWidth(120)
        v_layout = QHBoxLayout(version_frame)
        v_layout.setContentsMargins(12, 4, 12, 4)
        version_lbl = QLabel(f"v{__version__}", version_frame)
        version_lbl.setStyleSheet(f"""
            font-size: 12px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            color: #a78bfa;
            background: transparent;
            border: none;
        """)
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_layout.addWidget(version_lbl)

        # Center the version badge
        ver_container = QHBoxLayout()
        ver_container.addStretch()
        ver_container.addWidget(version_frame)
        ver_container.addStretch()
        top_layout.addLayout(ver_container)

        layout.addWidget(top_frame)

        # ── Content section ──
        content = QWidget(self)
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(32, 24, 32, 16)
        c_layout.setSpacing(16)

        # Description
        desc = QLabel(
            "Application professionnelle de projection pour églises et événements. "
            "Conçue pour la diffusion en direct et la présentation de textes bibliques.",
            content,
        )
        desc.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px;
            color: {Colors.TEXT_SECONDARY};
            background: transparent;
            line-height: 1.5;
        """)
        desc.setText(
            "Application professionnelle de projection pour églises et événements. "
            "Conçue pour la diffusion en direct, la présentation de textes bibliques et le pilotage du culte."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(desc)

        # Features list
        features = [
            ("book.svg", "Projection de versets bibliques"),
            ("music.svg", "Affichage de cantiques avec strophes"),
            ("book-open.svg", "Gestion de sermons et exposés"),
            ("cast.svg", "Intégration OBS avec Lower Third"),
            ("globe.svg", "Serveur web intégré pour streaming"),
        ]

        features_frame = QFrame(content)
        features_frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: {Radius.LG}px;
            }}
        """)
        f_layout = QVBoxLayout(features_frame)
        f_layout.setContentsMargins(16, 12, 16, 12)
        f_layout.setSpacing(8)

        for icon_name, feature_text in features:
            row = QHBoxLayout()
            row.setSpacing(10)

            feat_icon = QLabel(features_frame)
            feat_icon.setPixmap(app_icon(icon_name, Colors.TEXT_MUTED).pixmap(14, 14))
            feat_icon.setStyleSheet("background: transparent; border: none;")
            feat_icon.setFixedSize(14, 14)
            row.addWidget(feat_icon)

            feat_text = QLabel(feature_text, features_frame)
            feat_text.setStyleSheet(f"""
                font-size: 12px;
                color: {Colors.TEXT_SECONDARY};
                background: transparent;
                border: none;
            """)
            row.addWidget(feat_text, 1)
            f_layout.addLayout(row)

        c_layout.addWidget(features_frame)

        c_layout.addStretch()

        # Copyright & website
        copyright_label = QLabel("© 2025 Onzième Heure Tab. Tous droits réservés.", content)
        copyright_label.setStyleSheet(f"""
            font-size: 11px;
            color: {Colors.TEXT_DISABLED};
            background: transparent;
        """)
        copyright_label.setText("© 2025 Onzième Heure Tab. Tous droits réservés.")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(copyright_label)

        website_label = QLabel("Onzième Heure Tab", content)
        website_label.setStyleSheet(f"""
            font-size: 11px;
            color: {Colors.ACCENT_PRIMARY};
            background: transparent;
        """)
        website_label.setText("Onzième Heure Tab")
        website_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(website_label)

        # Attribution for the figurative background silhouettes (CC BY 3.0)
        credits_label = QLabel(
            "Silhouettes aigle/lion/agneau : game-icons.net (Lorc, Delapouite) — CC BY 3.0",
            content,
        )
        credits_label.setStyleSheet(f"""
            font-size: 10px;
            color: {Colors.TEXT_DISABLED};
            background: transparent;
        """)
        credits_label.setWordWrap(True)
        credits_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(credits_label)

        layout.addWidget(content, 1)

        # ── Footer ──
        footer = QFrame(self)
        footer.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_PRIMARY};
                border-top: 1px solid rgba(255, 255, 255, 0.06);
            }}
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 12)
        footer_layout.addStretch()

        close_btn = QPushButton(tr("close"), footer)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {Radius.MD}px;
                padding: 8px 28px;
                color: {Colors.TEXT_PRIMARY};
                font-size: 13px;
                font-weight: {Typography.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_ACTIVE};
                border-color: {Colors.BORDER_FOCUS};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        footer_layout.addWidget(close_btn)
        layout.addWidget(footer)

    @classmethod
    def show_about(cls, parent: QWidget | None = None) -> None:
        dialog = cls(parent)
        dialog.exec()
