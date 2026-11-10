"""Les références des playlists de la 2.8 (phase 4, comparées par `po-parite playlist`).

Sur une COPIE de la base, le vrai code de la 2.8 crée des playlists : paragraphes de sermons,
versets, strophes, paragraphes de l'Exposé, slides saisis (dont des vides), médias, et d'anciens
éléments « custom » dont le genre se devine. Puis, pour plusieurs slides de départ, il prépare le
programme de la playlist (`LibraryController.on_playlist_play`) et note le genre de chaque élément
(`item_kind`). Les fonctions sont appelées telles quelles, sans fenêtre : un simple espace de noms
leur tient lieu de `self`.

    py -3.14 outils/references_playlist_28.py <copie de project_on.db> <dossier de sortie>

Le dossier de sortie reçoit `playlist-28.db` (la copie où les playlists ont été écrites) et
`playlist.json`.
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.database.dao_playlist import PlaylistDao  # noqa: E402
from app.ui.playlist_tab import item_kind  # noqa: E402
from app.utils.library_controller import LibraryController as LC  # noqa: E402


def copy_database(source: Path, target: Path) -> None:
    if target.exists():
        target.unlink()
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    src.backup(dst)
    dst.close()
    src.close()


def play(dao: PlaylistDao, folder_id: int, item_id) -> dict | None:
    """`on_playlist_play` de la 2.8, le programme capturé au lieu d'être projeté."""
    captured = []
    me = SimpleNamespace(_current_playlist_folder_id=folder_id, _playlist_dao=dao)
    me._clean_text = LC._clean_text
    me._entries = lambda pairs: LC._entries(me, pairs)
    me._channel = lambda target: target
    me._deliver = lambda target, cue: captured.append(cue)
    me._submit_latest = lambda channel, fetch, done: done(fetch())
    LC.on_playlist_play(me, item_id)
    if not captured:
        return None
    cue = captured[0]
    return {
        "titre": cue.title,
        "entrees": [list(e) for e in cue.entries],
        "focus": cue.focus_entry,
        "visuels": list(cue.entry_visuals or ()),
    }


def main() -> None:
    source, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    target = out / "playlist-28.db"
    copy_database(source, target)
    db = Database(DatabaseConfig(db_path=target))
    dao = PlaylistDao(db)
    rng = random.Random(28)
    ro = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)

    def rows(sql: str, n: int) -> list:
        found = ro.execute(sql).fetchall()
        return rng.sample(found, min(n, len(found)))

    paragraphs = rows(
        "SELECT s.date || ' - ' || COALESCE(NULLIF(s.canonical_title, ''), s.title) || ' - ' || COALESCE(p.marker, ''), p.text "
        "FROM sermon_paragraph p JOIN sermon s ON s.id = p.sermon_id WHERE p.id % 997 = 3", 40)
    verses = rows(
        "SELECT b.name || ' ' || v.chapter || ':' || v.verse, v.text FROM bible_translation_verse v "
        "JOIN (SELECT DISTINCT translation_id, book, book_name AS name FROM bible_translation_verse) b "
        "ON b.translation_id = v.translation_id AND b.book = v.book WHERE v.id % 1499 = 5", 30)
    stanzas = rows(
        "SELECT COALESCE(h.number, '') || ' - ' || h.title || ' - Strophe ' || hs.stanza_no, hs.text "
        "FROM hymn_stanza hs JOIN hymn h ON h.id = hs.hymn_id WHERE hs.id % 53 = 1", 30)
    expose = rows(
        "SELECT 'Exposé des Sept Âges — ' || COALESCE(NULLIF(s.canonical_title, ''), s.title) || ' · Page 3 §' || p.paragraph_no, p.text "
        "FROM sermon_paragraph p JOIN sermon s ON s.id = p.sermon_id WHERE s.date LIKE 'BK-AGES%' AND p.id % 37 = 2", 20)
    custom = [
        ("Annonces", "Réunion de prière mercredi à 18 h."),
        ("Vide", "   "),
        ("", "Un slide sans référence."),
        ("Bienvenue", "Bienvenue à tous !\nQue Dieu vous bénisse."),
    ]
    # D'anciens éléments « custom » : le genre se devine d'après la référence.
    legacy = [(r, t) for r, t in paragraphs[:5] + verses[:5] + stanzas[:5] + expose[:3]]

    folders = {}
    folders["Sermons"] = [("sermon", r, t) for r, t in paragraphs[:20]]
    folders["Bible"] = [("bible", r, t) for r, t in verses[:20]]
    folders["Cantiques"] = [("hymn", r, t) for r, t in stanzas[:20]]
    folders["Exposé"] = [("expose", r, t) for r, t in expose[:15]]
    folders["Culte complet"] = (
        [("bible", r, t) for r, t in verses[20:25]]
        + [("custom", r, t) for r, t in custom]
        + [("hymn", r, t) for r, t in stanzas[20:24]]
        + [("sermon", r, t) for r, t in paragraphs[20:30]]
    )
    folders["Anciens éléments"] = [("custom", r, t) for r, t in legacy]

    cases = []
    for name, items in folders.items():
        folder = dao.create_folder(name)
        dao.add_items(items, folder_id=folder)
        listed = dao.list_items(folder)
        if name == "Culte complet":
            # Des médias : une image et une vidéo (projetés en phase 7 dans la 3.0).
            for path in ("C:/medias/affiche.png", "C:/medias/clip.mp4"):
                dao.add_item("media", Path(path).stem, "", folder_id=folder)
                with db.connect() as conn:
                    conn.execute("UPDATE playlist_item SET background = ? WHERE id = (SELECT MAX(id) FROM playlist_item)", (path,))
            listed = dao.list_items(folder)
        ids = [int(i["id"]) for i in listed]
        starts = [None, ids[0], ids[len(ids) // 2], ids[-1], 999_999_999]
        for start in starts:
            cases.append({"dossier": folder, "nom": name, "depart": start, "programme": play(dao, folder, start)})
        kinds = {
            str(i["id"]): item_kind(str(i.get("source") or ""), str(i.get("reference") or ""), str(i.get("background") or ""))
            for i in listed
        }
        cases[-1]["genres"] = kinds
    ro.close()
    (out / "playlist.json").write_text(json.dumps({"base": str(target), "cas": cases}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(folders)} playlists, {len(cases)} programmes")


if __name__ == "__main__":
    main()
