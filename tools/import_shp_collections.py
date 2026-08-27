"""Importe les collections annuelles SHP dans ``data/project_on.db``.

Les PDF ``shp/47/47.pdf`` a ``shp/65/65.pdf`` contiennent plusieurs sermons.
Leur mise en page fournit trois signaux fiables que ce script utilise ensemble:

* un bandeau bleu a texte blanc ouvre chaque sermon (titre, lieu, date);
* une ligne bleue a 10 points repete l'en-tete avant chaque paragraphe;
* le corps du paragraphe est noir et commence par son numero suivi d'un point.

L'import ne segmente donc jamais sur une simple ligne vide. Les en-tetes/pieds de
page Kosher et les informations d'export sont exclus par leur position et leur
libelle. Le titre, le lieu et la date proviennent toujours du bandeau imprime
(16 pt blanc), jamais de l'en-tete repete : le titre stocke est donc exactement
celui du PDF, coquilles comprises. Par defaut le script analyse et valide
seulement. ``--apply`` est requis pour remplacer uniquement les sermons SHP,
tout en conservant Expose, VGR, BSS et toute autre traduction deja presente.
``--apply --metadata-only`` importe le catalogue seul (titre exact, date, lieu)
sans le texte des paragraphes.

Apres l'import, l'application recalcule les metadonnees de recherche : la
traduction SHP garde toujours son titre PDF exact comme titre canonique.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sqlite3
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import fitz


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "shp"
DEFAULT_DB = ROOT / "data" / "project_on.db"
DEFAULT_REPORT = ROOT / "verification" / "shp_import_report.json"

BLUE = 0x0000FF
WHITE = 0xFFFFFF
DATE_AT_END_RE = re.compile(
    r"(?:(?P<weekday>Lun|Mar|Mer|Jeu|Ven|Sam|Dim)\s+)?"
    r"(?P<day>\d{2})\.(?P<month>\d{2})(?P<year_sep>\.|\s+)(?P<year>\d{2})"
    r"(?P<suffix>[A-Z])?\s*$",
    re.IGNORECASE,
)
LEADING_MARKER_RE = re.compile(r"\d+[A-Za-z]?(?:\s*\.\s*|$)")
WEEKDAY_RE = re.compile(
    r"^(?:Lun|Mar|Mer|Jeu|Ven|Sam|Dim)$", re.IGNORECASE
)
FOOTER_TOKENS = (
    "Shekinah Publications",
    "Recherche :",
    "Recherche :",
    "Kosher Page:",
    "Kosher Page :",
)


class ExtractionError(RuntimeError):
    """Erreur de structure qui rend l'import dangereux."""


@dataclass(frozen=True)
class BannerLine:
    text: str
    page: int
    y: float


@dataclass(frozen=True)
class ExtractedParagraph:
    marker: str
    text: str
    page_start: int
    page_end: int


@dataclass
class ExtractedSermon:
    title: str
    location: str
    date_code: str
    header: str
    source_path: str
    source_page: int
    paragraphs: list[ExtractedParagraph] = field(default_factory=list)


@dataclass
class FileExtraction:
    source_path: str
    page_count: int
    sermons: list[ExtractedSermon]
    warnings: list[str]
    elapsed_seconds: float


@dataclass
class _ParagraphBuilder:
    header: str
    page_start: int
    marker: str | None = None
    text_lines: list[str] = field(default_factory=list)
    page_end: int = 0


def _clean_line(value: str) -> str:
    text = unicodedata.normalize("NFC", value or "")
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    text = text.replace("\u00ad", "").replace("\ufeff", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", _clean_line(value)).casefold()
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _key(value))


def _edit_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _date_code(header: str) -> tuple[str, re.Match[str]]:
    match = DATE_AT_END_RE.search(header)
    if match is None:
        raise ExtractionError(f"Date d'en-tete introuvable: {header!r}")
    code = (
        f"{match.group('year')}-{match.group('month')}{match.group('day')}"
        f"{match.group('suffix') or ''}"
    )
    return code, match


