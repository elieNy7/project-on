"""Validate all hymn PDFs, then atomically rebuild only the hymn library.

Usage:
    py -3 tools/import_cantiques.py
    py -3 tools/import_cantiques.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.connection import Database, DatabaseConfig  # noqa: E402
from app.utils.hymn_pdf_parser import (  # noqa: E402
    HymnSection,
    parse_pdf_ranges,
)
from tools.import_swahili_hymns import parse_pdf as parse_swahili_pdf  # noqa: E402
from tools.import_cantique_adoration_folder import (  # noqa: E402
    DEFAULT_CACHE as AD_CACHE,
    DEFAULT_FOLDER as AD_FOLDER,
    NATIVE_OPENXML_EXTENSIONS,
    POWERPOINT_EXTENSIONS,
    clean_source_title,
    iter_folder_files,
    normalize_key,
    parse_cantique_file,
)

CANTIQUES_DIR = ROOT / "cantiques"
REPORT_PATH = ROOT / "verification" / "hymn_import_report.json"
BACKUP_DIR = ROOT / "tmp" / "db-backups"
AD_EXCLUDED_NON_HYMNS = {
    normalize_key("armageddon presentation cameroon.pptx"),
    normalize_key("L’ANNEE DE JUBILE,LE MYSTERE DE LA LIBERTE.pptx"),
}


@dataclass(frozen=True)
class PdfSpec:
    source: str
    filename: str
    ranges: list[tuple[int, int | None]]
    language: str
    column_break: bool
    expected_hymns: int
    note: str


@dataclass(frozen=True)
class ImportHymn:
    source: str
    number: str
    title: str
    language: str
    sections: list[HymnSection]
    pdf: str


SPECS = [
    PdfSpec(
        "PNY",
        "Cantique Pene Na Yo.pdf",
        [(0, 47)],
        "ln",
        True,
        150,
        "Pages 1-47; la page 48 est l'index. Le numéro 52 est absent du PDF.",
    ),
    PdfSpec(
        "CS",
        "Cantiques Crois seulement.pdf",
        [(0, 70), (76, None)],
        "fr",
        False,
        241,
        "Pages 71-76 ignorées (index); les pages 77-80 forment un second recueil numéroté.",
    ),
    PdfSpec(
        "CI",
        "Cantiques-Ins.pdf",
        [(4, 154)],
        "fr",
        False,
        304,
        "Pages 1-4 de garde et pages 155-168 sans chants ignorées; suffixes a/b conservés.",
    ),
]


def parse_all() -> tuple[list[ImportHymn], list[dict[str, Any]]]:
    expected_files = {spec.filename for spec in SPECS} | {"cantique-swahili.pdf"}
    actual_files = {path.name for path in CANTIQUES_DIR.glob("*.pdf")}
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        unexpected = sorted(actual_files - expected_files)
        raise RuntimeError(f"PDF manquants={missing}; PDF inattendus={unexpected}")

    hymns: list[ImportHymn] = []
    sources: list[dict[str, Any]] = []
    for spec in SPECS:
        path = CANTIQUES_DIR / spec.filename
        parsed = parse_pdf_ranges(
            path,
            spec.source,
            spec.ranges,
            column_break=spec.column_break,
        )
        if len(parsed) != spec.expected_hymns:
            raise RuntimeError(
                f"{spec.source}: {len(parsed)} chants, attendu {spec.expected_hymns}."
            )
        items = [
            ImportHymn(
                hymn.source,
                hymn.number,
                hymn.title,
                spec.language,
                hymn.sections,
                spec.filename,
            )
            for hymn in parsed
        ]
        hymns.extend(items)
        sources.append(source_report(spec.source, spec.filename, items, spec.note))

    sw_path = CANTIQUES_DIR / "cantique-swahili.pdf"
    sw_parsed = parse_swahili_pdf(sw_path)
    if len(sw_parsed) != 335:
        raise RuntimeError(f"SW: {len(sw_parsed)} chants, attendu 335.")
    sw_items = [
        ImportHymn(
            "SW",
            f"SW-{hymn.number:03d}",
            hymn.title,
            "sw",
            [HymnSection(s.text, s.label, s.is_chorus) for s in hymn.sections],
            sw_path.name,
        )
        for hymn in sw_parsed
    ]
    hymns.extend(sw_items)
    sources.append(
        source_report(
            "SW",
            sw_path.name,
            sw_items,
            "Pages 8-418; les refrains sont les blocs italiques du PDF.",
        )
    )
    validate_pdf_corpus(hymns)
    ad_hymns, ad_report = parse_adoration_powerpoints(hymns)
    hymns.extend(ad_hymns)
    sources.append(ad_report)
    validate_corpus(hymns)
    return hymns, sources


def detect_language(title: str, sections: list[HymnSection]) -> str:
    text = normalize_key(" ".join([title] + [section.text for section in sections]))
    tokens = set(text.split())
    markers = {
        "sw": {"bwana", "mungu", "wokovu", "katika", "moyo", "milele", "damu", "hakuna"},
        "ln": {"nkolo", "nzambe", "ngai", "biso", "mpo", "ezali", "nkembo", "motema"},
        "en": {"lord", "god", "jesus", "blood", "heaven", "glory", "love", "soul"},
        "fr": {"seigneur", "dieu", "jesus", "sang", "ciel", "gloire", "amour", "ame"},
    }
    scores = {language: len(tokens & words) for language, words in markers.items()}
    language, score = max(scores.items(), key=lambda item: item[1])
    return language if score >= 2 else "fr"


def hymn_content_signature(sections: list[HymnSection]) -> str:
    verses: list[str] = []
    choruses: list[str] = []
    for section in sections:
        text = section.text
        if section.is_chorus and "\n" in text:
            text = text.split("\n", 1)[1]
        key = normalize_key(text)
        if not key:
            continue
        if section.is_chorus:
            if key not in choruses:
                choruses.append(key)
        else:
            verses.append(key)
    payload = json.dumps(
        {"verses": verses, "choruses": choruses},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_adoration_powerpoints(
    existing_hymns: list[ImportHymn],
) -> tuple[list[ImportHymn], dict[str, Any]]:
    files = [
        path
        for path in iter_folder_files(AD_FOLDER)
        if path.suffix.lower() in POWERPOINT_EXTENSIONS
    ]
    unreadable: list[str] = []
    excluded: list[str] = []
    candidates: list[tuple[Path, str, list[HymnSection]]] = []
    for path in files:
        if normalize_key(path.name) in AD_EXCLUDED_NON_HYMNS:
            excluded.append(path.name)
            continue
        parsed = parse_cantique_file(path, AD_CACHE)
        if parsed is None:
            unreadable.append(path.name)
            continue
        sections = [
            HymnSection(
                str(section["text"]).strip(),
                str(section["label"]).strip(),
                bool(section["is_chorus"]),
            )
            for section in parsed.get("sections", [])
            if str(section.get("text", "")).strip()
        ]
        if not sections:
            unreadable.append(path.name)
            continue
        candidates.append((path, clean_source_title(parsed["title"]), sections))

    grouped: dict[str, list[tuple[Path, str, list[HymnSection]]]] = defaultdict(list)
    for candidate in candidates:
        grouped[hymn_content_signature(candidate[2])].append(candidate)

    def preference(candidate: tuple[Path, str, list[HymnSection]]) -> tuple[int, int, int, str]:
        path, title, _sections = candidate
        noise = sum(
            token in normalize_key(path.name)
            for token in ("copie", "lecture seule", "compatibility mode", "enregistrement automatique")
        )
        native = 0 if path.suffix.lower() in NATIVE_OPENXML_EXTENSIONS else 1
        return native, noise, len(title), normalize_key(path.name)

    existing_signatures = {
        hymn_content_signature(hymn.sections) for hymn in existing_hymns
    }
    duplicates: list[dict[str, Any]] = []
    selected: list[tuple[Path, str, list[HymnSection]]] = []
    skipped_existing_content = 0
    for signature, group in grouped.items():
        kept = min(group, key=preference)
        if len(group) > 1:
            duplicates.append(
                {
                    "kept": kept[0].name,
                    "skipped": sorted(item[0].name for item in group if item is not kept),
                }
            )
        if signature in existing_signatures:
            skipped_existing_content += 1
            continue
        selected.append(kept)

    selected.sort(key=lambda item: normalize_key(item[0].name))
    hymns: list[ImportHymn] = []
    for index, (path, title, sections) in enumerate(selected, start=1):
        hymns.append(
            ImportHymn(
                "AD",
                f"AD-{index:04d}",
                title,
                detect_language(title, sections),
                sections,
                path.name,
            )
        )

    section_list = [section for hymn in hymns for section in hymn.sections]
    report = {
        "source": "AD",
        "pdf": "CANTIQUE D'ADORATION (PowerPoint)",
        "files_scanned": len(files),
        "files_parsed_as_hymns": len(candidates),
        "hymns": len(hymns),
        "sections": len(section_list),
        "verses": sum(not section.is_chorus for section in section_list),
        "choruses": sum(section.is_chorus for section in section_list),
        "distinct_choruses": sum(
            len({section.text for section in hymn.sections if section.is_chorus})
            for hymn in hymns
        ),
        "first_number": hymns[0].number if hymns else "",
        "last_number": hymns[-1].number if hymns else "",
        "duplicate_files_skipped": len(candidates) - len(grouped),
        "duplicates": duplicates,
        "already_in_pdf_corpus": skipped_existing_content,
        "excluded_non_hymns": sorted(excluded),
        "unreadable_files": sorted(unreadable),
        "note": "PowerPoint analysés diapositive par diapositive; doublons de paroles supprimés.",
    }
    return hymns, report


def source_report(
    source: str,
    filename: str,
    hymns: list[ImportHymn],
    note: str,
) -> dict[str, Any]:
    sections = [section for hymn in hymns for section in hymn.sections]
    distinct_choruses = sum(
        len({section.text for section in hymn.sections if section.is_chorus})
        for hymn in hymns
    )
    return {
        "source": source,
        "pdf": filename,
        "hymns": len(hymns),
        "sections": len(sections),
        "verses": sum(not section.is_chorus for section in sections),
        "choruses": sum(section.is_chorus for section in sections),
        "distinct_choruses": distinct_choruses,
        "first_number": hymns[0].number,
        "last_number": hymns[-1].number,
        "note": note,
    }


def validate_pdf_corpus(hymns: list[ImportHymn]) -> None:
    if len(hymns) != 1030:
        raise RuntimeError(f"Corpus incomplet: {len(hymns)} chants au lieu de 1030.")


def validate_corpus(hymns: list[ImportHymn]) -> None:
    numbers = [hymn.number for hymn in hymns]
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        raise RuntimeError(f"Numéros dupliqués: {duplicates[:20]}")

    footer_fragments = (
        "petit troupeau tabernacle",
        "branhammessage.info",
        "table de matieres",
        "table des matieres",
        "table alphabétique",
        "table numérique",
        "page de titre",
    )
    errors: list[str] = []
    for hymn in hymns:
        if not hymn.title.strip() or not hymn.sections:
            errors.append(f"{hymn.number}: titre ou contenu vide")
        if not any(not section.is_chorus for section in hymn.sections):
            errors.append(f"{hymn.number}: aucun couplet")
        for section in hymn.sections:
            text = section.text.strip()
            if not text:
                errors.append(f"{hymn.number}: section vide")
            if any(fragment in text.casefold() for fragment in footer_fragments):
                errors.append(f"{hymn.number}: entête/footer dans {section.label}")
            starts_as_chorus = text.casefold().startswith(
                ("choeur", "chœur", "refrain", "dernier refrain")
            )
            if starts_as_chorus != section.is_chorus:
                errors.append(f"{hymn.number}: classification incohérente {section.label}")
    if errors:
        raise RuntimeError("Validation PDF échouée: " + "; ".join(errors[:20]))


def sermon_fingerprint(conn: sqlite3.Connection) -> dict[str, Any]:
    by_translation = [
        dict(row)
        for row in conn.execute(
            """
            SELECT tradition, COALESCE(language, '') AS language,
                   COUNT(*) AS sermons,
                   SUM(LENGTH(COALESCE(title, '')) + LENGTH(COALESCE(date, ''))
                       + LENGTH(COALESCE(location, ''))) AS metadata_chars,
                   MIN(id) AS min_id, MAX(id) AS max_id
            FROM sermon
            GROUP BY tradition, COALESCE(language, '')
            ORDER BY tradition, language
            """
        )
    ]
    paragraphs = [
        dict(row)
        for row in conn.execute(
            """
            SELECT s.tradition, COALESCE(s.language, '') AS language,
                   COUNT(*) AS paragraphs, SUM(LENGTH(sp.text)) AS text_chars,
                   MIN(sp.id) AS min_id, MAX(sp.id) AS max_id
            FROM sermon_paragraph sp
            JOIN sermon s ON s.id = sp.sermon_id
            GROUP BY s.tradition, COALESCE(s.language, '')
            ORDER BY s.tradition, language
            """
        )
    ]
    fts_count = conn.execute("SELECT COUNT(*) FROM sermon_paragraph_fts").fetchone()[0]
    payload = {"sermons": by_translation, "paragraphs": paragraphs, "fts": int(fts_count)}
    payload["sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload


def backup_database(db_path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"project_on-before-hymn-import-{timestamp}.db"
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


def rebuild_hymns(db: Database, hymns: Iterable[ImportHymn]) -> dict[str, Any]:
    with db.connect() as conn:
        sermon_before = sermon_fingerprint(conn)
        removed = int(conn.execute("SELECT COUNT(*) FROM hymn").fetchone()[0])

    backup_path = backup_database(db.db_path)
    hymn_list = list(hymns)
    with db.connect() as conn:
        conn.execute("DROP TABLE IF EXISTS hymn_stanza_fts")
        conn.execute("DELETE FROM hymn_stanza")
        conn.execute("DELETE FROM hymn")

        for sort_order, hymn in enumerate(hymn_list, start=1):
            canonical = Database._clean_hymn_title_for_canonical(hymn.title)
            title_search = Database._search_key(
                " ".join((canonical, hymn.title, hymn.number, hymn.language))
            )
            cursor = conn.execute(
                """
                INSERT INTO hymn
                    (title, number, language, sort_key, canonical_title, title_search)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    hymn.title,
                    hymn.number,
                    hymn.language,
                    f"{sort_order:05d}",
                    canonical,
                    title_search,
                ),
            )
            hymn_id = int(cursor.lastrowid)
            for stanza_no, section in enumerate(hymn.sections, start=1):
                conn.execute(
                    """
                    INSERT INTO hymn_stanza
                        (hymn_id, stanza_no, text, label, is_chorus)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        hymn_id,
                        stanza_no,
                        section.text,
                        section.label,
                        1 if section.is_chorus else 0,
                    ),
                )
        db._ensure_hymn_fts(conn)

    with db.connect() as conn:
        sermon_after = sermon_fingerprint(conn)
        if sermon_after != sermon_before:
            raise RuntimeError("Les tables de sermons ont changé pendant l'import.")
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        counts = {
            "hymns": int(conn.execute("SELECT COUNT(*) FROM hymn").fetchone()[0]),
            "sections": int(
                conn.execute("SELECT COUNT(*) FROM hymn_stanza").fetchone()[0]
            ),
            "verses": int(
                conn.execute(
                    "SELECT COUNT(*) FROM hymn_stanza WHERE is_chorus = 0"
                ).fetchone()[0]
            ),
            "choruses": int(
                conn.execute(
                    "SELECT COUNT(*) FROM hymn_stanza WHERE is_chorus = 1"
                ).fetchone()[0]
            ),
            "fts": int(
                conn.execute("SELECT COUNT(*) FROM hymn_stanza_fts").fetchone()[0]
            ),
        }
    expected_sections = sum(len(hymn.sections) for hymn in hymn_list)
    if counts["hymns"] != len(hymn_list) or counts["sections"] != expected_sections:
        raise RuntimeError(f"Comptage final incorrect: {counts}")
    if counts["fts"] != counts["sections"] or integrity != "ok":
        raise RuntimeError(f"Index/intégrité incorrects: {counts}, integrity={integrity}")
    return {
        "removed_hymns": removed,
        "backup": str(backup_path),
        "counts": counts,
        "integrity_check": integrity,
        "sermon_fingerprint": sermon_after,
    }


def print_report(sources: list[dict[str, Any]]) -> None:
    print("Sources de cantiques analysées et validées:")
    for item in sources:
        print(
            f"  {item['source']}: {item['hymns']} cantiques, "
            f"{item['verses']} couplets, {item['distinct_choruses']} refrains distincts "
            f"({item['choruses']} passages de refrain pour la projection) "
            f"({item['pdf']})"
        )
    print(f"  TOTAL: {sum(item['hymns'] for item in sources)} cantiques")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Nettoie et importe.")
    parser.add_argument("--db", type=Path, help="Base SQLite cible.")
    args = parser.parse_args()

    hymns, sources = parse_all()
    print_report(sources)
    if not args.apply:
        print("\nDry-run validé; aucune donnée modifiée. Utilisez --apply pour importer.")
        return

    db = Database(DatabaseConfig(args.db.resolve())) if args.db else Database.default()
    db.initialize()
    result = rebuild_hymns(db, hymns)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "database": str(db.db_path),
        "sources": sources,
        **result,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "\nImport terminé: "
        f"{result['counts']['hymns']} cantiques, "
        f"{result['counts']['verses']} couplets, "
        f"{result['counts']['choruses']} refrains."
    )
    print(f"Sauvegarde: {result['backup']}")
    print(f"Rapport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
