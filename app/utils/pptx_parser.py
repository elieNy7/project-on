from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

# Bornes de robustesse pour les imports (cf. plan du 2026-09-17, lot 4).
MAX_PPTX_SLIDES = 1000
MAX_XML_UNCOMPRESSED_BYTES = 64 * 1024 * 1024  # 64 Mo par partie XML


class PptxImportError(RuntimeError):
    """Import PPTX impossible ou incomplet (fichier illisible, corrompu).

    Le message est destiné à être affiché tel quel : il explique la cause
    réelle au lieu de retourner silencieusement une liste partielle.
    """


def _read_member(zf: zipfile.ZipFile, name: str) -> bytes:
    """Lit un membre ZIP en refusant de décompresser plus que la borne."""
    with zf.open(name) as handle:
        data = handle.read(MAX_XML_UNCOMPRESSED_BYTES + 1)
    if len(data) > MAX_XML_UNCOMPRESSED_BYTES:
        raise PptxImportError(
            f"Partie XML trop volumineuse dans la présentation : {name} "
            f"(limite {MAX_XML_UNCOMPRESSED_BYTES // (1024 * 1024)} Mo décompressés)."
        )
    return data


def _safe_xml(data: bytes, name: str) -> ET.Element:
    """Parse XML sans DTD : les parties OPC n'en contiennent jamais.

    Refuser toute déclaration ``<!DOCTYPE``/``<!ENTITY`` avant le parsing
    élimine l'expansion d'entités (« billion laughs ») sur un fichier
    apporté par un tiers ; une variante minuscule serait de toute façon
    rejetée par le parseur comme mal formée.
    """
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise PptxImportError(
            f"Déclaration de type de document interdite dans {name} : "
            "présentation refusée."
        )
    return ET.fromstring(data)


def _slide_parts_in_presentation_order(zf: zipfile.ZipFile) -> list[str]:
    """Retourne les parties de slides dans l'ordre officiel du paquet OPC.

    L'ordre de projection est défini par ``ppt/presentation.xml`` via ses
    relations (``ppt/_rels/presentation.xml.rels``), PAS par les numéros des
    fichiers ``ppt/slides/slideN.xml`` : un fichier réordonné (glisser-déposer
    de slides dans PowerPoint) doit être lu dans l'ordre de la présentation.

    Lève ``PptxImportError`` si une relation sldId ne pointe vers rien :
    un import partiel silencieux est inacceptable.
    """
    presentation = _safe_xml(_read_member(zf, "ppt/presentation.xml"), "ppt/presentation.xml")
    if "presentation" not in presentation.tag:
        raise PptxImportError("ppt/presentation.xml inattendu dans le paquet.")

    rels_name = "ppt/_rels/presentation.xml.rels"
    if rels_name not in zf.namelist():
        raise PptxImportError(
            "Relations de présentation absentes "
            "(ppt/_rels/presentation.xml.rels) : paquet invalide."
        )
    rels_root = _safe_xml(_read_member(zf, rels_name), rels_name)

    rel_targets: dict[str, str] = {}
    for rel in rels_root:
        r_id = rel.get("Id", "")
        target = rel.get("Target", "")
        mode = rel.get("TargetMode", "Internal")
        if not r_id or not target or mode == "External":
            continue
        rel_targets[r_id] = target

    slide_tree = presentation.find(
        "{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst"
    )
    if slide_tree is None:
        # Repli tolérant : chercher n'importe quel élément sldIdLst.
        for element in presentation.iter():
            if element.tag.split("}")[-1] == "sldIdLst":
                slide_tree = element
                break
    if slide_tree is None:
        return []

    parts: list[str] = []
    for sld_id in slide_tree:
        rid = sld_id.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        if not rid:
            continue
        target = rel_targets.get(rid)
        if not target:
            raise PptxImportError(
                f"Relation de slide manquante dans presentation.xml.rels : {rid}. "
                "La présentation est incomplète ou corrompue."
            )
        normalized = target.replace("\\", "/")
        # Les cibles sont relatives au dossier "ppt/".
        if normalized.startswith("/"):
            part = normalized.lstrip("/")
        elif normalized.startswith("ppt/"):
            part = normalized
        else:
            part = f"ppt/{normalized}"
        parts.append(part)

    return parts


