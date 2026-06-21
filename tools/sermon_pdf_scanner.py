"""Scanner de PDFs de sermons VGR pour créer une base de données SQLite.

Structure des noms de fichiers:
- Français: FRN63-0901M Token VGR.pdf
- Anglais: 63-0901M Token VGR.pdf

Extrait:
- langue (fr/en)
- date (YYYY-MM-DD)
- titre
- lieu (si disponible dans le PDF)
- traducteur (VGR, SHP pour français)
- paragraphes
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Try to import PDF libraries
try:
    import fitz  # PyMuPDF

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from pypdf import PdfReader

    HAS_PYPDF = True
except ImportError:
    try:
        from PyPDF2 import PdfReader

        HAS_PYPDF = True
    except ImportError:
        HAS_PYPDF = False


@dataclass
class SermonMetadata:
    """Métadonnées extraites du nom de fichier d'un sermon."""

    filename: str
    language: str  # 'fr' ou 'en'
    date: str  # Format YYYY-MM-DD
    date_code: str  # Format original YY-MMDD
    time_suffix: str  # M (matin), E (soir), A, B, S, X, etc.
    title: str
    translator: str  # VGR, SHP, etc.
    file_path: str


@dataclass
class SermonParagraph:
    """Un paragraphe extrait d'un sermon PDF."""

    paragraph_no: int
    text: str
    ref: str | None = None


