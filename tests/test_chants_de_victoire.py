"""Analyse du recueil Chants de Victoire (lignes synthétiques, sans le PDF)."""

from __future__ import annotations

from tools.import_chants_de_victoire import _Builder, _clean


def _build(lines: list[tuple[str, float, str]]) -> list:
    """lines : (rôle, retrait, texte) avec rôle = n(uméro), t(itre) ou b(ody)."""
    builder = _Builder()
    for role, indent, text in lines:
        if role == "n":
            builder.start_hymn(text)
        elif role == "t":
            builder.add_title(text)
        else:
            builder.add_body(indent, text)
    builder.flush()
    return builder.hymns


def test_repeat_markers_become_bis_and_ter() -> None:
    assert _clean(r"\lrep Nous t’adorons, ô grand Roi ! \rrep \rep{2}") == "Nous t’adorons, ô grand Roi ! (bis)"
    assert _clean(r"\lrep Gloire à Toi, \rrep \rep{3} – gloire à") == "Gloire à Toi, (ter) – gloire à"


def test_stanzas_refrain_and_refrain_reminder() -> None:
    hymns = _build([
        ("n", 0, "11"), ("t", 0, "Adorable mystère"),
        ("b", 0, "1. Adorable mystère,"), ("b", 11, "Le Fils du Roi des rois,"),
        ("b", 6, "Honneur, honneur et gloire"), ("b", 6, "Au Sauveur, au Seigneur !"),
        ("b", 0, "2. Adorable mystère,"), ("b", 11, "C’est pour moi qu’il mourut !"),
        ("b", 11, "« Honneur, honneur et gloire, etc. »"),
    ])
    (hymn,) = hymns
    assert hymn.number == "CV-011"
    assert hymn.title == "Adorable mystère"
    assert [(s.label, s.is_chorus) for s in hymn.sections] == [
        ("Strophe 1", False), ("Refrain", True), ("Strophe 2", False), ("Refrain", True),
    ]
    assert hymn.sections[0].text == "Adorable mystère,\nLe Fils du Roi des rois,"
    assert hymn.sections[3].text == "Choeur:\nHonneur, honneur et gloire\nAu Sauveur, au Seigneur !"


def test_wrapped_line_title_on_two_lines_and_variant_number() -> None:
    hymns = _build([
        ("n", 0, "25b"), ("t", 0, "Bénissons Dieu par nos"), ("t", 0, "cantiques"),
        ("b", 0, "Rien, ô Jésus ! que ta grâce,"),
        ("b", 11, "Le Seigneur est pour nous : contre nous qui"), ("b", 29, "sera ?"),
    ])
    (hymn,) = hymns
    assert hymn.number == "CV-025B"
    assert hymn.title == "Bénissons Dieu par nos cantiques"
    # Chant d'une seule strophe, sans « 1. » : c'est la strophe 1.
    assert [s.label for s in hymn.sections] == ["Strophe 1"]
    assert hymn.sections[0].text.endswith("contre nous qui sera ?")
