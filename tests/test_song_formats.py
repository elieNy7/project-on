"""Import OpenLyrics, OpenSong et CCLI SongSelect."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.song_formats import read_song_file

OPENLYRICS = """<?xml version='1.0' encoding='UTF-8'?>
<song xmlns="http://openlyrics.info/namespace/2009/song" version="0.8">
  <properties>
    <titles><title>À toi la gloire</title></titles>
    <songbooks><songbook name="Chants" entry="33"/></songbooks>
    <verseOrder>v1 c1 v2 c1</verseOrder>
  </properties>
  <lyrics>
    <verse name="v1"><lines>À toi la gloire<br/>Ô Ressuscité</lines></verse>
    <verse name="c1"><lines>Gloire à toi<br/>Alléluia</lines></verse>
    <verse name="v2"><lines><comment>doux</comment>Vois-le paraître<br/>C'est Jésus</lines></verse>
  </lyrics>
</song>
"""

OPENSONG = """<?xml version="1.0" encoding="UTF-8"?>
<song>
  <title>Grâce infinie</title>
  <hymn_number>12</hymn_number>
  <presentation>V1 C V2</presentation>
  <lyrics>[V1]
.G       C
 Grâce infinie
 Que Dieu m'a faite
;commentaire
[C]
 Gloire, gloire
[V2]
 Quand nous serons
</lyrics>
</song>
"""

CCLI_TXT = """Amazing Grace

Verse 1
Amazing grace how sweet the sound
That saved a wretch like me

Chorus
My chains are gone

Verse 2
'Twas grace that taught my heart to fear

CCLI Song # 4768151
© 2006 sixsteps Music
For use solely with the SongSelect® Terms of Use.
"""

CCLI_USR = """[File]
Type=SongSelect Import File
Version=3.0
Title=Mighty to Save
Fields=Verse 1/tChorus 1
Words=Everyone needs compassion/nLove that's never failing/tSavior He can move the mountains/nMy God is mighty to save
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_openlyrics_follows_verse_order(tmp_path: Path) -> None:
    song = read_song_file(_write(tmp_path, "gloire.xml", OPENLYRICS))
    assert song["title"] == "À toi la gloire"
    assert song["number"] == "33"
    assert song["stanzas"] == [
        ("À toi la gloire\nÔ Ressuscité", False),
        ("Gloire à toi\nAlléluia", True),
        ("Vois-le paraître\nC'est Jésus", False),
        ("Gloire à toi\nAlléluia", True),
    ]


def test_opensong_skips_chords_and_comments(tmp_path: Path) -> None:
    song = read_song_file(_write(tmp_path, "grace", OPENSONG))
    assert song["title"] == "Grâce infinie" and song["number"] == "12"
    assert song["stanzas"] == [
        ("Grâce infinie\nQue Dieu m'a faite", False),
        ("Gloire, gloire", True),
        ("Quand nous serons", False),
    ]


def test_ccli_text_and_usr(tmp_path: Path) -> None:
    song = read_song_file(_write(tmp_path, "amazing.txt", CCLI_TXT))
    assert song["title"] == "Amazing Grace"
    assert song["stanzas"] == [
        ("Amazing grace how sweet the sound\nThat saved a wretch like me", False),
        ("My chains are gone", True),
        ("'Twas grace that taught my heart to fear", False),
    ]
    usr = read_song_file(_write(tmp_path, "mighty.usr", CCLI_USR))
    assert usr["title"] == "Mighty to Save"
    assert usr["stanzas"][1] == ("Savior He can move the mountains\nMy God is mighty to save", True)


def test_unknown_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        read_song_file(_write(tmp_path, "vide.txt", "\n\n"))
    with pytest.raises(Exception):
        read_song_file(_write(tmp_path, "autre.xml", "<playlist/>"))


def test_import_song_paths_saves_and_skips_duplicates(tmp_path: Path) -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from app.database.connection import Database, DatabaseConfig
    from app.database.dao_hymns import HymnsDao
    from app.utils.library_controller import LibraryController

    db = Database(DatabaseConfig(db_path=tmp_path / "s.db"))
    db.initialize()
    path = _write(tmp_path, "gloire.xml", OPENLYRICS)

    # Le traitement d'un fichier, sans fenêtre de progression.
    captured = {}

    class _Fake:
        _hymns_dao = HymnsDao(db)

        def _start_import(self, title, items, process, refresh=None):
            import threading

            captured["results"] = [process(item, threading.Event()) for item in items]

        def refresh_hymns(self):
            pass

    fake = _Fake()
    LibraryController.import_song_paths(fake, [path])
    LibraryController.import_song_paths(fake, [path])
    first, second = captured["results"][0], None
    assert isinstance(first, int) or first is None
    hymns = HymnsDao(db).list_hymns()
    assert [h["title"] for h in hymns].count("À toi la gloire") == 1
