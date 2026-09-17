"""Politique de livraison : contrôles statiques fail-closed des scripts.

Aucun téléchargement, aucune exécution d'installeur, aucun réseau —
seulement la lecture des scripts pour verrouiller les garanties.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8-sig")


def test_ndi_setup_refuses_http_and_verifies_signature_before_running():
    script = _read("tools/setup_ndi_runtime.ps1")

    assert "https://ndi.link/NDIRedistV6" in script
    assert "Assert-HttpsUrl" in script
    assert "Refusing non-HTTPS download URL" in script

    download_index = script.index("Invoke-WebRequest")
    verify_index = script.index("Assert-AuthenticodeSignedByExpectedPublisher $tmp")
    run_index = script.index("Start-Process -FilePath $tmp")

    # Ordre imposé : vérification HTTPS -> téléchargement -> signature -> exécution.
    assert script.index("Assert-HttpsUrl $RedistUrl") < download_index
    assert download_index < verify_index < run_index
    assert "finally" in script  # le temporaire est supprimé même en échec


def test_sign_script_has_no_silent_fallback_from_explicit_thumbprint():
    script = _read("installer/sign.ps1")

    # Une empreinte définie mais introuvable doit être un échec, pas un repli.
    assert "return $null" in script
    assert "Certificat introuvable pour l'empreinte demandee" in script
    # Mode strict : empreinte obligatoire + statut de signature validé.
    assert "SIGN_THUMBPRINT est obligatoire" in script
    assert "Mode strict : statut de signature" in script
    # La signature résultante doit provenir de l'empreinte attendue.
    assert "au lieu de l'empreinte attendue" in script


def test_installer_build_blocks_on_signature_failure_in_strict_mode():
    script = _read("build_installer.bat")

    assert "SIGN_STRICT" in script
    assert "build interrompu" in script


def test_publish_requires_signed_installer_by_default():
    script = _read("tools/publish_github.ps1")

    assert "AllowUnsigned" in script
    assert "NOT Authenticode-signed" in script
    assert "unexpected certificate" in script