def extract_slides_from_pptx(pptx_path: Path) -> list[str]:
    """Extract text content from each slide in official presentation order.

    L'ordre suit ``ppt/presentation.xml`` (sldIdLst + relations), pas les
    numéros de fichiers.  Lève ``PptxImportError`` au lieu de renvoyer
    silencieusement une liste partielle quand le fichier est illisible,
    corrompu, contient des slides sans texte détecté ou dépasse les bornes.
    """
    path = Path(pptx_path)
    if not path.is_file():
        raise PptxImportError(f"Fichier introuvable : {path}")
    if not zipfile.is_zipfile(path):
        raise PptxImportError(
            f"Fichier illisible (pas une présentation PowerPoint valide) : {path.name}"
        )

    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "ppt/presentation.xml" not in zf.namelist():
                raise PptxImportError(
                    "Présentation invalide : ppt/presentation.xml est absent."
                )

            parts = _slide_parts_in_presentation_order(zf)
            if not parts:
                raise PptxImportError(
                    "Aucune slide référencée dans ppt/presentation.xml "
                    "(sldIdLst vide ou absente)."
                )

            names = zf.namelist()
            missing = [part for part in parts if part not in names]
            if missing:
                raise PptxImportError(
                    "Slides manquantes dans le paquet : " + ", ".join(missing[:5])
                    + ("…" if len(missing) > 5 else "")
                    + ". Import interrompu pour éviter une présentation partielle."
                )
            if len(parts) > MAX_PPTX_SLIDES:
                raise PptxImportError(
                    f"Présentation trop grande : {len(parts)} slides "
                    f"(maximum {MAX_PPTX_SLIDES})."
                )

            slides: list[str] = []
            for part_name in parts:
                payload = _read_member(zf, part_name)
                root = _safe_xml(payload, part_name)

                texts: list[str] = []
                for p in root.iter():
                    if p.tag.endswith("}p"):
                        p_text = "".join(
                            [
                                t.text
                                for t in p.iter()
                                if t.tag.endswith("}t") and t.text
                            ]
                        )
                        if p_text.strip():
                            texts.append(p_text.strip())

                slide_text = "\n".join(texts).strip()
                if slide_text:
                    slides.append(slide_text)

            return slides

    except PptxImportError:
        raise
    except (zipfile.BadZipFile, ET.ParseError, OSError) as exc:
        raise PptxImportError(
            f"Lecture de la présentation impossible : {path.name} ({exc})"
        ) from exc


def _clean_stanza_text(text: str, title: str) -> str:
    """Remove the hymn title from the stanza ONLY if it appears as a distinct header.
    Does NOT remove the title if it is part of the lyrics/sentence.
    """
    cleaned = text.strip()
    title_lower = title.lower().strip()

    if not title_lower:
        return cleaned

    # 1. Check if the text matches the title exactly (case-insensitive)
    if cleaned.lower() == title_lower:
        return ""

    # 2. Check if the text starts with the title followed by a distinct separator
    #    or if the title is repeated (e.g. "Title Title! Lyrics")
    if cleaned.lower().startswith(title_lower):
        remaining = cleaned[len(title) :]  # No strip yet to check separator

        # Valid separators indicating a header:
        # - Newline (if we had them, but inputs are usually stripped of newlines by extract_slides)
        # - " - ", " : ", " | "
        # - Repetition of title (Title... Title...)

        # Check for repetition first (most common case for "Title\nTitle! Lyrics")
        # "Amazing Grace Amazing Grace!..."
        if remaining.strip().lower().startswith(title_lower):
            # Remove the first occurrence (the header)
            return remaining.strip()

        # Case: "Title\nLyrics". This is common in PowerPoint slides where
        # the title box is exported before the lyrics box.
        if remaining.startswith(("\n", "\r")):
            return remaining.strip()

        # Check for clear separators
        # We look at the immediate next chars

        # If remaining starts with space/punctuation that is a separator
        stripped_remaining = remaining.strip()

        # If ' - ', ' : ', ' | ', ' – ', ' — '
        separators = ["-", "–", "—", ":", "|", "."]
        # Note: "." might be "St. John", so be careful. But "Title." is usually header.

        if not stripped_remaining:
            # Case: "Title " -> Empty.
            return ""

        # If it starts with non-word separator char (except typical punctuation found in lyrics like '!', '?', ',')
        # Typical lyric punctuation: '!', '?', ',', ';', '’', '\''

        should_remove = False

        # Case: "Title - Subtitle"
        for sep in separators:
            if stripped_remaining.startswith(sep):
                should_remove = True
                remaining = stripped_remaining[len(sep) :]  # Advance past sep
                break

        if should_remove:
            return remaining.strip()

    # We do NOT remove title if it's just a prefix of a sentence (e.g. "Amazing Grace! how sweet...")
    # We also REMOVED the "search inside string" logic which was causing false positives.

    return cleaned.strip()


