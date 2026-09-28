"""Raccourcis clavier configurables (télécommande de présentation, Stream Deck).

Chaque action de la régie a un raccourci par défaut, modifiable dans
Réglages → Raccourcis. Un Stream Deck (action « Raccourci clavier ») ou une
télécommande de présentation (qui envoie Page suivante / Page précédente, F5,
B…) pilote ainsi Project-On sans logiciel supplémentaire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ShortcutAction:
    id: str
    label: str
    default: str
    help_key: str = ""  # clé de traduction de l'aide F1, si elle existe


ACTIONS: tuple[ShortcutAction, ...] = (
    ShortcutAction("take", "Envoyer l'aperçu au direct", "F2", "shortcut_take"),
    ShortcutAction("next_slide", "Slide suivant (télécommande)", "PgDown"),
    ShortcutAction("prev_slide", "Slide précédent (télécommande)", "PgUp"),
    ShortcutAction("hide", "Masquer / afficher le texte", "B", "shortcut_hide"),
    ShortcutAction("projection", "Ouvrir / fermer la projection", "F5", "shortcut_projection"),
    ShortcutAction("hdmi_mire", "Mire de la sortie HDMI", "F8", "shortcut_hdmi_mire"),
    ShortcutAction("next_section", "Déroulé : section suivante", "Ctrl+Alt+N"),
    ShortcutAction("global_search", "Recherche globale", "Ctrl+K", "shortcut_search_everywhere"),
    ShortcutAction("search", "Rechercher dans l'onglet", "Ctrl+F", "shortcut_search"),
    ShortcutAction("paragraph_search", "Rechercher un paragraphe", "Ctrl+G", "shortcut_search_global"),
    ShortcutAction("preflight", "Contrôle avant culte", "Ctrl+Shift+D", "shortcut_preflight"),
    ShortcutAction("history", "Historique du culte", "Ctrl+H"),
    ShortcutAction("welcome", "Projeter l'écran d'accueil", "Ctrl+Shift+W"),
    ShortcutAction("quote", "Image de citation du direct", "Ctrl+Shift+I"),
    ShortcutAction("help", "Aide des raccourcis", "F1", "shortcut_help"),
)

# Touches réservées : la navigation par flèches, Échap et Ctrl+1..7 restent
# fixes (elles suivent les conventions de Windows et de PowerPoint).
RESERVED = {"Up", "Down", "Left", "Right", "Esc", "Escape", "Home", "End",
            *(f"Ctrl+{i}" for i in range(1, 8))}


def action(action_id: str) -> ShortcutAction | None:
    return next((a for a in ACTIONS if a.id == action_id), None)


@dataclass
class ShortcutSettings:
    """Raccourcis modifiés par l'opérateur (id → touche ; "" = désactivé)."""

    keys: dict[str, str] = field(default_factory=dict)

    def key_for(self, action_id: str) -> str:
        if action_id in self.keys:
            return str(self.keys[action_id] or "")
        found = action(action_id)
        return found.default if found else ""

    def effective(self) -> dict[str, str]:
        return {a.id: self.key_for(a.id) for a in ACTIONS}

    def conflicts(self) -> dict[str, list[str]]:
        """Touche utilisée par plusieurs actions (ou réservée) → actions."""
        by_key: dict[str, list[str]] = {}
        for action_id, key in self.effective().items():
            if key:
                by_key.setdefault(key.lower(), []).append(action_id)
        out = {k: v for k, v in by_key.items() if len(v) > 1}
        for action_id, key in self.effective().items():
            if key and key in RESERVED:
                out.setdefault(key.lower(), []).append(action_id)
        return out

    def sanitized(self) -> ShortcutSettings:
        known = {a.id for a in ACTIONS}
        keys = {
            str(k): str(v or "").strip()
            for k, v in (self.keys or {}).items()
            if str(k) in known
        }
        # Inutile de stocker une valeur identique au défaut.
        keys = {k: v for k, v in keys.items() if v != action(k).default}
        return ShortcutSettings(keys=keys)

    @classmethod
    def from_payload(cls, payload: Any) -> ShortcutSettings:
        keys = payload.get("keys") if isinstance(payload, dict) else None
        return cls(keys=dict(keys) if isinstance(keys, dict) else {}).sanitized()
