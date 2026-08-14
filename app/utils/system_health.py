from __future__ import annotations

import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.version import __version__


HealthStatus = Literal["success", "warning", "error"]


@dataclass(frozen=True)
class HealthCheck:
    key: str
    title: str
    status: HealthStatus
    detail: str


@dataclass(frozen=True)
class HealthReport:
    checks: tuple[HealthCheck, ...]
    generated_at: datetime

    @property
    def errors(self) -> int:
        return sum(check.status == "error" for check in self.checks)

    @property
    def warnings(self) -> int:
        return sum(check.status == "warning" for check in self.checks)

    @property
    def overall_status(self) -> HealthStatus:
        if self.errors:
            return "error"
        if self.warnings:
            return "warning"
        return "success"

    def to_text(self) -> str:
        labels = {"success": "OK", "warning": "ATTENTION", "error": "ERREUR"}
        lines = [
            f"Project-On {__version__} - Rapport de contrôle avant service",
            f"Généré le {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Résumé : {self.errors} erreur(s), {self.warnings} avertissement(s)",
            "",
        ]
        for check in self.checks:
            lines.append(f"[{labels[check.status]}] {check.title}")
            lines.append(f"    {check.detail}")
        return "\n".join(lines) + "\n"


def _format_size(value: int) -> str:
    size = float(max(0, value))
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if size < 1024 or unit == "To":
            return f"{size:.1f} {unit}" if unit != "o" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} To"


def _database_checks(database_path: Path) -> list[HealthCheck]:
    if not database_path.is_file():
        return [
            HealthCheck(
                "database",
                "Base de données",
                "error",
                f"Fichier introuvable : {database_path}",
            )
        ]

    checks: list[HealthCheck] = []
    try:
        with closing(
            sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        ) as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
            integrity = str(row[0]) if row else "Aucun résultat"
            status: HealthStatus = "success" if integrity.lower() == "ok" else "error"
            checks.append(
                HealthCheck(
                    "database",
                    "Intégrité des données",
                    status,
                    f"SQLite : {integrity} · {_format_size(database_path.stat().st_size)}",
                )
            )

            tables = {
                str(name)
                for (name,) in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            content_specs = (
                ("bible_translation_verse", "versets"),
                ("hymn", "cantiques"),
                ("sermon", "prédications"),
                ("playlist_item", "éléments de playlist"),
            )
            counts: list[str] = []
            for table, label in content_specs:
                if table in tables:
                    count = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                    counts.append(f"{count:,} {label}".replace(",", " "))

            if counts:
                checks.append(
                    HealthCheck(
                        "content",
                        "Bibliothèque disponible",
                        "success",
                        " · ".join(counts),
                    )
                )
            else:
                checks.append(
                    HealthCheck(
                        "content",
                        "Bibliothèque disponible",
                        "warning",
                        "Aucune table de contenu reconnue.",
                    )
                )
    except sqlite3.Error as exc:
        checks.append(
            HealthCheck("database", "Base de données", "error", str(exc))
        )
    return checks


def run_system_health(
    *,
    database_path: Path,
    data_directory: Path,
    presentation_directory: Path,
    screen_count: int,
    obs_mode: str,
    obs_port: int,
    ndi_runtime_path: Path | None = None,
) -> HealthReport:
    """Run the operator preflight without changing application content."""
    checks = _database_checks(Path(database_path))

    data_path = Path(data_directory)
    try:
        data_path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="project-on-check-", dir=data_path, delete=True):
            pass
        checks.append(
            HealthCheck(
                "storage",
                "Stockage utilisateur",
                "success",
                "Le dossier des données est accessible en lecture et écriture.",
            )
        )
    except OSError as exc:
        checks.append(HealthCheck("storage", "Stockage utilisateur", "error", str(exc)))

    try:
        free_bytes = shutil.disk_usage(data_path).free
        disk_status: HealthStatus = "success" if free_bytes >= 1024**3 else "warning"
        disk_detail = f"{_format_size(free_bytes)} libres"
        if disk_status == "warning":
            disk_detail += " · au moins 1 Go est recommandé"
        checks.append(HealthCheck("disk", "Espace disque", disk_status, disk_detail))
    except OSError as exc:
        checks.append(HealthCheck("disk", "Espace disque", "warning", str(exc)))

    required_assets = ("index.html", "script.js", "obs.html", "obs-script.js")
    missing_assets = [
        name for name in required_assets if not (Path(presentation_directory) / name).is_file()
    ]
    checks.append(
        HealthCheck(
            "presentation",
            "Moteur de projection",
            "error" if missing_assets else "success",
            (
                "Fichiers manquants : " + ", ".join(missing_assets)
                if missing_assets
                else "Projection locale et sortie OBS prêtes."
            ),
        )
    )

    normalized_screen_count = max(0, int(screen_count))
    checks.append(
        HealthCheck(
            "screens",
            "Écrans détectés",
            "success" if normalized_screen_count >= 2 else "warning",
            (
                f"{normalized_screen_count} écrans détectés · sortie dédiée disponible."
                if normalized_screen_count >= 2
                else "Un seul écran détecté · connectez le projecteur avant le service."
            ),
        )
    )

    if str(obs_mode).lower() == "ndi":
        ndi_ready = bool(ndi_runtime_path and Path(ndi_runtime_path).is_file())
        checks.append(
            HealthCheck(
                "obs",
                "Sortie OBS / NDI",
                "success" if ndi_ready else "error",
                (
                    "Runtime NDI détecté."
                    if ndi_ready
                    else "Runtime NDI introuvable · passez en mode Web ou réinstallez Project-On."
                ),
            )
        )
    else:
        valid_port = 1024 <= int(obs_port) <= 65535
        checks.append(
            HealthCheck(
                "obs",
                "Sortie OBS Web",
                "success" if valid_port else "error",
                (
                    f"Source navigateur locale configurée sur le port {int(obs_port)}."
                    if valid_port
                    else f"Port invalide : {obs_port}. Utilisez une valeur entre 1024 et 65535."
                ),
            )
        )

    return HealthReport(tuple(checks), datetime.now())