class SermonPdfScanner:
    """Scanner de PDFs de sermons pour extraction et stockage en base de données."""

    # Regex pour parser les noms de fichiers
    # Français: FRN63-0901M Token VGR.pdf
    # Anglais: 63-0901M Token VGR.pdf
    _FILENAME_RE = re.compile(
        r"^(?P<lang>FRN)?"  # Préfixe langue optionnel
        r"(?P<yy>\d{2})-"  # Année (2 chiffres)
        r"(?P<mmdd>\d{4})"  # Mois et jour
        r"(?P<suffix>[MEABSX])?"  # Suffixe optionnel (Matin, Evening, etc.)
        r"\s+"  # Espace(s)
        r"(?P<title>.+?)"  # Titre
        r"\s+"  # Espace(s)
        r"(?P<translator>VGR|SHP)"  # Traducteur
        r"\.pdf$",  # Extension
        re.IGNORECASE,
    )

    # Regex alternatif pour les livres et tracts
    _BOOK_RE = re.compile(
        r"^(?P<lang>FRN)?"
        r"(?P<type>BK|TR)-"  # BK = Book, TR = Tract
        r"(?P<code>[A-Z]+)"
        r"\s+"
        r"(?P<title>.+?)"
        r"\s+"
        r"(?P<translator>VGR|SHP)"
        r"\.(?:pdf|docx)$",
        re.IGNORECASE,
    )

    # Regex pour extraire les paragraphes numérotés
    # Format E-1, E-2 (anglais original)
    _PARA_E_RE = re.compile(r"^E-(\d+)\s+(.+)", re.MULTILINE)
    # Format numéro seul sur une ligne (traductions VGR)
    _PARA_NUM_RE = re.compile(r"^(\d+)\s*$", re.MULTILINE)

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialise le schéma de la base de données."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sermon (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    date TEXT,
                    date_code TEXT,
                    time_suffix TEXT,
                    language TEXT NOT NULL,
                    translator TEXT NOT NULL,
                    location TEXT,
                    file_path TEXT NOT NULL,
                    paragraph_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_sermon_language 
                    ON sermon (language);
                CREATE INDEX IF NOT EXISTS idx_sermon_translator 
                    ON sermon (translator);
                CREATE INDEX IF NOT EXISTS idx_sermon_date 
                    ON sermon (date);
                CREATE INDEX IF NOT EXISTS idx_sermon_title 
                    ON sermon (title);
                
                CREATE TABLE IF NOT EXISTS sermon_paragraph (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sermon_id INTEGER NOT NULL,
                    paragraph_no INTEGER NOT NULL,
                    ref TEXT,
                    text TEXT NOT NULL,
                    FOREIGN KEY (sermon_id) REFERENCES sermon (id) ON DELETE CASCADE,
                    UNIQUE (sermon_id, paragraph_no)
                );
                
                CREATE INDEX IF NOT EXISTS idx_paragraph_sermon 
                    ON sermon_paragraph (sermon_id, paragraph_no);
                CREATE INDEX IF NOT EXISTS idx_paragraph_text 
                    ON sermon_paragraph (text);
                
                CREATE TABLE IF NOT EXISTS scan_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    files_scanned INTEGER,
                    files_added INTEGER,
                    files_skipped INTEGER,
                    errors INTEGER
                );
            """)
            conn.commit()

    def parse_filename(self, filename: str, file_path: str) -> SermonMetadata | None:
        """Parse un nom de fichier PDF pour extraire les métadonnées."""
        # Essayer d'abord le format sermon standard
        match = self._FILENAME_RE.match(filename)
        if match:
            lang_prefix = match.group("lang")
            language = "fr" if lang_prefix else "en"

            yy = match.group("yy")
            mmdd = match.group("mmdd")
            mm = mmdd[:2]
            dd = mmdd[2:]

            # Convertir en date ISO
            year = f"19{yy}" if int(yy) > 25 else f"20{yy}"
            date = f"{year}-{mm}-{dd}"
            date_code = f"{yy}-{mmdd}"

            time_suffix = match.group("suffix") or ""
            title = match.group("title").strip()
            translator = match.group("translator").upper()

            return SermonMetadata(
                filename=filename,
                language=language,
                date=date,
                date_code=date_code,
                time_suffix=time_suffix,
                title=title,
                translator=translator,
                file_path=file_path,
            )

        # Essayer le format livre/tract (BK, TR)
        match = self._BOOK_RE.match(filename)
        if match:
            lang_prefix = match.group("lang")
            language = "fr" if lang_prefix else "en"
            doc_type = match.group("type").upper()  # BK ou TR
            code = match.group("code")
            title = match.group("title").strip()
            translator = match.group("translator").upper()

            return SermonMetadata(
                filename=filename,
                language=language,
                date=None,  # Pas de date pour les livres
                date_code=f"{doc_type}-{code}",
                time_suffix=doc_type,  # Utiliser le type comme suffixe
                title=title,
                translator=translator,
                file_path=file_path,
            )

        return None

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extrait le texte d'un fichier PDF."""
        if HAS_PYMUPDF:
            return self._extract_with_pymupdf(pdf_path)
        if HAS_PYPDF:
            return self._extract_with_pypdf(pdf_path)
        raise RuntimeError(
            "Aucune bibliothèque PDF disponible. "
            "Installez PyMuPDF (pip install pymupdf) ou pypdf (pip install pypdf)",
        )

    def _extract_with_pymupdf(self, pdf_path: Path) -> str:
        """Extrait le texte avec PyMuPDF (fitz)."""
        text_parts = []
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n".join(text_parts)

    def _extract_with_pypdf(self, pdf_path: Path) -> str:
        """Extrait le texte avec pypdf/PyPDF2."""
        text_parts = []
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)

    def extract_paragraphs(self, text: str) -> list[SermonParagraph]:
        """Extrait les paragraphes numérotés du texte."""
        paragraphs = []

        # Essayer d'abord le format E-1, E-2, etc.
        e_matches = list(self._PARA_E_RE.finditer(text))

        if e_matches:
            for i, match in enumerate(e_matches):
                para_no = int(match.group(1))
                start = match.end()
                end = e_matches[i + 1].start() if i + 1 < len(e_matches) else len(text)
                para_text = text[start:end].strip()
                para_text = self._clean_text(para_text)

                if para_text:
                    paragraphs.append(
                        SermonParagraph(
                            paragraph_no=para_no,
                            text=para_text,
                            ref=f"E-{para_no}",
                        )
                    )
            return paragraphs

        # Essayer le format numéro seul sur une ligne (PDFs VGR traduits)
        num_matches = list(self._PARA_NUM_RE.finditer(text))

        if len(num_matches) >= 5:  # Au moins 5 paragraphes numérotés
            # Filtrer pour garder seulement les numéros qui semblent être des paragraphes
            # (numéros croissants ou proches)
            valid_matches = []
            for match in num_matches:
                num = int(match.group(1))
                # Ignorer les numéros trop grands (probablement des années ou pages)
                if 1 <= num <= 500:
                    valid_matches.append((num, match))

            if len(valid_matches) >= 5:
                # Trier par position dans le texte
                valid_matches.sort(key=lambda x: x[1].start())

                for i, (para_no, match) in enumerate(valid_matches):
                    # Le texte commence après le numéro
                    start = match.end()
                    # Et va jusqu'au prochain numéro ou la fin
                    if i + 1 < len(valid_matches):
                        end = valid_matches[i + 1][1].start()
                    else:
                        end = len(text)

                    para_text = text[start:end].strip()
                    para_text = self._clean_text(para_text)

                    # Ignorer les paragraphes trop courts
                    if para_text and len(para_text) > 30:
                        paragraphs.append(
                            SermonParagraph(
                                paragraph_no=para_no,
                                text=para_text,
                                ref=f"§{para_no}",
                            )
                        )

                if paragraphs:
                    return paragraphs

        # Fallback: diviser par lignes vides
        blocks = re.split(r"\n\s*\n", text)
        for i, block in enumerate(blocks, 1):
            block = self._clean_text(block)
            if block and len(block) > 50:  # Ignorer les blocs trop courts
                paragraphs.append(
                    SermonParagraph(
                        paragraph_no=i,
                        text=block,
                    )
                )

        return paragraphs

    def _clean_text(self, text: str) -> str:
        """Nettoie le texte extrait."""
        # Supprimer les caractères de contrôle
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Normaliser les espaces
        text = re.sub(r"[ \t]+", " ", text)
        # Normaliser les sauts de ligne
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Supprimer les espaces en début/fin de ligne
        text = "\n".join(line.strip() for line in text.split("\n"))
        return text.strip()

    def extract_location(self, text: str) -> str | None:
        """Tente d'extraire le lieu du sermon depuis le texte."""
        # Chercher des patterns communs pour le lieu
        patterns = [
            r"(?:Preached|Prêché)\s+(?:at|à)\s+([^,\n]+)",
            r"(?:Location|Lieu)\s*:\s*([^\n]+)",
            r"(?:Jeffersonville|Branham Tabernacle|Phoenix|Los Angeles|Chicago)[^\n]*",
        ]

        for pattern in patterns:
            match = re.search(pattern, text[:2000], re.IGNORECASE)
            if match:
                return (
                    match.group(1).strip()
                    if match.lastindex
                    else match.group(0).strip()
                )

        return None

    def scan_directory(
        self,
        directory: Path,
        extract_content: bool = True,
        verbose: bool = True,
    ) -> dict:
        """Scanne un répertoire pour les PDFs de sermons.

        Args:
            directory: Répertoire à scanner
            extract_content: Si True, extrait aussi le contenu des PDFs
            verbose: Affiche les messages de progression

        Returns:
            Statistiques du scan

        """
        stats = {
            "files_scanned": 0,
            "files_added": 0,
            "files_skipped": 0,
            "errors": 0,
            "error_files": [],
        }

        if not directory.exists():
            raise ValueError(f"Le répertoire n'existe pas: {directory}")

        # Trouver tous les PDFs
        pdf_files = list(directory.rglob("*.pdf"))

        if verbose:
            print(f"Trouvé {len(pdf_files)} fichiers PDF dans {directory}")

        with sqlite3.connect(self.db_path) as conn:
            for pdf_path in pdf_files:
                stats["files_scanned"] += 1

                # Parser le nom de fichier
                metadata = self.parse_filename(pdf_path.name, str(pdf_path))

                if metadata is None:
                    if verbose:
                        print(f"  Ignoré (format non reconnu): {pdf_path.name}")
                    stats["files_skipped"] += 1
                    continue

                # Vérifier si déjà en base
                existing = conn.execute(
                    "SELECT id FROM sermon WHERE filename = ?",
                    (metadata.filename,),
                ).fetchone()

                if existing:
                    if verbose:
                        print(f"  Déjà en base: {metadata.filename}")
                    stats["files_skipped"] += 1
                    continue

                try:
                    location = None
                    paragraphs = []

                    if extract_content:
                        if verbose:
                            print(f"  Extraction: {metadata.filename}")

                        text = self.extract_text_from_pdf(pdf_path)
                        location = self.extract_location(text)
                        paragraphs = self.extract_paragraphs(text)

                    # Insérer le sermon
                    cursor = conn.execute(
                        """
                        INSERT INTO sermon 
                            (filename, title, date, date_code, time_suffix, 
                             language, translator, location, file_path, paragraph_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            metadata.filename,
                            metadata.title,
                            metadata.date,
                            metadata.date_code,
                            metadata.time_suffix,
                            metadata.language,
                            metadata.translator,
                            location,
                            metadata.file_path,
                            len(paragraphs),
                        ),
                    )
                    sermon_id = cursor.lastrowid

                    # Insérer les paragraphes (dédupliquer les numéros)
                    if paragraphs:
                        seen_nos = set()
                        unique_paras = []
                        for p in paragraphs:
                            # Si le numéro existe déjà, utiliser un numéro séquentiel
                            para_no = p.paragraph_no
                            while para_no in seen_nos:
                                para_no += 1000  # Décaler pour éviter les conflits
                            seen_nos.add(para_no)
                            unique_paras.append((sermon_id, para_no, p.ref, p.text))

                        conn.executemany(
                            """
                            INSERT INTO sermon_paragraph 
                                (sermon_id, paragraph_no, ref, text)
                            VALUES (?, ?, ?, ?)
                            """,
                            unique_paras,
                        )

                    conn.commit()
                    stats["files_added"] += 1

                    if verbose:
                        print(
                            f"  Ajouté: {metadata.title} ({metadata.language}, {len(paragraphs)} paragraphes)"
                        )

                except Exception as e:
                    stats["errors"] += 1
                    stats["error_files"].append((pdf_path.name, str(e)))
                    if verbose:
                        print(f"  Erreur: {pdf_path.name} - {e}")

            # Enregistrer le log du scan
            conn.execute(
                """
                INSERT INTO scan_log (files_scanned, files_added, files_skipped, errors)
                VALUES (?, ?, ?, ?)
                """,
                (
                    stats["files_scanned"],
                    stats["files_added"],
                    stats["files_skipped"],
                    stats["errors"],
                ),
            )
            conn.commit()

        return stats

    def rescan_empty_sermons(self, verbose: bool = True) -> dict:
        """Rescanne les sermons qui n'ont pas de paragraphes."""
        stats = {
            "sermons_rescanned": 0,
            "paragraphs_added": 0,
            "errors": 0,
        }

        with sqlite3.connect(self.db_path) as conn:
            # Trouver les sermons sans paragraphes
            rows = conn.execute(
                "SELECT id, filename, file_path FROM sermon WHERE paragraph_count = 0",
            ).fetchall()

            if verbose:
                print(f"Sermons sans paragraphes: {len(rows)}")

            for row in rows:
                sermon_id = row[0]
                filename = row[1]
                file_path = Path(row[2])

                if not file_path.exists():
                    if verbose:
                        print(f"  Fichier non trouvé: {filename}")
                    continue

                try:
                    if verbose:
                        print(f"  Rescan: {filename}")

                    text = self.extract_text_from_pdf(file_path)
                    paragraphs = self.extract_paragraphs(text)

                    if paragraphs:
                        # Dédupliquer les numéros
                        seen_nos = set()
                        unique_paras = []
                        for p in paragraphs:
                            para_no = p.paragraph_no
                            while para_no in seen_nos:
                                para_no += 1000
                            seen_nos.add(para_no)
                            unique_paras.append((sermon_id, para_no, p.ref, p.text))

                        conn.executemany(
                            """
                            INSERT OR REPLACE INTO sermon_paragraph 
                                (sermon_id, paragraph_no, ref, text)
                            VALUES (?, ?, ?, ?)
                            """,
                            unique_paras,
                        )

                        # Mettre à jour le compteur
                        conn.execute(
                            "UPDATE sermon SET paragraph_count = ? WHERE id = ?",
                            (len(paragraphs), sermon_id),
                        )
                        conn.commit()

                        stats["sermons_rescanned"] += 1
                        stats["paragraphs_added"] += len(paragraphs)

                        if verbose:
                            print(f"    Ajouté {len(paragraphs)} paragraphes")

                except Exception as e:
                    stats["errors"] += 1
                    if verbose:
                        print(f"    Erreur: {e}")

        return stats

    def get_statistics(self) -> dict:
        """Retourne les statistiques de la base de données."""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}

            # Nombre total de sermons
            row = conn.execute("SELECT COUNT(*) FROM sermon").fetchone()
            stats["total_sermons"] = row[0]

            # Par langue
            rows = conn.execute(
                "SELECT language, COUNT(*) FROM sermon GROUP BY language",
            ).fetchall()
            stats["by_language"] = {r[0]: r[1] for r in rows}

            # Par traducteur
            rows = conn.execute(
                "SELECT translator, COUNT(*) FROM sermon GROUP BY translator",
            ).fetchall()
            stats["by_translator"] = {r[0]: r[1] for r in rows}

            # Nombre total de paragraphes
            row = conn.execute("SELECT COUNT(*) FROM sermon_paragraph").fetchone()
            stats["total_paragraphs"] = row[0]

            # Plage de dates
            row = conn.execute(
                "SELECT MIN(date), MAX(date) FROM sermon WHERE date IS NOT NULL",
            ).fetchone()
            stats["date_range"] = {"min": row[0], "max": row[1]}

            return stats


