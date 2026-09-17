from pathlib import Path
import sqlite3

import pytest

from app.utils import app_paths
from app.database.connection import Database, DatabaseConfig
from app.database.dao_hymns import HymnsDao


_bootstrap = (app_paths.ensure_data_initialized,)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch, isolate_user_paths):
    monkeypatch.setattr(app_paths, "ensure_data_initialized", _bootstrap[0])
    # Never consult the registry, user profile or bundled databases/Bible files.
    monkeypatch.setattr(app_paths, "user_data_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(app_paths, "resource_root", lambda: tmp_path / "resources")
    monkeypatch.setattr(app_paths, "data_dir", lambda: tmp_path / "profile" / "data")
    monkeypatch.setattr(app_paths, "is_frozen", lambda: True)
    monkeypatch.setattr("app.database.connection.bible_json_dir", lambda: tmp_path / "bible")


def test_media_same_name_and_size_preserves_both_contents(tmp_path):
    first = tmp_path / "a" / "slide.png"
    second = tmp_path / "b" / "slide.png"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"AAAA")
    second.write_bytes(b"BBBB")
    a = app_paths.import_media_file(first)
    b = app_paths.import_media_file(second)
    assert a != b
    assert a.read_bytes() == b"AAAA"
    assert b.read_bytes() == b"BBBB"
    assert app_paths.import_media_file(first) == a


def test_media_copy_failure_never_publishes(tmp_path, monkeypatch):
    source = tmp_path / "slide.png"
    source.write_bytes(b"complete")
    def broken_copy(src, dst):
        Path(dst).write_bytes(b"partial")
        raise OSError("interrupted copy")
    monkeypatch.setattr(app_paths.shutil, "copy2", broken_copy)
    with pytest.raises(OSError):
        app_paths.import_media_file(source)
    assert list(app_paths.media_dir().iterdir()) == []


def test_media_identical_content_other_name(tmp_path):
    a = tmp_path / "one.png"
    b = tmp_path / "two.png"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    assert app_paths.import_media_file(a) == app_paths.import_media_file(b)


def test_missing_media_returns_none(tmp_path):
    assert app_paths.import_media_file(tmp_path / "missing") is None


# ── ensure_data_initialized : amorçage vérifié, jamais d'écrasement ────────


def _make_db(path, marker):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE marker (value TEXT)")
        conn.execute("INSERT INTO marker VALUES (?)", (value := marker,))
        conn.commit()
    return value


def test_bootstrap_copies_and_verifies_missing_database(tmp_path):
    bundled = tmp_path / "resources" / "data" / "project_on.db"
    _make_db(bundled, "bundled")
    app_paths.ensure_data_initialized()
    target = tmp_path / "profile" / "data" / "project_on.db"
    assert target.is_file()
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT value FROM marker").fetchone()[0] == "bundled"


def test_bootstrap_never_replaces_existing_user_database(tmp_path):
    bundled = tmp_path / "resources" / "data" / "project_on.db"
    _make_db(bundled, "bundled")
    target = tmp_path / "profile" / "data" / "project_on.db"
    user_value = _make_db(target, "user")
    app_paths.ensure_data_initialized()
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT value FROM marker").fetchone()[0] == user_value


def test_bootstrap_never_replaces_corrupted_existing_database(tmp_path):
    bundled = tmp_path / "resources" / "data" / "project_on.db"
    _make_db(bundled, "bundled")
    target = tmp_path / "profile" / "data" / "project_on.db"
    # Vestige sans en-tête valide : l'origine (utilisateur vs copie tronquée)
    # étant indécidable, l'amorçage ne doit rien remplacer en silence.
    payload = b"partial"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    app_paths.ensure_data_initialized()
    assert target.read_bytes() == payload
    assert list(target.parent.glob("*.bootstrap-*")) == []


def test_bootstrap_leaves_real_corrupted_database_alone(tmp_path):
    bundled = tmp_path / "resources" / "data" / "project_on.db"
    _make_db(bundled, "bundled")
    target = tmp_path / "profile" / "data" / "project_on.db"
    # En-tête SQLite valide mais contenu corrompu : base utilisateur à ne pas
    # remplacer en silence.
    payload = b"SQLite format 3\x00" + b"\x00" * 32
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    app_paths.ensure_data_initialized()
    assert target.read_bytes() == payload


# ── upgrade_data_pack : contenu + index de recherche dans la même transaction