def _banner_chunks(line: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s{2,}", line.strip()) if part.strip()]


def _next_marker(marker: str) -> str:
    match = re.fullmatch(r"(?P<number>\d+)(?P<suffix>[A-Za-z]?)", marker)
    if match is None:
        return marker
    suffix = match.group("suffix")
    if suffix:
        return f"{match.group('number')}{chr(ord(suffix.lower()) + 1)}"
    return str(int(match.group("number")) + 1)


def parse_paragraph_start(
    text: str, expected_marker: str | None
) -> tuple[str, str] | None:
    """Lit le marqueur en evitant les numeros de page superposes.

    Quelques pages du PDF placent leur numero interne juste devant le vrai
    marqueur (par exemple ``9. 11. Et la meme Lumiere...``). Quand le marqueur
    attendu est present dans cette suite initiale, il est retenu et les numeros
    parasites qui le precedent sont retires.
    """

    clean = _clean_line(text)
    matches: list[re.Match[str]] = []
    position = 0
    while True:
        match = LEADING_MARKER_RE.match(clean, position)
        if match is None:
            break
        matches.append(match)
        position = match.end()
    if not matches:
        return None
    markers = [match.group(0).split(".", 1)[0].strip() for match in matches]
    chosen = 0
    if expected_marker is not None and expected_marker in markers:
        chosen = markers.index(expected_marker)
    marker = markers[chosen]
    body = _clean_line(clean[matches[chosen].end() :])
    return marker, body


def parse_banner_metadata(
    banner_lines: Iterable[BannerLine], header: str
) -> tuple[str, str, str]:
    """Retourne ``(titre, lieu, code_date)`` a partir du bandeau blanc.

    Le titre peut occuper deux lignes. Lorsque titre et lieu partagent une ligne,
    le PDF les separe par une large suite d'espaces, conservee dans le span PDF.
    """

    date_code, header_date = _date_code(header)
    header_base = _clean_line(header[: header_date.start()])
    title_parts: list[str] = []
    location_parts: list[str] = []
    location_started = False

    usable = [line for line in banner_lines if _clean_line(line.text)]
    if not usable:
        raise ExtractionError(f"Bandeau de sermon absent avant: {header!r}")

    for banner_line in usable:
        raw_chunks = _banner_chunks(banner_line.text)
        contains_date = DATE_AT_END_RE.search(_clean_line(banner_line.text)) is not None
        chunks: list[str] = []
        for raw in raw_chunks:
            chunk = _clean_line(raw)
            chunk = DATE_AT_END_RE.sub("", chunk).strip()
            if not chunk or WEEKDAY_RE.fullmatch(chunk):
                continue
            chunks.append(chunk)

        if not chunks:
            continue
        if contains_date:
            location_parts.extend(chunks)
            location_started = True
        elif len(chunks) >= 2 and not location_started:
            title_parts.append(chunks[0])
            location_parts.extend(chunks[1:])
            location_started = True
        elif location_started:
            location_parts.extend(chunks)
        else:
            title_parts.extend(chunks)

    title = _clean_line(" ".join(title_parts))
    location = _clean_line(" ".join(location_parts))
    if not title:
        raise ExtractionError(f"Titre vide dans le bandeau: {header!r}")

    reconstructed = _key(" ".join(part for part in (title, location) if part))
    header_key = _key(header_base)
    if reconstructed != header_key and _edit_distance(
        _compact_key(reconstructed), _compact_key(header_key)
    ) > 2:
        raise ExtractionError(
            "Le bandeau et l'en-tete repete ne concordent pas: "
            f"titre={title!r}, lieu={location!r}, en-tete={header!r}"
        )
    return title, location, date_code


def _line_style(line: dict[str, Any]) -> tuple[str, set[int], float]:
    spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
    text = "".join(str(span.get("text", "")) for span in spans)
    colors = {int(span.get("color", 0)) for span in spans}
    max_size = max((float(span.get("size", 0.0)) for span in spans), default=0.0)
    return text, colors, max_size


def _is_page_chrome(text: str, y: float, page_height: float) -> bool:
    clean = _clean_line(text)
    if y < 90.0 or y >= page_height - 107.0:
        return True
    if clean in {"Kosher", "Recherche :", "Shekinah Publications : Kosher"}:
        return True
    if clean.startswith("Page:") or clean.startswith("Date :"):
        return True
    return any(token in clean for token in FOOTER_TOKENS)


def extract_pdf(pdf_path: Path, root: Path = ROOT) -> FileExtraction:
    """Extrait et valide tous les sermons d'un PDF annuel SHP."""

    started = time.perf_counter()
    relative_source = pdf_path.resolve().relative_to(root.resolve()).as_posix()
    sermons: list[ExtractedSermon] = []
    warnings: list[str] = []
    current_sermon: ExtractedSermon | None = None
    current_para: _ParagraphBuilder | None = None
    pending_banner: list[BannerLine] = []
    banner_open = False
    pending_header_parts: list[str] = []
    pending_header_page = 0

    def finish_paragraph() -> None:
        nonlocal current_para
        if current_para is None:
            return
        text = _clean_line(" ".join(current_para.text_lines))
        if current_para.marker is None and not text:
            current_para = None
            return
        if current_sermon is None:
            raise ExtractionError(
                f"{relative_source}: paragraphe sans sermon, page {current_para.page_start}"
            )
        if current_para.marker is None:
            if current_sermon is not None and not current_sermon.paragraphs:
                current_para.marker = "1"
                warning = (
                    f"{current_sermon.date_code}: texte source sans marqueur, "
                    "marqueur 1 attribue"
                )
                if warning not in warnings:
                    warnings.append(warning)
            else:
                raise ExtractionError(
                    f"{relative_source}: numero de paragraphe absent, "
                    f"page {current_para.page_start}, {current_para.header!r}"
                )
        if not text:
            raise ExtractionError(
                f"{relative_source}: paragraphe {current_para.marker} vide, "
                f"page {current_para.page_start}"
            )
        if any(token in text for token in FOOTER_TOKENS):
            raise ExtractionError(
                f"{relative_source}: pied de page detecte dans le paragraphe "
                f"{current_para.marker}, page {current_para.page_start}"
            )
        current_sermon.paragraphs.append(
            ExtractedParagraph(
                marker=current_para.marker,
                text=text,
                page_start=current_para.page_start,
                page_end=current_para.page_end or current_para.page_start,
            )
        )
        current_para = None

    def start_pending_header() -> None:
        nonlocal current_sermon, current_para
        nonlocal pending_banner, banner_open
        nonlocal pending_header_parts, pending_header_page
        if not pending_header_parts:
            return
        header = _clean_line(" ".join(pending_header_parts))
        page_no = pending_header_page
        try:
            code, date_match = _date_code(header)
        except ExtractionError as exc:
            raise ExtractionError(
                f"{relative_source}, page {page_no}: {exc}"
            ) from exc
        if date_match.group("year_sep") != ".":
            warning = (
                f"{code}: separateur manquant dans la date PDF "
                f"({date_match.group(0).strip()!r})"
            )
            if warning not in warnings:
                warnings.append(warning)

        if current_sermon is None or current_sermon.date_code != code:
            try:
                title, location, banner_code = parse_banner_metadata(
                    pending_banner, header
                )
            except ExtractionError as exc:
                raise ExtractionError(
                    f"{relative_source}, page {page_no}: {exc}"
                ) from exc
            if banner_code != code:
                raise ExtractionError(
                    f"{relative_source}, page {page_no}: dates incompatibles "
                    f"({banner_code} / {code})"
                )
            banner_base = " ".join(part for part in (title, location) if part)
            if _key(banner_base) != _key(header[: date_match.start()]):
                warning = (
                    f"{code}: ecart typographique entre bandeau et en-tete "
                    f"({title!r} / {header!r})"
                )
                if warning not in warnings:
                    warnings.append(warning)
            current_sermon = ExtractedSermon(
                title=title,
                location=location,
                date_code=code,
                header=header,
                source_path=relative_source,
                source_page=page_no,
            )
            sermons.append(current_sermon)
        elif _key(current_sermon.header) != _key(header):
            raise ExtractionError(
                f"{relative_source}, page {page_no}: deux en-tetes differents "
                f"pour {code}: {current_sermon.header!r} / {header!r}"
            )

        pending_banner = []
        banner_open = False
        current_para = _ParagraphBuilder(
            header=header,
            page_start=page_no,
            page_end=page_no,
        )
        pending_header_parts = []
        pending_header_page = 0

    document = fitz.open(pdf_path)
    page_count = len(document)
    try:
        flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
        for page_index, page in enumerate(document):
            page_no = page_index + 1
            page_height = float(page.rect.height)
            page_dict = page.get_text("dict", flags=flags, sort=True)
            for block in page_dict.get("blocks", []):
                for line in block.get("lines", []):
                    raw_text, colors, max_size = _line_style(line)
                    if not raw_text.strip():
                        continue
                    y = float(line.get("bbox", (0.0, 0.0, 0.0, 0.0))[1])

                    # Le sous-titre eventuel du bandeau est blanc mais a 10 pt;
                    # seules les lignes principales titre/lieu/date sont a 16 pt.
                    is_banner = WHITE in colors and 14.0 <= max_size <= 20.0
                    is_header = BLUE in colors and max_size <= 11.5
                    is_chrome = _is_page_chrome(raw_text, y, page_height)

                    if is_header:
                        if pending_header_parts:
                            pending_text = _clean_line(" ".join(pending_header_parts))
                            if DATE_AT_END_RE.search(pending_text) is not None:
                                # En-tete orphelin en bas de page, repete au
                                # debut de la suivante avant le meme paragraphe.
                                start_pending_header()
                                finish_paragraph()
                        if not pending_header_parts:
                            finish_paragraph()
                            pending_header_page = page_no
                        pending_header_parts.append(_clean_line(raw_text))
                        continue

                    # Certains en-tetes longs occupent deux lignes bleues. Ils
                    # ne sont interpretes qu'au premier element non bleu.
                    if pending_header_parts:
                        pending_text = _clean_line(" ".join(pending_header_parts))
                        if DATE_AT_END_RE.search(pending_text) is None and is_chrome:
                            # Une ligne d'en-tete peut commencer en bas d'une
                            # page et sa date apparaitre en haut de la suivante.
                            continue
                    start_pending_header()

                    if is_banner:
                        if not banner_open:
                            finish_paragraph()
                            pending_banner = []
                            banner_open = True
                        pending_banner.append(BannerLine(raw_text, page_no, y))
                        continue

                    if is_chrome:
                        continue
                    if current_para is None:
                        continue

                    body = _clean_line(raw_text)
                    if not body:
                        continue
                    current_para.page_end = page_no
                    if current_para.marker is None:
                        expected_marker = None
                        if current_sermon is not None and current_sermon.paragraphs:
                            expected_marker = _next_marker(
                                current_sermon.paragraphs[-1].marker
                            )
                        parsed = parse_paragraph_start(body, expected_marker)
                        if parsed is None:
                            current_para.text_lines.append(body)
                            continue
                        current_para.marker, initial_text = parsed
                        if initial_text:
                            current_para.text_lines.append(initial_text)
                    else:
                        expected_marker = None
                        if current_sermon is not None and current_sermon.paragraphs:
                            expected_marker = _next_marker(
                                current_sermon.paragraphs[-1].marker
                            )
                        replacement = None
                        if (
                            expected_marker is not None
                            and current_para.marker != expected_marker
                            and not current_para.text_lines
                        ):
                            replacement = parse_paragraph_start(body, expected_marker)
                        if replacement is not None and replacement[0] == expected_marker:
                            current_para.marker, corrected_text = replacement
                            if corrected_text:
                                current_para.text_lines.append(corrected_text)
                        else:
                            current_para.text_lines.append(body)

        start_pending_header()
        finish_paragraph()
    finally:
        document.close()

    if not sermons:
        raise ExtractionError(f"Aucun sermon extrait de {relative_source}")

    seen_codes: set[str] = set()
    for sermon in sermons:
        if sermon.date_code in seen_codes:
            raise ExtractionError(
                f"{relative_source}: code sermon duplique: {sermon.date_code}"
            )
        seen_codes.add(sermon.date_code)
        if not sermon.paragraphs:
            raise ExtractionError(
                f"{relative_source}: sermon sans paragraphe: {sermon.date_code}"
            )
        markers = [paragraph.marker for paragraph in sermon.paragraphs]
        duplicate_markers = sorted(
            marker for marker in set(markers) if markers.count(marker) > 1
        )
        if duplicate_markers:
            warnings.append(
                f"{sermon.date_code}: marqueurs repetes {duplicate_markers[:10]}"
            )

    return FileExtraction(
        source_path=relative_source,
        page_count=page_count,
        sermons=sermons,
        warnings=warnings,
        elapsed_seconds=round(time.perf_counter() - started, 3),
    )


def discover_pdfs(source: Path, years: set[str] | None = None) -> list[Path]:
    pdfs = sorted(
        source.glob("*/*.pdf"),
        key=lambda path: (path.parent.name, path.name.casefold()),
    )
    if years:
        pdfs = [path for path in pdfs if path.parent.name in years]
    if not pdfs:
        raise ExtractionError(f"Aucun PDF annuel trouve dans {source}")
    return pdfs


def extract_corpus(pdfs: list[Path], workers: int) -> list[FileExtraction]:
    if workers <= 1 or len(pdfs) == 1:
        results = []
        for path in pdfs:
            result = extract_pdf(path)
            results.append(result)
            print(
                f"[{path.parent.name}] {len(result.sermons)} sermons, "
                f"{sum(len(s.paragraphs) for s in result.sermons)} paragraphes "
                f"({result.elapsed_seconds:.1f}s)",
                flush=True,
            )
        return results

    results: list[FileExtraction] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(extract_pdf, path): path for path in pdfs}
        for future in concurrent.futures.as_completed(futures):
            path = futures[future]
            result = future.result()
            results.append(result)
            print(
                f"[{path.parent.name}] {len(result.sermons)} sermons, "
                f"{sum(len(s.paragraphs) for s in result.sermons)} paragraphes "
                f"({result.elapsed_seconds:.1f}s)",
                flush=True,
            )
    return sorted(results, key=lambda item: item.source_path)


