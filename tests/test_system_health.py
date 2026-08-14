from __future__ import annotations

from pathlib import Path

from app.database.connection import Database
from app.utils.system_health import run_system_health


def _presentation_assets(directory: Path) -> None:
    directory.mkdir(parents=True)
    for name in ("index.html", "script.js", "obs.html", "obs-script.js"):
        (directory / name).write_text("ok", encoding="utf-8")


def test_system_health_reports_ready_environment(db: Database, tmp_path: Path) -> None:
    presentation = tmp_path / "presentation"
    data = tmp_path / "data"
    _presentation_assets(presentation)

    report = run_system_health(
        database_path=db.db_path,
        data_directory=data,
        presentation_directory=presentation,
        screen_count=2,
        obs_mode="web",
        obs_port=8080,
    )

    assert report.overall_status == "success"
    assert report.errors == 0
    assert report.warnings == 0
    assert {check.key for check in report.checks} >= {
        "database",
        "content",
        "storage",
        "disk",
        "presentation",
        "screens",
        "obs",
    }
    assert "Project-On" in report.to_text()


def test_system_health_flags_operator_blockers(db: Database, tmp_path: Path) -> None:
    presentation = tmp_path / "presentation"
    presentation.mkdir()

    report = run_system_health(
        database_path=db.db_path,
        data_directory=tmp_path / "data",
        presentation_directory=presentation,
        screen_count=1,
        obs_mode="web",
        obs_port=80,
    )

    assert report.overall_status == "error"
    assert report.errors >= 2
    assert report.warnings >= 1
    by_key = {check.key: check for check in report.checks}
    assert by_key["presentation"].status == "error"
    assert by_key["screens"].status == "warning"
    assert by_key["obs"].status == "error"