FTS_DDL = (
    "CREATE VIRTUAL TABLE sermon_paragraph_fts USING fts5("
    "text, ref, sermon_title, canonical_title, "
    "content='', detail=none, "
    "tokenize='unicode61 remove_diacritics 2')"
)


def _prepare_target_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE sermon (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, date TEXT,
                tradition TEXT NOT NULL, language TEXT, source_path TEXT,
                sort_key TEXT, location TEXT DEFAULT '',
                canonical_title TEXT DEFAULT '', title_search TEXT DEFAULT ''
            );
            CREATE TABLE sermon_paragraph (
                id INTEGER PRIMARY KEY, sermon_id INTEGER NOT NULL,
                paragraph_no INTEGER NOT NULL, ref TEXT, text TEXT NOT NULL,
                marker TEXT DEFAULT '',
                FOREIGN KEY (sermon_id) REFERENCES sermon (id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(FTS_DDL)
        conn.execute(
            "INSERT INTO sermon (id, title, date, tradition, language) "
            "VALUES (1, 'Ancien chapitre', 'BK-AGES-01', 'VGR', 'fr')"
        )
        conn.execute(
            "INSERT INTO sermon_paragraph (sermon_id, paragraph_no, ref, text) "
            "VALUES (1, 1, '¶1', 'Ancien paragraphe obsolète.')"
        )
        conn.execute(
            "INSERT INTO sermon_paragraph_fts (rowid, text, ref, sermon_title, "
            "canonical_title) VALUES (1, 'Ancien paragraphe obsolète.', '¶1', "
            "'Ancien chapitre', 'Ancien chapitre')"
        )
        conn.execute(
            "INSERT INTO app_meta VALUES ('data_pack_version', '1')"
        )
        conn.execute(
            "INSERT INTO app_meta VALUES ('startup_maintenance_version', '10')"
        )


def _prepare_pack_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sermon (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, date TEXT,
                tradition TEXT NOT NULL, language TEXT, source_path TEXT,
                sort_key TEXT, location TEXT DEFAULT '',
                canonical_title TEXT DEFAULT '', title_search TEXT DEFAULT ''
            );
            CREATE TABLE sermon_paragraph (
                id INTEGER PRIMARY KEY, sermon_id INTEGER NOT NULL,
                paragraph_no INTEGER NOT NULL, ref TEXT, text TEXT NOT NULL,
                marker TEXT DEFAULT ''
            );
            """
        )
        conn.execute(
            "INSERT INTO sermon (id, title, date, tradition, language) "
            "VALUES (7, 'Nouveau chapitre', 'BK-AGES-01', 'VGR', 'fr')"
        )
        conn.execute(
            "INSERT INTO sermon_paragraph (id, sermon_id, paragraph_no, ref, "
            "text) VALUES (11, 7, 1, '¶1', 'Paragraphe neuf a Rechercher.')"
        )


def test_data_pack_replaces_content_and_fts_in_one_transaction(tmp_path):
    target = tmp_path / "target.db"
    pack = tmp_path / "pack.db"
    _prepare_target_db(target)
    _prepare_pack_db(pack)
    assert app_paths.upgrade_data_pack(target, pack)
    with sqlite3.connect(target) as conn:
        paragraphs = conn.execute(
            "SELECT text FROM sermon_paragraph"
        ).fetchall()
        assert [row[0] for row in paragraphs] == ["Paragraphe neuf a Rechercher."]
        # L'index de recherche doit refléter le nouveau contenu immédiatement.
        hits = conn.execute(
            "SELECT rowid FROM sermon_paragraph_fts WHERE sermon_paragraph_fts "
            "MATCH 'Rechercher'"
        ).fetchall()
        assert hits
        stale = conn.execute(
            "SELECT rowid FROM sermon_paragraph_fts WHERE sermon_paragraph_fts "
            "MATCH 'obsolète'"
        ).fetchall()
        assert stale == []
        # Marqueur durable : la maintenance complète est reprogrammée.
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key='startup_maintenance_version'"
        ).fetchone()
        assert row is None


def test_data_pack_failure_rolls_back_everything(tmp_path):
    target = tmp_path / "target.db"
    pack = tmp_path / "pack.db"
    _prepare_target_db(target)
    _prepare_pack_db(pack)
    # Forcer un échec : la table app_meta du pack manque ? Non — corrompre la
    # base pack après création pour faire échouer une requête.
    with sqlite3.connect(pack) as conn:
        conn.execute("DROP TABLE sermon_paragraph")
    assert not app_paths.upgrade_data_pack(target, pack)
    with sqlite3.connect(target) as conn:
        text = conn.execute(
            "SELECT text FROM sermon_paragraph WHERE paragraph_no = 1"
        ).fetchone()[0]
        assert text == "Ancien paragraphe obsolète."
        version = conn.execute(
            "SELECT value FROM app_meta WHERE key='data_pack_version'"
        ).fetchone()[0]
        assert version == "1"


def test_data_pack_already_current_is_noop(tmp_path):
    target = tmp_path / "target.db"
    pack = tmp_path / "pack.db"
    _prepare_target_db(target)
    with sqlite3.connect(target) as conn:
        conn.execute(
            "UPDATE app_meta SET value='999' WHERE key='data_pack_version'"
        )
    _prepare_pack_db(pack)
    assert not app_paths.upgrade_data_pack(target, pack)
    with sqlite3.connect(target) as conn:
        text = conn.execute(
            "SELECT text FROM sermon_paragraph WHERE paragraph_no = 1"
        ).fetchone()[0]
        assert text == "Ancien paragraphe obsolète."


# ── Jeu de données de démonstration indexé dès le premier démarrage ────────


def test_demo_data_searchable_after_first_initialize(tmp_path):
    from app.database.connection import Database, DatabaseConfig

    database = Database(DatabaseConfig(db_path=tmp_path / "fresh.db"))
    database.initialize()
    dao = HymnsDao(database)
    results = dao.search_stanzas("chanter")
    assert results
    sermons_found = database.search_sermons("substance") if hasattr(
        database, "search_sermons"
    ) else None
    if sermons_found is not None:
        assert sermons_found


# ── Dédoublonnage hymnes : identité exacte, pas une approximation ───────────


def test_exact_duplicate_identity(tmp_path):
    from app.database.connection import Database, DatabaseConfig

    database = Database(DatabaseConfig(db_path=tmp_path / "dupe.db"))
    database.initialize()
    dao = HymnsDao(database)
    stanzas = ["Strophe une.\nSuite du texte.", "Refrain : Gloire à Dieu."]
    dao.import_hymn("Grâce", stanzas, number="12")
    assert dao.exact_duplicate_exists("Grâce", stanzas)
    assert not dao.exact_duplicate_exists("Grâce", ["Autre texte."])
    assert not dao.exact_duplicate_exists("Amour", stanzas)


def test_substring_title_is_not_a_duplicate(tmp_path):
    from app.database.connection import Database, DatabaseConfig

    database = Database(DatabaseConfig(db_path=tmp_path / "substr.db"))
    database.initialize()
    dao = HymnsDao(database)
    dao.import_hymn("Grâce infinie", ["Texte long."])
    # « Grâce » n'est pas un doublon exact de « Grâce infinie ».
    assert not dao.exact_duplicate_exists("Grâce", ["Texte long."])
    # Mais l'identité exacte continue de détecter le même titre.
    assert dao.exact_duplicate_exists("Grâce  infinie", ["Texte long."])
    # hymn_exists est désormais une identité exacte de titre : « Grâce »
    # n'est plus rejeté parce que « Grâce infinie » existe.
    assert not dao.hymn_exists("Grâce")
    assert dao.hymn_exists("Grâce  infinie")


def test_bootstrap_never_publishes_unverifiable_source(tmp_path):
    bundled = tmp_path / "resources" / "data" / "project_on.db"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_bytes(b"not a database")
    app_paths.ensure_data_initialized()
    assert not (tmp_path / "profile" / "data" / "project_on.db").exists()


def test_bootstrap_leaves_real_corrupted_database_alone(tmp_path):
    bundled = tmp_path / "resources" / "data" / "project_on.db"
    _make_db(bundled, "bundled")
    target = tmp_path / "profile" / "data" / "project_on.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    # En-tête SQLite valide mais contenu corrompu : base utilisateur à ne pas
    # remplacer en silence — la reprise d'amorçage ne s'applique qu'aux
    # vestiges sans en-tête.
    payload = b"SQLite format 3\x00" + b"\x00" * 32
    target.write_bytes(payload)
    app_paths.ensure_data_initialized()
    assert target.read_bytes() == payload
