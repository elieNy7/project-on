"""Fixtures partagées pour les tests de Project-On.

Isolation systématique : aucun test ne doit écrire dans le profil réel
(APPDATA\\Project-On) ni dans data/ ou presentation/ du dépôt. Les fonctions
de app.utils.app_paths qui produisent des chemins *inscriptibles* sont
redirigées vers un répertoire temporaire par une fixture autouse.

Les fonctions de *lecture* de ressources (resource_root, project_root,
app_root, bible_json_dir, assets_dir, is_frozen) ne sont PAS patchées : les
tests continuent de lire les ressources du dépôt, et les tests qui simulent
explicitement frozen/project_root/app_paths ne sont pas cassés.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.database.connection import Database, DatabaseConfig
from app.utils import app_paths as _app_paths


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Base de données SQLite temporaire initialisée avec le schéma complet."""
    db_path = tmp_path / "test_project_on.db"
    database = Database(DatabaseConfig(db_path=db_path))
    database.initialize()
    return database


# Fonctions « inscriptibles » de app_paths à rediriger vers tmp_path.
# Les fonctions dérivées (logs_dir, settings_path, app_db_path,
# sermons_vgr_db_path) appellent data_dir() dynamiquement : elles suivent
# automatiquement le patch. backgrounds_dir/media_dir suivent user_data_dir.
_WRITABLE_FUNCS = (
    "user_data_dir",
    "data_dir",
    "ensure_presentation_workdir",
    "ensure_data_initialized",
    "backgrounds_dir",
    "media_dir",
)

_ORIGINALS = {name: getattr(_app_paths, name) for name in _WRITABLE_FUNCS}


def _rebind_aliases(monkeypatch: pytest.MonkeyPatch, patched: dict) -> None:
    """Rebind les alias déjà importés dans les modules chargés.

    Les modules de production importent parfois les fonctions par nom
    (``from app.utils.app_paths import data_dir``). Pour chaque module déjà
    présent dans sys.modules, toute référence identique (même objet) à une
    fonction originale est remplacée par la version patchée, quel que soit le
    nom local de l'alias.
    """
    original_to_patched = {
        id(_ORIGINALS[name]): patched[name] for name in _WRITABLE_FUNCS
    }
    for module in list(sys.modules.values()):
        if module is _app_paths or module is None:
            continue
        ns = getattr(module, "__dict__", None)
        if not ns:
            continue
        for attr, value in list(ns.items()):
            replacement = original_to_patched.get(id(value))
            if replacement is not None:
                monkeypatch.setattr(module, attr, replacement, raising=False)


@pytest.fixture(autouse=True)
def isolate_user_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isole chaque test du profil réel et des répertoires inscriptibles du dépôt."""
    sandbox = tmp_path / "sandbox"
    user_data = sandbox / "user-data"
    data = sandbox / "data"
    presentation = sandbox / "presentation"
    for d in (user_data, data, presentation):
        d.mkdir(parents=True)

    # Filet de sécurité : toute lecture directe de %APPDATA% tombe dans le bac
    # à sable (user_data_dir() lit APPDATA ; le registre est ignoré car la
    # fonction est patchée, mais d'autres codes pourraient construire le chemin).
    monkeypatch.setenv("APPDATA", str(user_data.parent))
    monkeypatch.setenv("LOCALAPPDATA", str(user_data.parent))

    patched = {
        "user_data_dir": lambda: user_data,
        "data_dir": lambda: data,
        "ensure_presentation_workdir": lambda: presentation,
        "ensure_data_initialized": lambda: None,
        "backgrounds_dir": lambda: _ensure_dir(user_data / "backgrounds"),
        "media_dir": lambda: _ensure_dir(user_data / "media"),
    }
    for name, replacement in patched.items():
        monkeypatch.setattr(_app_paths, name, replacement)

    _rebind_aliases(monkeypatch, patched)
    yield


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
