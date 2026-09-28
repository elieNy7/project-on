"""Import de chants depuis d'autres logiciels.

- **OpenLyrics** (XML, OpenLP, FreeWorship…) : ``<song><properties><titles>``
  et ``<lyrics><verse name="v1|c1|b1">`` ; l'ordre ``<verseOrder>`` est
  respecté (refrain répété là où le fichier le demande) ;
- **OpenSong** (XML sans extension ou .xml) : ``<song><title>``,
  ``<lyrics>`` avec des marqueurs ``[V1]``, ``[C]``, ``[B]`` ;
- **CCLI SongSelect** texte (.txt) : blocs « Verse 1 », « Chorus »,
  « Couplet 1 », « Refrain »… séparés par des lignes vides, pied de page
  « CCLI Song # … » ignoré ; et .usr (format SongSelect « USR »).

Chaque lecteur renvoie ``{"title", "number", "stanzas": [(texte, refrain)]}``.
"""

from __future__ import annotations

import configparser
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SONG_FILE_FILTER = (
    "Chants (*.xml *.txt *.usr *.sng);;OpenLyrics / OpenSong (*.xml);;"
    "CCLI SongSelect (*.txt *.usr);;Tous les fichiers (*)"
)

_CHORUS_NAMES = re.compile(
    r"^(?:c(?=\d|[a-z]?$)|chorus|refrain|ch(?:oe|œ)ur|pre-?chorus|pré-?refrain)",
    re.IGNORECASE
)
_SECTION_HEADER = re.compile(
    r"^\s*(?:verse|couplet|strophe|chorus|refrain|ch(?:oe|œ)ur|bridge|pont|"
    r"pre-?chorus|pré-?refrain|tag|ending|fin|intro|outro)\b[\s\d.:]*$",
    re.IGNORECASE,
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children(element, name: str):
    return [c for c in element if _local(c.tag) == name]


def _find(element, *path: str):
    current = [element]
    for name in path:
        current = [c for node in current for c in _children(node, name)]
        if not current:
            return None
    return current[0]


def _lines_text(element) -> str:
    """Texte d'un ``<lines>`` OpenLyrics : ``<br/>`` = retour à la ligne."""
    parts: list[str] = []

    def walk(node) -> None:
        if node.text:
            parts.append(node.text)
        for child in node:
            name = _local(child.tag)
            if name == "br":
                parts.append("\n")
            elif name == "comment":
                pass
            else:
                walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(element)
    text = "".join(parts)
    return "\n".join(line.strip() for line in text.split("\n") if line.strip())


def parse_openlyrics(root) -> dict[str, Any]:
    title_el = _find(root, "properties", "titles", "title")
    title = (title_el.text or "").strip() if title_el is not None else ""
    number = ""
    songbook = _find(root, "properties", "songbooks", "songbook")
    if songbook is not None:
        number = str(songbook.get("entry") or "").strip()
    verses: dict[str, tuple[str, bool]] = {}
    ordered: list[str] = []
    lyrics = _find(root, "lyrics")
    for verse in _children(lyrics, "verse") if lyrics is not None else []:
        name = str(verse.get("name") or f"v{len(ordered) + 1}").strip().lower()
        blocks = [_lines_text(lines) for lines in _children(verse, "lines")]
        body = "\n".join(b for b in blocks if b)
        if body:
            verses[name] = (body, bool(_CHORUS_NAMES.match(name)))
            ordered.append(name)
    order_el = _find(root, "properties", "verseorder")
    sequence = ordered
    if order_el is not None and (order_el.text or "").strip():
        wanted = [n.lower() for n in (order_el.text or "").split()]
        if all(n in verses for n in wanted):
            sequence = wanted
    return {"title": title, "number": number, "stanzas": [verses[n] for n in sequence]}


def parse_opensong(root) -> dict[str, Any]:
    title = (_find(root, "title").text or "").strip() if _find(root, "title") is not None else ""
    number_el = _find(root, "hymn_number")
    number = (number_el.text or "").strip() if number_el is not None else ""
    lyrics_el = _find(root, "lyrics")
    lyrics = lyrics_el.text if lyrics_el is not None and lyrics_el.text else ""
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current = "V1"
    for raw in lyrics.replace("\r", "").split("\n"):
        marker = re.match(r"^\s*\[([^\]]+)\]\s*$", raw)
        if marker:
            current = marker.group(1).strip().upper()
            if current not in sections:
                sections[current] = []
                order.append(current)
            continue
        if not raw.strip() or raw.startswith(";") or raw.startswith("."):
            continue  # ligne vide, commentaire ou accords
        line = re.sub(r"^\s*\d?\s", "", raw) if raw[:1] in " 0123456789" else raw
        line = line.replace("|", " ").replace("_", "").strip()
        if current not in sections:
            sections[current] = []
            order.append(current)
        if line:
            sections[current].append(line)
    presentation = _find(root, "presentation")
    sequence = order
    if presentation is not None and (presentation.text or "").strip():
        wanted = [n.upper() for n in (presentation.text or "").split()]
        if all(n in sections for n in wanted):
            sequence = wanted
    stanzas = [
        ("\n".join(sections[name]), name.startswith(("C", "P")))
        for name in sequence
        if sections.get(name)
    ]
    return {"title": title, "number": number, "stanzas": stanzas}


def parse_ccli_text(text: str, fallback_title: str = "") -> dict[str, Any]:
    """Texte SongSelect : titre en 1re ligne, sections nommées, pied CCLI."""
    lines = [line.rstrip() for line in text.replace("\r", "").split("\n")]
    # Pied de page : à partir de la première ligne « CCLI » / « © ».
    for index, line in enumerate(lines):
        if re.match(r"^\s*(?:CCLI\b|©|Copyright\b|For use solely)", line, re.IGNORECASE):
            lines = lines[:index]
            break
    while lines and not lines[0].strip():
        lines.pop(0)
    title = lines.pop(0).strip() if lines else fallback_title
    stanzas: list[tuple[str, bool]] = []
    block: list[str] = []
    is_chorus = False

    def flush() -> None:
        nonlocal block
        body = "\n".join(line.strip() for line in block if line.strip())
        if body:
            stanzas.append((body, is_chorus))
        block = []

    for line in lines:
        if not line.strip():
            flush()
            continue
        if _SECTION_HEADER.match(line):
            flush()
            is_chorus = bool(_CHORUS_NAMES.match(line.strip()))
            continue
        block.append(line)
    flush()
    return {"title": title or fallback_title, "number": "", "stanzas": stanzas}


def parse_ccli_usr(text: str, fallback_title: str = "") -> dict[str, Any]:
    """Format SongSelect « USR » (INI : Title, Fields, Words avec ``/t``)."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(text if text.lstrip().startswith("[") else "[File]\n" + text)
    section = parser["File"] if parser.has_section("File") else parser[parser.sections()[0]]
    title = section.get("Title", fallback_title).strip()
    fields = [f.strip() for f in section.get("Fields", "").split("/t")]
    words = section.get("Words", "").split("/t")
    stanzas: list[tuple[str, bool]] = []
    for index, body in enumerate(words):
        body = "\n".join(line.strip() for line in body.split("/n") if line.strip())
        if not body:
            continue
        name = fields[index] if index < len(fields) else ""
        stanzas.append((body, bool(_CHORUS_NAMES.match(name))))
    return {"title": title, "number": "", "stanzas": stanzas}


def read_song_file(path: Path) -> dict[str, Any]:
    """Lit un chant (format détecté par le contenu) ; ValueError si inconnu."""
    path = Path(path)
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1252 décode presque tout
        raise ValueError("Encodage du fichier non reconnu.")
    stripped = text.lstrip()
    if stripped.startswith("<"):
        root = ET.fromstring(stripped.encode("utf-8"))
        if _local(root.tag) != "song":
            raise ValueError("Fichier XML qui n'est pas un chant.")
        song = parse_openlyrics(root) if _find(root, "lyrics", "verse") is not None \
            else parse_opensong(root)
    elif re.search(r"^\s*\[File\]|^\s*Words\s*=", text, re.MULTILINE):
        song = parse_ccli_usr(text, path.stem)
    else:
        song = parse_ccli_text(text, path.stem)
    song["title"] = (song.get("title") or path.stem).strip()
    if not song["stanzas"]:
        raise ValueError("Aucune strophe trouvée.")
    return song