def validate_corpus(results: list[FileExtraction]) -> dict[str, Any]:
    sermons = [sermon for result in results for sermon in result.sermons]
    if not sermons:
        raise ExtractionError("Le corpus extrait est vide")
    codes = [sermon.date_code for sermon in sermons]
    duplicates = sorted(code for code in set(codes) if codes.count(code) > 1)
    if duplicates:
        raise ExtractionError(f"Codes sermon dupliques dans le corpus: {duplicates}")

    footer_hits: list[str] = []
    empty_texts: list[str] = []
    for sermon in sermons:
        for paragraph in sermon.paragraphs:
            if not paragraph.text.strip():
                empty_texts.append(f"{sermon.date_code}:{paragraph.marker}")
            if any(token in paragraph.text for token in FOOTER_TOKENS):
                footer_hits.append(f"{sermon.date_code}:{paragraph.marker}")
    if empty_texts:
        raise ExtractionError(f"Paragraphes vides: {empty_texts[:20]}")
    if footer_hits:
        raise ExtractionError(f"Pieds de page inclus: {footer_hits[:20]}")

    return {
        "pdf_count": len(results),
        "page_count": sum(result.page_count for result in results),
        "sermon_count": len(sermons),
        "paragraph_count": sum(len(sermon.paragraphs) for sermon in sermons),
        "warning_count": sum(len(result.warnings) for result in results),
        "by_year": {
            Path(result.source_path).parent.name: {
                "pages": result.page_count,
                "sermons": len(result.sermons),
                "paragraphs": sum(len(s.paragraphs) for s in result.sermons),
                "warnings": result.warnings,
            }
            for result in results
        },
    }


