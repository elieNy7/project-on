"""Miniature YouTube (1280×720) aux couleurs de l'église."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

from app.utils.church_graphics import (
    THUMBNAIL_MAX_BYTES,
    ChurchProfile,
    ThumbnailSpec,
    _highlight_words,
    render_youtube_thumbnail,
    save_thumbnail,
)

RED = (200, 30, 40)


def _cutout(path: Path) -> Path:
    image = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 20, 200, 120), fill=(*RED, 255))
    draw.rectangle((60, 130, 240, 400), fill=(*RED, 255))
    image.save(path)
    return path


def _profile(tmp_path: Path) -> ChurchProfile:
    return ChurchProfile(name="Église La Grâce", pastor_title="Pasteur", pastor_name="Elie",
                         pastor_photo=str(_cutout(tmp_path / "p.png")),
                         accent_color="#F0BE64")


def test_highlighted_words() -> None:
    assert _highlight_words("Le *vrai* repos") == [("Le", False), ("vrai", True), ("repos", False)]
    assert _highlight_words("*Jésus revient*") == [("Jésus", True), ("revient", True)]


def test_thumbnail_size_speaker_side_and_accent(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    spec = ThumbnailSpec(title="Le *vrai* repos", date="28 septembre")
    image = render_youtube_thumbnail(profile, spec)
    assert image.size == (1280, 720)

    def red_columns(img):
        rgb = img.convert("RGB")
        return [x for x in range(0, 1280, 8)
                if any(rgb.getpixel((x, y)) == RED for y in range(400, 720, 8))]

    right = red_columns(image)
    assert right and min(right) > 640  # orateur à droite
    left = red_columns(render_youtube_thumbnail(profile, ThumbnailSpec(title="Foi",
                                                                        photo_side="left")))
    assert left and max(left) < 640
    # Mot entre astérisques : couleur d'accent présente dans la zone du titre.
    title_zone = image.convert("RGB").crop((40, 180, 700, 560))
    assert (240, 190, 100) in set(title_zone.get_flattened_data() if hasattr(title_zone, "get_flattened_data") else title_zone.getdata())
    # Sans orateur : pas de photo.
    alone = render_youtube_thumbnail(profile, ThumbnailSpec(title="Foi", show_speaker=False))
    assert not red_columns(alone)


def test_background_image_and_save_under_youtube_limit(tmp_path: Path) -> None:
    noise = Image.effect_noise((1600, 900), 120).convert("RGB")  # image difficile à compresser
    noise.save(tmp_path / "fond.png")
    spec = ThumbnailSpec(title="Marcher par la foi", background=str(tmp_path / "fond.png"))
    image = render_youtube_thumbnail(_profile(tmp_path), spec)
    written = save_thumbnail(image, tmp_path / "mini.png")
    assert written.stat().st_size <= THUMBNAIL_MAX_BYTES
    assert Image.open(written).size == (1280, 720)


def test_thumbnail_dialog_and_shortcut(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.church_profile_dialog import ThumbnailDialog, french_date
    from app.utils.shortcuts import ShortcutSettings

    assert french_date(date(2026, 9, 27)) == "Dimanche 27 septembre 2026"
    assert ShortcutSettings().key_for("thumbnail") == "Ctrl+Shift+Y"
    dialog = ThumbnailDialog(_profile(tmp_path), title="Le *vrai* repos")
    try:
        spec = dialog.spec()
        assert spec.title == "Le *vrai* repos" and spec.label == "Culte du dimanche"
        dialog.side.setCurrentIndex(1)
        assert dialog.spec().photo_side == "left"
        assert dialog.image().size == (1280, 720)
    finally:
        dialog.close()


def test_all_layouts_render(tmp_path: Path) -> None:
    from app.utils.church_graphics import BUILTIN_THUMBNAIL_MODELS, THUMBNAIL_LAYOUTS

    profile = _profile(tmp_path)
    assert {m["layout"] for m in BUILTIN_THUMBNAIL_MODELS} == set(THUMBNAIL_LAYOUTS)
    for model in BUILTIN_THUMBNAIL_MODELS:
        spec = ThumbnailSpec(title="Le *vrai* repos de l'âme", date="Dimanche",
                             reference="Mt 11:28").with_model(model)
        assert render_youtube_thumbnail(profile, spec).size == (1280, 720)
    # Couleur d'accent propre au modèle.
    spec = ThumbnailSpec(title="*Foi*", accent="#FF0000", show_speaker=False, layout="center")
    image = render_youtube_thumbnail(profile, spec).convert("RGB")
    assert (255, 0, 0) in list(image.crop((300, 200, 980, 560)).get_flattened_data() if hasattr(image, "get_flattened_data") else image.crop((300, 200, 980, 560)).getdata())


def test_models_keep_design_not_sermon_text() -> None:
    from app.utils.church_graphics import sanitize_thumbnail_models

    spec = ThumbnailSpec(title="Titre", date="Hier", reference="Jn 3:16", layout="band",
                         label="En direct", accent="rgb(10, 20, 30)", photo_side="left")
    model = spec.model("Mon direct")
    assert model["name"] == "Mon direct" and "title" not in model and "date" not in model
    assert model["accent"] == "#0A141E"
    applied = ThumbnailSpec(title="Nouveau", date="Dimanche").with_model(model)
    assert (applied.title, applied.date, applied.layout, applied.photo_side) == (
        "Nouveau", "Dimanche", "band", "left")
    cleaned = sanitize_thumbnail_models(
        [model, {**model, "name": "mon DIRECT"}, {"name": ""}, "x", {"name": "B", "layout": "?"}])
    assert [m["name"] for m in cleaned] == ["Mon direct", "B"]
    assert cleaned[1]["layout"] == "split"


def test_models_saved_in_settings(tmp_path: Path) -> None:
    from app.utils.settings import AppSettings

    settings = AppSettings()
    settings.thumbnail_models = [ThumbnailSpec(layout="boxed").model("Prière du soir")]
    settings.save(tmp_path / "settings.json")
    loaded = AppSettings.load(tmp_path / "settings.json")
    assert loaded.thumbnail_models[0]["name"] == "Prière du soir"
    assert loaded.thumbnail_models[0]["layout"] == "boxed"


def test_dialog_saves_applies_and_deletes_models(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

    QApplication.instance() or QApplication([])
    from app.ui.church_profile_dialog import ThumbnailDialog

    sources = []
    for index, color in enumerate(((10, 90, 200), (200, 120, 30), (40, 160, 80))):
        path = tmp_path / f"culte-{index}.png"
        Image.new("RGB", (160, 90), color).save(path)
        sources.append(str(path))
    photos_folder = tmp_path / "photos"
    dialog = ThumbnailDialog(_profile(tmp_path), title="Foi", photos_folder=photos_folder)
    emitted: list = []
    gallery_changes: list = []
    dialog.modelsChanged.connect(emitted.append)
    dialog.photosChanged.connect(gallery_changes.append)
    try:
        # Photos ajoutées depuis la miniature : copiées et renvoyées au profil.
        dialog.gallery.add_photos(sources)
        copied = gallery_changes[-1]
        assert len(copied) == 3 and all(Path(p).parent == photos_folder for p in copied)
        dialog.gallery.set_checked(copied[:2])
        assert dialog.spec().photos == copied[:2]

        dialog.layout_combo.setCurrentIndex(dialog.layout_combo.findData("band"))
        dialog.composition.setCurrentIndex(dialog.composition.findData("photo"))
        dialog.label.setCurrentText("Veillée")
        dialog.darkness.setValue(40)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Veillée du vendredi", True))
        dialog._save_model()
        saved = emitted[-1][0]
        assert (saved["name"], saved["layout"], saved["composition"], saved["darkness"]) == (
            "Veillée du vendredi", "band", "photo", 40)
        assert saved["photos"] == copied[:2]

        # Revenir à un modèle fourni puis réappliquer celui de l'église.
        dialog.model.setCurrentIndex(0)
        dialog._apply_selected_model()
        assert dialog.spec().layout == "split" and dialog.spec().title == "Foi"
        assert dialog.spec().photos == []  # modèle fourni : toutes les photos
        dialog.model.setCurrentIndex(dialog.model.findData("church:Veillée du vendredi"))
        dialog._apply_selected_model()
        spec = dialog.spec()
        assert (spec.layout, spec.label, spec.composition) == ("band", "Veillée", "photo")
        assert spec.photos == copied[:2]
        assert dialog.delete_model_btn.isEnabled()
        assert dialog.model.currentText() == "★ Veillée du vendredi"

        monkeypatch.setattr(QMessageBox, "question",
                            lambda *a, **k: QMessageBox.StandardButton.Yes)
        dialog._delete_model()
        assert emitted[-1] == []
    finally:
        dialog.close()

    # Réouverture : le dernier modèle de l'église est présélectionné.
    reopened = ThumbnailDialog(_profile(tmp_path), models=[saved])
    try:
        assert reopened.spec().layout == "band"
    finally:
        reopened.close()


def _photo(path: Path, color) -> str:
    Image.new("RGB", (320, 180), color).save(path)
    return str(path)


def test_background_is_composed_of_church_photos(tmp_path: Path) -> None:
    from app.utils.church_graphics import thumbnail_background

    photos = [_photo(tmp_path / "a.png", (230, 40, 40)), _photo(tmp_path / "b.png", (40, 200, 60)),
              _photo(tmp_path / "c.png", (40, 60, 230))]
    profile = ChurchProfile(photos=photos, accent_color="#FFFFFF")
    plain = ThumbnailSpec(tint=False, blur=False, darkness=0)

    # Mosaïque : une photo par panneau (rouge, vert, bleu de gauche à droite).
    mosaic = thumbnail_background(profile, plain, 1280, 720).convert("RGB")
    left, middle, right = (mosaic.getpixel((x, 360)) for x in (200, 640, 1080))
    assert left[0] > 150 and middle[1] > 150 and right[2] > 150
    # Séparation couleur d'accent entre deux panneaux (inclinée).
    assert (255, 255, 255) in {mosaic.getpixel((x, 360)) for x in range(400, 480)}

    # Une photo : la première choisie remplit le cadre.
    single = thumbnail_background(
        profile, ThumbnailSpec(composition="photo", photos=[photos[1]], tint=False, blur=False,
                               darkness=0), 1280, 720).convert("RGB")
    assert single.getpixel((640, 360))[1] > 150 and single.getpixel((1000, 360))[1] > 150

    # Teinte de l'église et assombrissement changent l'image.
    graded = thumbnail_background(profile, ThumbnailSpec(composition="photo", darkness=60),
                                  1280, 720).convert("RGB")
    assert sum(graded.getpixel((640, 360))) < sum(single.getpixel((640, 360)))

    # Fond uni, ou pas de photos : fond de l'église.
    for spec, prof in ((ThumbnailSpec(composition="plain"), profile),
                       (ThumbnailSpec(), ChurchProfile(primary_color="#102030"))):
        image = thumbnail_background(prof, spec, 1280, 720).convert("RGB")
        r, g, b = image.getpixel((640, 360))
        assert max(r, g, b) < 120


def test_profile_keeps_photos(tmp_path: Path) -> None:
    photos = [_photo(tmp_path / "a.png", (1, 2, 3))]
    profile = ChurchProfile.from_payload({"photos": photos + photos + ["", 5]})
    assert profile.photos == photos + ["5"]
    assert ChurchProfile.from_payload({"photos": "x"}).photos == []


def test_church_dialog_gallery(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from app.ui.church_profile_dialog import ChurchProfileDialog

    dialog = ChurchProfileDialog(ChurchProfile(), logo_folder=tmp_path / "church")
    changes: list = []
    dialog.profileChanged.connect(changes.append)
    try:
        dialog.gallery.add_photos([_photo(tmp_path / "culte.png", (9, 9, 9))])
        assert changes and Path(changes[-1].photos[0]).parent == tmp_path / "church" / "photos"
        dialog.set_gallery_photos([])
        assert dialog.read_profile().photos == []
    finally:
        dialog.close()
