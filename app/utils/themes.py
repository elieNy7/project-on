from __future__ import annotations

"""Thèmes de projection façon ProPresenter.

Un thème = un nom + un jeu de réglages stylistiques (une
:class:`~app.utils.settings.ProjectionSettings`). Le thème « actif » est
miroir de ``AppSettings.projection`` (source de vérité historique) ; les
autres thèmes vivent dans ``AppSettings.themes``. Chaque type de contenu
(bible, cantique, sermon…) peut être assigné à un thème précis — sans
assignation, la slide utilise le thème actif.
"""

import copy
import logging
from dataclasses import dataclass, field

from app.utils.settings import ProjectionSettings

log = logging.getLogger(__name__)

DEFAULT_THEME_ID = "default"

# Champs stylistiques portés par un thème (tout ProjectionSettings sauf
# l'écran de sortie, qui reste un choix matériel par machine).
_THEME_EXCLUDED_FIELDS = frozenset({"display_screen"})

# Types de contenu assignable à un thème.
ASSIGNABLE_SOURCES = (
    "bible",
    "hymn",
    "sermon",
    "expose",
    "custom",
    "image",
    "video",
    "web",
)


@dataclass
class Theme:
    id: str
    name: str
    style: ProjectionSettings = field(default_factory=ProjectionSettings)

    def to_payload(self) -> dict:
        cfg = self.style.to_presentation_config()
        return {"id": self.id, "name": self.name, "style": cfg}

    @classmethod
    def from_payload(cls, payload: dict) -> Theme | None:
        if not isinstance(payload, dict):
            return None
        theme_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not theme_id:
            return None
        style = ProjectionSettings()
        raw = payload.get("style")
        if isinstance(raw, dict):
            for key, value in raw.items():
                if hasattr(style, key) and key not in _THEME_EXCLUDED_FIELDS:
                    try:
                        setattr(style, key, value)
                    except Exception:
                        pass
        return cls(id=theme_id, name=name or theme_id, style=style)


def make_theme_id(name: str, existing: list[str]) -> str:
    """Identifiant stable et unique dérivé du nom (« or-bleu-nuit-2 »…)."""
    import re
    import unicodedata

    base = unicodedata.normalize("NFKD", str(name or "theme"))
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower() or "theme"
    theme_id = base
    n = 2
    while theme_id in existing:
        theme_id = f"{base}-{n}"
        n += 1
    return theme_id


def default_theme(projection: ProjectionSettings | None = None) -> Theme:
    """Thème « Par défaut » : miroir des réglages de projection actuels."""
    style = (
        copy.deepcopy(projection) if projection is not None else ProjectionSettings()
    )
    return Theme(id=DEFAULT_THEME_ID, name="Par défaut", style=style)


def builtin_theme_presets() -> list[Theme]:
    """Thèmes prédéfinis proposés dans le gestionnaire (« façon ProPresenter »)."""
    presets: list[Theme] = []

    dark = ProjectionSettings()
    dark.slide_style = "cinematic"
    dark.bg_mode = "color"
    dark.bg_gradient_enabled = True
    dark.bg_color = "#05070d"
    dark.bg_color_2 = "#101d33"
    dark.bg_gradient_angle = 160
    dark.text_color = "rgba(255,255,255,0.97)"
    dark.ref_color = "rgba(160,190,235,0.85)"
    presets.append(Theme(id="epure-nuit", name="Épuré Nuit", style=dark))

    gold = ProjectionSettings()
    gold.slide_style = "cinematic"
    gold.bg_mode = "color"
    gold.bg_gradient_enabled = True
    gold.bg_color = "#120d04"
    gold.bg_color_2 = "#33230b"
    gold.bg_gradient_angle = 145
    gold.text_color = "rgba(255,248,232,0.98)"
    gold.ref_color = "rgba(230,180,76,0.9)"
    presets.append(Theme(id="or-ancien", name="Or Ancien", style=gold))

    light = ProjectionSettings()
    light.slide_style = "clean"
    light.bg_mode = "color"
    light.bg_gradient_enabled = False
    light.bg_color = "#f4f1ea"
    light.text_color = "rgba(24,32,48,0.96)"
    light.ref_color = "rgba(90,102,124,0.9)"
    light.text_shadow = True
    light.shadow_color = "rgba(255,255,255,0.85)"
    light.shadow_blur = 10
    presets.append(Theme(id="blanc-minimal", name="Blanc Minimal", style=light))

    return presets


class ThemeRegistry:
    """Accès en lecture aux thèmes portés par la config de projection.

    Côté fenêtre (``ProjectionWindow``), les thèmes arrivent par
    ``config.json`` : ``themes`` (id → style), ``theme_assignments``,
    ``active_theme``.
    """

    def __init__(self, config: dict) -> None:
        themes_raw = config.get("themes")
        self.themes: dict[str, dict] = {}
        if isinstance(themes_raw, dict):
            for theme_id, style in themes_raw.items():
                if isinstance(style, dict):
                    self.themes[str(theme_id)] = dict(style)
        assignments = config.get("theme_assignments")
        self.assignments: dict[str, str] = {}
        if isinstance(assignments, dict):
            for source, theme_id in assignments.items():
                s = str(source or "").lower()
                t = str(theme_id or "").strip()
                if s and t and t in self.themes:
                    self.assignments[s] = t
        self.active_id = str(config.get("active_theme") or DEFAULT_THEME_ID)
        if self.active_id not in self.themes:
            self.active_id = next(iter(self.themes), DEFAULT_THEME_ID)

    def theme_id_for(self, source: str) -> str:
        return self.assignments.get(str(source or "").lower(), self.active_id)

    def style_for(self, source: str) -> dict | None:
        """Style effectif pour une source, ou None si identique au style
        global déjà appliqué (thème actif sans surcharge)."""
        theme_id = self.theme_id_for(source)
        if theme_id == self.active_id:
            return None
        style = self.themes.get(theme_id)
        return dict(style) if style else None