def _backup_database(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"project_on-before-shp-import-{stamp}.db"
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


def _search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", _clean_line(value).lower())
    without_accents = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", without_accents)).strip()


def apply_import(
    db_path: Path,
    results: list[FileExtraction],
    backup_dir: Path | None,
    vacuum: bool,
    metadata_only: bool = False,
) -> dict[str, Any]:
    if not db_path.exists():
        raise ExtractionError(f"Base de donnees introuvable: {db_path}")
    backup_path = _backup_database(db_path, backup_dir) if backup_dir else None
    sermons = [sermon for result in results for sermon in result.sermons]
    sermons.sort(key=lambda item: item.date_code)

    connection = sqlite3.connect(db_path, timeout=120.0)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 120000")
        connection.execute("BEGIN IMMEDIATE")
        expose_before = int(
            connection.execute(
                "SELECT COUNT(*) FROM sermon WHERE COALESCE(date, '') LIKE 'BK-AGES%'"
            ).fetchone()[0]
        )
        expose_paragraphs_before = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM sermon_paragraph p
                JOIN sermon s ON s.id = p.sermon_id
                WHERE COALESCE(s.date, '') LIKE 'BK-AGES%'
                """
            ).fetchone()[0]
        )
        preserved_before = {
            str(row[0]): {"sermons": int(row[1]), "paragraphs": int(row[2])}
            for row in connection.execute(
                """
                SELECT s.tradition, COUNT(DISTINCT s.id), COUNT(p.id)
                FROM sermon s
                LEFT JOIN sermon_paragraph p ON p.sermon_id = s.id
                WHERE s.tradition <> 'SHP'
                  AND COALESCE(s.date, '') NOT LIKE 'BK-AGES%'
                GROUP BY s.tradition
                ORDER BY s.tradition
                """
            ).fetchall()
        }
        if expose_before == 0:
            raise ExtractionError(
                "Aucun chapitre Expose n'est present; suppression interrompue"
            )

        connection.execute("DROP TABLE IF EXISTS sermon_paragraph_fts")
        connection.execute(
            """
            DELETE FROM sermon_paragraph
            WHERE sermon_id IN (
                SELECT id FROM sermon
                WHERE tradition = 'SHP'
                  AND COALESCE(date, '') NOT LIKE 'BK-AGES%'
            )
            """
        )
        connection.execute(
            """
            DELETE FROM sermon
            WHERE tradition = 'SHP'
              AND COALESCE(date, '') NOT LIKE 'BK-AGES%'
            """
        )

        sermon_sql = """
            INSERT INTO sermon
                (title, date, tradition, language, source_path, sort_key,
                 location, canonical_title, title_search)
            VALUES (?, ?, 'SHP', 'fr', ?, ?, ?, ?, ?)
        """
        paragraph_sql = """
            INSERT INTO sermon_paragraph
                (sermon_id, paragraph_no, ref, text, marker)
            VALUES (?, ?, ?, ?, ?)
        """
        for sermon in sermons:
            canonical = sermon.title
            title_search = _search_key(
                " ".join(
                    (
                        sermon.title,
                        sermon.location,
                        sermon.date_code,
                        "SHP",
                        "fr",
                    )
                )
            )
            cursor = connection.execute(
                sermon_sql,
                (
                    sermon.title,
                    sermon.date_code,
                    sermon.source_path,
                    sermon.date_code,
                    sermon.location,
                    canonical,
                    title_search,
                ),
            )
            sermon_id = int(cursor.lastrowid)
            if metadata_only:
                # Mode catalogue : seul le titre exact, la date et le lieu
                # sont importes; le texte reste dans les PDF sources.
                continue
            rows = []
            for ordinal, paragraph in enumerate(sermon.paragraphs, start=1):
                marker = f"§{paragraph.marker}"
                rows.append(
                    (
                        sermon_id,
                        ordinal,
                        f"{sermon.title} {marker}",
                        paragraph.text,
                        marker,
                    )
                )
            connection.executemany(paragraph_sql, rows)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    # Recalcule titres canoniques, marqueurs et index FTS avec le code de l'app.
    sys.path.insert(0, str(ROOT))
    from app.database.connection import Database, DatabaseConfig

    database = Database(DatabaseConfig(db_path=db_path))
    with database.connect() as connection:
        database._ensure_sermon_search_metadata(connection)
    if vacuum:
        database._reclaim_space()

    connection = sqlite3.connect(db_path)
    try:
        preserved_after = {
            str(row[0]): {"sermons": int(row[1]), "paragraphs": int(row[2])}
            for row in connection.execute(
                """
                SELECT s.tradition, COUNT(DISTINCT s.id), COUNT(p.id)
                FROM sermon s
                LEFT JOIN sermon_paragraph p ON p.sermon_id = s.id
                WHERE s.tradition <> 'SHP'
                  AND COALESCE(s.date, '') NOT LIKE 'BK-AGES%'
                GROUP BY s.tradition
                ORDER BY s.tradition
                """
            ).fetchall()
        }
        actual = {
            "expose_sermons": int(
                connection.execute(
                    "SELECT COUNT(*) FROM sermon WHERE COALESCE(date, '') LIKE 'BK-AGES%'"
                ).fetchone()[0]
            ),
            "expose_paragraphs": int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM sermon_paragraph p
                    JOIN sermon s ON s.id = p.sermon_id
                    WHERE COALESCE(s.date, '') LIKE 'BK-AGES%'
                    """
                ).fetchone()[0]
            ),
            "shp_sermons": int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM sermon
                    WHERE tradition = 'SHP' AND COALESCE(date, '') NOT LIKE 'BK-AGES%'
                    """
                ).fetchone()[0]
            ),
            "shp_paragraphs": int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM sermon_paragraph p
                    JOIN sermon s ON s.id = p.sermon_id
                    WHERE s.tradition = 'SHP'
                      AND COALESCE(s.date, '') NOT LIKE 'BK-AGES%'
                    """
                ).fetchone()[0]
            ),
            "preserved_translations": preserved_after,
            "fts_rows": int(
                connection.execute(
                    "SELECT COUNT(*) FROM sermon_paragraph_fts"
                ).fetchone()[0]
            ),
            "all_paragraphs": int(
                connection.execute("SELECT COUNT(*) FROM sermon_paragraph").fetchone()[0]
            ),
        }
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        connection.close()

    expected_sermons = len(sermons)
    expected_paragraphs = (
        0 if metadata_only else sum(len(sermon.paragraphs) for sermon in sermons)
    )
    if actual["expose_sermons"] != expose_before:
        raise ExtractionError("Le nombre de chapitres Expose a change apres l'import")
    if actual["expose_paragraphs"] != expose_paragraphs_before:
        raise ExtractionError("Les paragraphes Expose ont change apres l'import")
    if actual["shp_sermons"] != expected_sermons:
        raise ExtractionError("Le compte final des sermons SHP est incorrect")
    if actual["shp_paragraphs"] != expected_paragraphs:
        raise ExtractionError("Le compte final des paragraphes SHP est incorrect")
    if preserved_after != preserved_before:
        raise ExtractionError(
            "Une traduction non-SHP a change pendant l'import: "
            f"avant={preserved_before}, apres={preserved_after}"
        )
    if actual["fts_rows"] != actual["all_paragraphs"]:
        raise ExtractionError("L'index de recherche FTS n'est pas synchronise")
    if integrity.lower() != "ok":
        raise ExtractionError(f"PRAGMA integrity_check: {integrity}")

    return {
        "backup_path": str(backup_path) if backup_path else None,
        "database_path": str(db_path),
        "integrity_check": integrity,
        "metadata_only": metadata_only,
        **actual,
    }


