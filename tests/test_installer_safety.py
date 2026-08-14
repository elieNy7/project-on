from __future__ import annotations

from pathlib import Path

from app.version import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _section(script: str, name: str) -> str:
    marker = f"[{name}]"
    start = script.index(marker) + len(marker)
    end = script.find("\n[", start)
    return script[start:] if end < 0 else script[start:end]


def test_upgrade_preserves_user_database_and_settings() -> None:
    script = (PROJECT_ROOT / "installer" / "setup.iss").read_text(encoding="utf-8")
    install_delete = _section(script, "InstallDelete")

    assert "{userappdata}" not in install_delete.lower()
    assert "{localappdata}" not in install_delete.lower()
    assert "UninstallOldVersion" not in script
    assert "function InitializeSetup" not in script


def test_uninstall_does_not_silently_delete_user_data() -> None:
    script = (PROJECT_ROOT / "installer" / "setup.iss").read_text(encoding="utf-8")

    if "[UninstallDelete]" in script:
        uninstall_delete = _section(script, "UninstallDelete")
        assert "{userappdata}" not in uninstall_delete.lower()
        assert "{localappdata}" not in uninstall_delete.lower()


def test_release_version_is_consistent_across_product_surfaces() -> None:
    installer = (PROJECT_ROOT / "installer" / "setup.iss").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    site = (PROJECT_ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    release_notes = (PROJECT_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    assert f'#define MyAppVersion "{__version__}"' in installer
    assert f"ProjectOn_{__version__}_Setup.exe" in readme
    assert f"/v{__version__}/ProjectOn_{__version__}_Setup.exe" in site
    assert release_notes.startswith(f"# Project-On {__version__}\n")