def _is_chorus_slide(text: str) -> bool:
    """Check if a slide is a chorus.
    Matches:
    - Starts with Chœur, Choeur, Chorus, Refrain (case-insensitve)
    - Maybe preceded by a number/bullet: "1. Refrain", "- Refrain"
    - Maybe followed by colon: "Refrain:"
    """
    text_lower = text.strip().lower()
    # Regex to match start of string, optional numbering/bullets, then chorus keyword
    # ^(?:[\d\.\-\)\s]*)\b(ch[oeœ]ur|chorus|refrain)\b
    return bool(
        re.match(
            r"(?i)^(?:[\d.\-)\s]*)(?:dernier\s+)?"
            r"\b(ch(?:oe|œ)urs?|chorus|refrain)",
            text_lower,
        )
    )


def _extract_chorus_text(text: str) -> str:
    """Extract chorus text, removing the label."""
    # Remove the label found by _is_chorus_slide
    # We want to keep the text AFTER the label.
    # Regex: replace the match with empty string.
    pattern = (
        r"(?i)^(?:[\d.\-)\s]*)(?:dernier\s+)?"
        r"\b(ch(?:oe|œ)urs?|chorus|refrain)[\s:：\-–—]*"
    )
    cleaned = re.sub(pattern, "", text.strip())
    return cleaned.strip()