def write_report(
    report_path: Path,
    source: Path,
    db_path: Path,
    summary: dict[str, Any],
    results: list[FileExtraction],
    applied: dict[str, Any] | None,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": str(source),
        "database": str(db_path),
        "summary": summary,
        "applied": applied,
        "sermons": [
            {
                "date_code": sermon.date_code,
                "title": sermon.title,
                "location": sermon.location,
                "source_path": sermon.source_path,
                "source_page": sermon.source_page,
                "paragraph_count": len(sermon.paragraphs),
                "first_marker": sermon.paragraphs[0].marker,
                "last_marker": sermon.paragraphs[-1].marker,
            }
            for result in results
            for sermon in result.sermons
        ],
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyse les PDF annuels SHP et remplace uniquement les sermons SHP "
            "en preservant VGR, BSS et Expose."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--years",
        nargs="*",
        help="Sous-ensemble de dossiers a analyser (exemple: --years 47 48).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Nombre de PDF analyses en parallele (defaut: 4).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Applique le nettoyage/import. Sans cette option: analyse seulement.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help=(
            "Avec --apply : n'importe que le catalogue (titre exact du PDF, "
            "date, lieu) sans le texte des paragraphes."
        ),
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="N'enregistre pas la copie de securite de la base avant l'import.",
    )
    parser.add_argument(
        "--no-vacuum",
        action="store_true",
        help="Ne compacte pas la base apres le remplacement.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source.resolve()
    db_path = args.db.resolve()
    report_path = args.report.resolve()
    years = set(args.years or []) or None
    if args.apply and years is not None:
        raise ExtractionError(
            "--apply exige le corpus complet; retirez --years pour eviter une base partielle"
        )
    if args.metadata_only and not args.apply:
        raise ExtractionError("--metadata-only n'a de sens qu'avec --apply")
    pdfs = discover_pdfs(source, years)
    print(f"Analyse de {len(pdfs)} PDF SHP avec {max(1, args.workers)} worker(s)...")
    results = extract_corpus(pdfs, max(1, args.workers))
    summary = validate_corpus(results)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    applied = None
    if args.apply:
        backup_dir = None if args.no_backup else ROOT / "tmp" / "db-backups"
        applied = apply_import(
            db_path=db_path,
            results=results,
            backup_dir=backup_dir,
            vacuum=not args.no_vacuum,
            metadata_only=args.metadata_only,
        )
        print(json.dumps(applied, ensure_ascii=False, indent=2), flush=True)

    write_report(report_path, source, db_path, summary, results, applied)
    print(f"Rapport: {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExtractionError as error:
        print(f"ERREUR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(2) from error