def main():
    """Point d'entrée principal pour le scanner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scanner de PDFs de sermons VGR",
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Répertoire contenant les PDFs à scanner",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "sermons_vgr.db",
        help="Chemin de la base de données SQLite",
    )
    parser.add_argument(
        "--no-content",
        action="store_true",
        help="Ne pas extraire le contenu des PDFs (métadonnées seulement)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Afficher les statistiques de la base de données",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Mode silencieux",
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Rescanner les sermons sans paragraphes",
    )

    args = parser.parse_args()

    scanner = SermonPdfScanner(args.db)

    if args.rescan:
        print("\n=== Rescan des sermons sans paragraphes ===")
        stats = scanner.rescan_empty_sermons(verbose=not args.quiet)
        print(f"\nSermons rescannés: {stats['sermons_rescanned']}")
        print(f"Paragraphes ajoutés: {stats['paragraphs_added']}")
        print(f"Erreurs: {stats['errors']}")
        return

    if args.stats:
        stats = scanner.get_statistics()
        print("\n=== Statistiques de la base de données ===")
        print(f"Total sermons: {stats['total_sermons']}")
        print(f"Total paragraphes: {stats['total_paragraphs']}")
        print(f"Par langue: {stats['by_language']}")
        print(f"Par traducteur: {stats['by_translator']}")
        print(
            f"Plage de dates: {stats['date_range']['min']} à {stats['date_range']['max']}"
        )
        return

    print(f"\n=== Scan du répertoire: {args.directory} ===")
    print(f"Base de données: {args.db}")
    print(f"Extraction du contenu: {'Non' if args.no_content else 'Oui'}")
    print()

    stats = scanner.scan_directory(
        args.directory,
        extract_content=not args.no_content,
        verbose=not args.quiet,
    )

    print("\n=== Résumé du scan ===")
    print(f"Fichiers scannés: {stats['files_scanned']}")
    print(f"Fichiers ajoutés: {stats['files_added']}")
    print(f"Fichiers ignorés: {stats['files_skipped']}")
    print(f"Erreurs: {stats['errors']}")

    if stats["error_files"]:
        print("\nFichiers en erreur:")
        for filename, error in stats["error_files"]:
            print(f"  - {filename}: {error}")


if __name__ == "__main__":
    main()