def _normalize_for_match(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_source_header(text: str, title: str = "") -> str:
    """Remove leading source headers such as '282. TITLE ( Eb ) *' from a slide."""
    cleaned = re.sub(r"[ \t]+", " ", str(text or "").strip())
    if not cleaned:
        return ""

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) >= 2:
        if re.match(r"^\d{3,4}[a-z]?\.?\s*\S+", lines[0], re.IGNORECASE):
            cleaned = "\n".join(lines[1:]).strip()
            lines = lines[1:]

    if len(lines) >= 2:
        first_key = _normalize_for_match(lines[0])
        title_key = _normalize_for_match(title)
        next_starts_content = bool(
            re.match(
                r"^(?:\d{1,2}\s*[.\-)]\s*|[*•\-]\s*|ch[oeœ]ur\b|refrain\b)",
                lines[1],
                re.IGNORECASE,
            )
        )
        first_letters = [ch for ch in lines[0] if ch.isalpha()]
        first_is_title_like = bool(first_letters) and (
            sum(1 for ch in first_letters if ch.isupper()) / len(first_letters) >= 0.65
        )
        if next_starts_content and (
            (title_key and (first_key.startswith(title_key) or title_key.startswith(first_key)))
            or first_is_title_like
        ):
            cleaned = "\n".join(lines[1:]).strip()

    # Most AD slides start with a catalogue number, an uppercase title, and
    # often a chord marker before the actual lyric.
    chord_header = re.match(
        r"^\s*\d{1,4}[a-z]?\.?\s*.+?\(\s*[A-G](?:[#b])?m?\s*\)\s*[*.:\-–—]*\s*(.+)$",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if chord_header:
        return chord_header.group(1).lstrip("*.:-–—• ").strip()

    # Same pattern without parentheses, e.g. "29. J'AI RESOLU Bb".
    bare_chord_header = re.match(
        r"^\s*\d{1,4}[a-z]?\.?\s*.+?\s+[A-G](?:[#b])?m?\s*[*.:\-–—]+\s*(.+)$",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if bare_chord_header:
        return bare_chord_header.group(1).lstrip("*.:-–—• ").strip()

    uppercase_title_header = re.match(
        r"^\s*\d{1,4}[a-z]?\.?\s*([A-ZÀ-Ý0-9'’ ,!?;:\-]{3,}?)\s+((?:[A-ZÀ-Ý]\s+)?[A-ZÀ-Ýa-zà-ÿ][a-zà-ÿ].*)$",
        cleaned,
        flags=re.DOTALL,
    )
    if uppercase_title_header:
        return uppercase_title_header.group(2).lstrip("*.:-–—• ").strip()

    numbered = re.match(
        r"^\s*\d{1,4}[a-z]?\.?\s*([A-ZÀ-Ý0-9'’ ,!?;:\-]+?)\s+(.+)$",
        cleaned,
        flags=re.DOTALL,
    )
    if not numbered:
        return cleaned.lstrip("*•- ").strip()

    header = numbered.group(1).strip(" .:-–—")
    body = numbered.group(2).strip()
    if len(_normalize_for_match(header)) < 3:
        return cleaned

    body_key = _normalize_for_match(body)
    header_key = _normalize_for_match(header)
    title_key = _normalize_for_match(title)
    if body_key.startswith(header_key) or (
        title_key and header_key.startswith(title_key)
    ):
        return body.lstrip("*.:-–— ").strip()
    return cleaned.lstrip("*•- ").strip()


def _split_numbered_compound_stanza(text: str) -> list[str]:
    """Split one slide that contains multiple numbered couplets."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return []

    marker_re = re.compile(r"(?:^|\n)\s*(\d{1,2})\.\s*")
    matches = list(marker_re.finditer(cleaned))
    if len(matches) < 2:
        return [cleaned]

    prefix = cleaned[: matches[0].start()].strip()
    parts: list[str] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        body = cleaned[start:end].strip()
        if not body:
            continue
        if idx == 0 and prefix:
            prefix_key = _normalize_for_match(prefix)
            body_key = _normalize_for_match(body)
            if prefix_key and not body_key.startswith(prefix_key):
                body = f"{prefix}\n{body}"
        parts.append(body.lstrip("*•- ").strip())

    return parts or [cleaned]


def _strip_leading_verse_marker(text: str) -> str:
    return re.sub(r"^\s*\d{1,2}\s*[.\-)]\s*", "", str(text or "").strip()).strip()


def _detect_repeated_lyric_block(
    slides: list[dict[str, Any]],
) -> tuple[str, tuple[str, ...]] | None:
    """Find a repeated multi-line refrain embedded inside verse slides."""

    candidates: dict[tuple[str, ...], set[int]] = {}
    originals: dict[tuple[str, ...], str] = {}
    for slide_index, slide in enumerate(slides):
        if slide["is_chorus"]:
            continue
        lines = [line.strip() for line in str(slide["text"]).splitlines() if line.strip()]
        keys = [_normalize_for_match(line) for line in lines]
        for start in range(len(lines)):
            for end in range(start + 1, min(len(lines), start + 8) + 1):
                block_keys = tuple(keys[start:end])
                if not all(block_keys):
                    continue
                block_text = "\n".join(lines[start:end])
                if len(block_keys) == 1 and len(block_text) < 40:
                    continue
                if len(block_keys) >= 2 and len(block_text) < 35:
                    continue
                candidates.setdefault(block_keys, set()).add(slide_index)
                originals.setdefault(block_keys, block_text)

    minimum_occurrences = 2 if len(slides) <= 8 else 3
    valid = [
        (keys, indexes)
        for keys, indexes in candidates.items()
        if len(indexes) >= minimum_occurrences
        and (len(keys) >= 2 or len(indexes) >= 3)
    ]
    if not valid:
        return None

    keys, _indexes = max(
        valid,
        key=lambda item: (
            len(item[1]) * len(originals[item[0]]),
            len(item[0]),
            len(item[1]),
        ),
    )
    return originals[keys], keys


def _remove_repeated_block(text: str, block_keys: tuple[str, ...]) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    keys = [_normalize_for_match(line) for line in lines]
    width = len(block_keys)
    for start in range(0, len(keys) - width + 1):
        if tuple(keys[start : start + width]) == block_keys:
            return "\n".join(lines[:start] + lines[start + width :]).strip()
    return "\n".join(lines).strip()


def _post_process_stanzas(stanzas: list[str], title: str) -> list[str]:
    result: list[str] = []
    for stanza in stanzas:
        cleaned = _strip_source_header(stanza, title)
        if _is_chorus_slide(cleaned):
            if cleaned.strip():
                result.append(cleaned.strip())
            continue
        result.extend(
            _strip_leading_verse_marker(part)
            for part in _split_numbered_compound_stanza(cleaned)
        )
    return [s.strip() for s in result if s and s.strip()]


def parse_slides_as_hymn(slides: list[str], title: str) -> dict[str, Any] | None:
    """Core logic to parse a list of slide texts into a hymn structure."""
    if not slides:
        return None

    # First pass: clean slides, identify chorus, and track slide order
    cleaned_slides: list[dict[str, Any]] = []  # {"text": ..., "is_chorus": bool}
    chorus_text: str = ""
    chorus_label: str = "Chœur:"
    explicit_chorus_texts: list[str] = []

    for slide_text in slides:
        # Check for chorus BEFORE cleaning (cleaning might remove labels if title matches label, unlikely but safe)
        is_chorus_label = _is_chorus_slide(slide_text)

        cleaned = _strip_source_header(_clean_stanza_text(slide_text, title), title)
        if not cleaned or cleaned.lower() == title.lower():
            continue

        if is_chorus_label:
            extracted = _extract_chorus_text(slide_text)
            extracted = _clean_stanza_text(extracted, title)
            if not chorus_text and extracted:
                chorus_text = extracted
                # Detect label from original text for display preference
                if "refrain" in slide_text.lower():
                    chorus_label = "Refrain:"
            if extracted:
                explicit_chorus_texts.append(extracted)
            cleaned_slides.append({"text": extracted, "is_chorus": True})
        else:
            cleaned_slides.append({"text": cleaned, "is_chorus": False})

    if not cleaned_slides:
        return None

    # Detect a refrain embedded at the end (or middle) of several verse slides.
    if not chorus_text:
        repeated = _detect_repeated_lyric_block(cleaned_slides)
        if repeated is not None:
            chorus_text, block_keys = repeated
            for slide in cleaned_slides:
                remainder = _remove_repeated_block(slide["text"], block_keys)
                if remainder != slide["text"]:
                    slide["text"] = remainder
                    slide["is_chorus"] = not bool(remainder)

    # Whole-slide implicit chorus detection.
    if not chorus_text:
        texts = [s["text"] for s in cleaned_slides]
        counts = Counter(texts)
        total_slides = len(texts)

        # Heuristics for implicit chorus:
        # 1. Repeats >= 2 times AND (is > 25% of total OR total slides <= 5)
        # 2. appears at even positions? (Too complex)

        found_implicit = False
        for txt, cnt in counts.most_common():
            if cnt < 2:
                break

            # If it's the most common and appears significantly
            if cnt >= 2:
                # Strengthening the heuristic:
                # If total slides is small (e.g., 4 slides: V1, C, V2, C), 30% is 1.2. So 2 counts is enough.
                # If total slides is large (e.g. 20), 2 counts might be accidental repetition.
                # Let's say if it repeats >= 3 times, it's definitely chorus.
                # If it repeats 2 times, we check percentage or if it's the ONLY repeated slide.

                is_valid = False
                if cnt >= 3 or (
                    cnt == 2 and (total_slides <= 8 or cnt >= total_slides * 0.2)
                ):
                    is_valid = True

                if is_valid:
                    chorus_text = txt
                    chorus_label = "Chœur:"  # Default
                    found_implicit = True
                    break

        if found_implicit:
            for s in cleaned_slides:
                if s["text"] == chorus_text:
                    s["is_chorus"] = True

    unique_explicit_choruses = {
        _normalize_for_match(text) for text in explicit_chorus_texts if text.strip()
    }
    if len(unique_explicit_choruses) > 1:
        # Bilingual/multi-refrain decks need their original slide order; using
        # only the first refrain would silently discard the other language.
        ordered_stanzas = [
            f"Chœur:\n{slide['text']}" if slide["is_chorus"] else slide["text"]
            for slide in cleaned_slides
            if slide["text"]
        ]
        stanzas = _post_process_stanzas(ordered_stanzas, title)
        if not stanzas:
            return None
        return _build_hymn_result(title, stanzas)

    # Collect unique verses (skip chorus slides)
    verses: list[str] = []
    for s in cleaned_slides:
        if not s["is_chorus"] and s["text"]:
            verses.append(s["text"])

    if not verses:
        return None

    # Build final stanzas: verse, chorus, verse, chorus, ...
    stanzas: list[str] = []
    for verse in verses:
        stanzas.append(verse)
        if chorus_text:
            stanzas.append(f"{chorus_label}\n{chorus_text}")

    stanzas = _post_process_stanzas(stanzas, title)
    if not stanzas:
        return None

    return _build_hymn_result(title, stanzas)


def _build_hymn_result(title: str, stanzas: list[str]) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    verse_no = 0
    chorus_no = 0
    for stanza in stanzas:
        is_chorus = _is_chorus_slide(stanza)
        if is_chorus:
            chorus_no += 1
            label = "Refrain" if chorus_no == 1 else f"Refrain {chorus_no}"
        else:
            verse_no += 1
            label = f"Strophe {verse_no}"
        sections.append({"text": stanza, "label": label, "is_chorus": is_chorus})

    return {
        "title": title,
        "stanzas": stanzas,
        "sections": sections,
    }


def parse_pptx_as_hymn(pptx_path: Path) -> dict[str, Any] | None:
    """Parse a PPTX file as a hymn.

    Lève ``PptxImportError`` si le fichier est illisible ou corrompu (aucune
    réussite silencieuse partielle).  Retourne None seulement si le paquet est
    valide mais ne contient aucun texte exploitable.
    """
    path = Path(pptx_path)
    title = path.stem

    slides = extract_slides_from_pptx(path)
    return parse_slides_as_hymn(slides, title)


def parse_pptx_folder(folder_path: Path) -> list[dict[str, Any]]:
    """Parse all PPTX files in a folder as hymns.

    Retourne la liste des cantiques extraits.  Lève ``PptxImportError`` si un
    fichier est illisible (message listant le fichier fautif) : un dossier ne
    doit jamais produire un bilan qui ignore des échecs de lecture.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        return []

    hymns: list[dict[str, Any]] = []
    failed: list[str] = []
    for pattern in ("*.pptx", "*.ppsx"):
        for pptx_file in sorted(folder.glob(pattern)):
            try:
                hymn = parse_pptx_as_hymn(pptx_file)
            except PptxImportError as exc:
                failed.append(f"{pptx_file.name} : {exc}")
                continue
            if hymn:
                hymns.append(hymn)

    if failed:
        raise PptxImportError(
            "Import partiel refusé — fichiers illisibles :\n- " + "\n- ".join(failed)
        )

    return hymns
