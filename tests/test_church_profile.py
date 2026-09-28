"""Profil de l'église, écran d'accueil et images de citations."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.bible_tab import join_references
from app.utils.church_graphics import ChurchProfile, render_quote, render_welcome
from app.utils.settings import AppSettings

ROOT = Path(__file__).resolve().parents[1]


def test_profile_sanitized_and_round_trip(tmp_path: Path) -> None:
    profile = ChurchProfile.from_payload({"name": " Tabernacle ", "primary_color": "bleu"})
    assert profile.name == "Tabernacle"
    assert profile.primary_color == ChurchProfile().primary_color  # couleur invalide
    path = tmp_path / "s.json"
    settings = AppSettings()
    settings.church = ChurchProfile(name="Église", accent_color="#112233")
    settings.save(path)
    loaded = AppSettings.load(path).church
    assert loaded.name == "Église" and loaded.accent_color == "#112233"


def test_quote_formats_and_colors() -> None:
    profile = ChurchProfile(name="Église", primary_color="#102030",
                            logo=str(ROOT / "assets" / "logo" / "app icon.png"))
    for fmt, size in (("square", (1080, 1080)), ("story", (1080, 1920)),
                      ("landscape", (1920, 1080))):
        image = render_quote(profile, "Dieu est amour. " * 20, "1 Jean 4:8", fmt)
        assert image.size == size
    corner = render_quote(profile, "Court", "", "square").getpixel((2, 0))
    assert all(abs(a - b) <= 1 for a, b in zip(corner[:3], (16, 32, 48)))
    welcome = render_welcome(profile, 960, 540)
    assert welcome.size == (960, 540)


def test_join_references() -> None:
    assert join_references(["Jean 3:16"]) == "Jean 3:16"
    assert join_references(["Jean 3:16", "Jean 3:17", "Jean 3:18"]) == "Jean 3:16-18"
    assert join_references(["Jean 3:36", "Jean 4:1"]) == "Jean 3:36 – Jean 4:1"


def test_dialogs_and_welcome_projection(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.database.connection import Database, DatabaseConfig
    from app.ui.church_profile_dialog import ChurchProfileDialog, QuoteImageDialog
    from app.ui.main_window import MainWindow

    dialog = ChurchProfileDialog(ChurchProfile(name="Église test"))
    emitted = []
    dialog.profileChanged.connect(emitted.append)
    dialog.motto.setText("Christ est la lumière")
    dialog._emit()
    assert emitted[-1].motto == "Christ est la lumière"
    assert dialog.preview.pixmap() is not None
    dialog.close()

    quote = QuoteImageDialog(ChurchProfile(name="Église"), "Jean 3:16", "Car Dieu…")
    quote.format.setCurrentIndex(quote.format.findData("story"))
    assert quote.image().size == (1080, 1920)
    quote.close()

    monkeypatch.setattr(MainWindow, "_start_obs_output", lambda self: None)
    monkeypatch.setattr(MainWindow, "_poll_obs_status", lambda self: None)
    db = Database(DatabaseConfig(db_path=tmp_path / "m.db"))
    db.initialize()
    window = MainWindow(db=db)
    try:
        window._settings.church = ChurchProfile(name="Église test")
        window._project_welcome_screen()
        slide = json.loads((window._presentation_dir / "slide.json").read_text("utf-8"))
        assert slide["image"].endswith("accueil.png") and Path(slide["image"]).is_file()
        window._project_socials_screen()
        slide = json.loads((window._presentation_dir / "slide.json").read_text("utf-8"))
        assert slide["image"].endswith("reseaux-sociaux.png")
    finally:
        window.close()


# ── Réseaux sociaux et personnalisation ──────────────────────────────────


def test_socials_sanitized_and_links() -> None:
    from app.utils.church_graphics import display_handle, link_url

    profile = ChurchProfile.from_payload({
        "socials": {"facebook": " facebook.com/eglise ", "inconnu": "x", "youtube": ""},
        "qr_target": "youtube",  # compte vide : pas de QR code
        "background_dim": 300, "quote_style": "fantaisie",
    })
    assert profile.socials == {"facebook": "facebook.com/eglise"}
    assert profile.qr_target == ""
    assert profile.background_dim == 85 and profile.quote_style == "classic"
    assert [p.key for p, _v in profile.social_items()] == ["facebook"]

    assert link_url("youtube", "@Eglise") == "https://youtube.com/@Eglise"
    assert link_url("whatsapp", "+243 81 234 5678") == "https://wa.me/243812345678"
    assert link_url("facebook", "facebook.com/eglise") == "https://facebook.com/eglise"
    assert link_url("instagram", "@eglise") == "https://instagram.com/eglise"
    assert link_url("email", "a@b.org") == "mailto:a@b.org"
    assert link_url("website", "https://eglise.org") == "https://eglise.org"
    assert display_handle("website", "https://www.eglise.org/") == "eglise.org"


def test_socials_screen_and_qr_code(tmp_path: Path) -> None:
    from app.utils.church_graphics import qr_image, render_socials

    profile = ChurchProfile(
        name="Église",
        socials={"youtube": "@Eglise", "whatsapp": "+243 81 000 0000"},
        qr_target="youtube",
        background_mode="solid",
        primary_color="#224466",
    )
    image = render_socials(profile)
    assert image.size == (1920, 1080)
    assert image.getpixel((5, 5))[:3] == (34, 68, 102)  # couleur unie
    qr = qr_image("https://youtube.com/@Eglise", 200)
    assert qr is not None and qr.size == (200, 200)
    # Le QR code est bien présent : pixels noirs dans la zone de droite.
    right = image.crop((1300, 300, 1860, 900)).convert("L")
    assert right.getextrema()[0] < 40


def test_background_image_is_dimmed(tmp_path: Path) -> None:
    from PIL import Image

    photo = tmp_path / "fond.png"
    Image.new("RGB", (400, 300), (200, 200, 200)).save(photo)
    profile = ChurchProfile(background_mode="image", background_image=str(photo),
                            background_dim=50)
    pixel = render_welcome(profile, 640, 360).getpixel((3, 3))
    assert 90 <= pixel[0] <= 110  # 200 assombri de moitié


def test_profile_dialog_reads_socials_and_exports(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.church_profile_dialog import ChurchProfileDialog, export_visuals

    dialog = ChurchProfileDialog(ChurchProfile(name="Église", socials={"facebook": "fb.com/e"}))
    try:
        dialog.social_edits["youtube"].setText("@Eglise")
        dialog.qr_target.setCurrentIndex(dialog.qr_target.findData("youtube"))
        dialog.service_times.setPlainText("Dimanche 9h30")
        dialog.quote_style.setCurrentIndex(dialog.quote_style.findData("framed"))
        profile = dialog.read_profile()
        assert profile.socials == {"facebook": "fb.com/e", "youtube": "@Eglise"}
        assert profile.qr_target == "youtube" and profile.quote_style == "framed"
        assert profile.service_times == "Dimanche 9h30"
        for index in range(dialog.preview_kind.count()):
            dialog.preview_kind.setCurrentIndex(index)
            assert dialog.preview.pixmap() is not None
        written = export_visuals(profile, tmp_path / "visuels")
        assert [p.name for p in written] == [
            "accueil.png", "reseaux-sociaux.png", "reseaux-sociaux-carre.png"
        ]
    finally:
        dialog.close()


def test_profile_socials_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    settings = AppSettings()
    settings.church = ChurchProfile(socials={"tiktok": "@eglise"}, qr_target="tiktok",
                                    service_times="Dimanche")
    settings.save(path)
    loaded = AppSettings.load(path).church
    assert loaded.socials == {"tiktok": "@eglise"} and loaded.qr_target == "tiktok"
