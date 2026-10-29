"""Module natif Rust (rust/project_on_core) : mêmes résultats que Python."""

from __future__ import annotations

import sqlite3

import pytest

from app.utils import text_utils
from app.utils.text_utils import _py_unaccent, install_unaccent

SAMPLES = [
    "",
    "Colonne de FEU",
    "Éternel Dieu, ô Père, ça déjà",
    "Œuvre, cœur, ﬁn², ½",
    "Café décomposé",
    "ΟΔΟΣ Σοφία",
    "İstanbul ǅemal",
    "Ünïcödé ñ ß ø Ł",
    "日本語 العربية עברית",
    "ẹ́ marques empilées",
]

native = pytest.mark.skipif(
    not text_utils.NATIVE_TEXT, reason="module natif non compilé sur ce poste"
)


@native
@pytest.mark.parametrize("text", SAMPLES)
def test_native_unaccent_matches_python(text):
    assert text_utils.unaccent(text) == _py_unaccent(text)


@native
@pytest.mark.parametrize("value", [None, 0, 12, 3.5, ""])
def test_native_unaccent_non_text_like_python(value):
    assert text_utils.unaccent(value) == _py_unaccent(value)


@native
def test_unaccent_many_matches_python():
    values = [*SAMPLES, None, 0, 7]
    assert text_utils.unaccent_many(values) == [_py_unaccent(v) for v in values]


def _sql_unaccent(conn, value):
    return conn.execute("SELECT unaccent(?)", (value,)).fetchone()[0]


def _check_sql(conn):
    for text in SAMPLES:
        assert _sql_unaccent(conn, text) == _py_unaccent(text)
    assert _sql_unaccent(conn, None) == ""
    assert _sql_unaccent(conn, 0) == ""
    assert _sql_unaccent(conn, 12) == "12"
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.executemany("INSERT INTO t VALUES (?)", [("Élie à Béthel",), ("autre",)])
    rows = conn.execute(
        "SELECT x FROM t WHERE unaccent(x) LIKE unaccent(?)", ("%ELIE A BETH%",)
    ).fetchall()
    assert rows == [("Élie à Béthel",)]


@native
def test_install_unaccent_loads_native_sqlite_extension():
    conn = sqlite3.connect(":memory:")
    install_unaccent(conn)
    # L'extension native est déclarée par SQLite, pas par Python : la
    # fonction reste disponible même sans repli Python enregistré.
    _check_sql(conn)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("SELECT load_extension('x')")  # chargement refermé


def test_install_unaccent_python_fallback(monkeypatch):
    monkeypatch.setattr(text_utils, "_NATIVE_SQLITE_EXTENSION", None)
    conn = sqlite3.connect(":memory:")
    install_unaccent(conn)
    _check_sql(conn)


def test_install_unaccent_falls_back_when_extension_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        text_utils, "_NATIVE_SQLITE_EXTENSION", str(tmp_path / "absent.dll")
    )
    conn = sqlite3.connect(":memory:")
    install_unaccent(conn)
    _check_sql(conn)
