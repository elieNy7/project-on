"""Télécharge une sélection de familles Google Fonts dans assets/fonts/.

Source : dépôt officiel google/fonts (GitHub). Pour chaque famille on
préfère les TTF statiques (Regular + Bold) quand le dépôt en propose ;
sinon on prend la police variable (instance par défaut = Regular — Qt 6
gère l'axe de graisse). La licence OFL.txt accompagne toujours les
fichiers (redistribution autorisée par la SIL Open Font License).

Usage :
    python tools/download_google_fonts.py            # télécharge tout
    python tools/download_google_fonts.py --list     # liste les familles

Le manifeste ``assets/fonts/fonts.json`` est (re)généré à la fin : c'est
lui que lit ``app/utils/fonts.py`` pour alimenter la liste des polices.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"
MANIFEST_PATH = FONTS_DIR / "fonts.json"

RAW = "https://raw.githubusercontent.com/google/fonts/main"
API_DIR = "https://api.github.com/repos/google/fonts/contents"

# Garde-fous anti-SSRF : seuls ces hôtes et ce format de nom de fichier sont
# acceptés, quel que soit le contenu renvoyé par l'API GitHub.
_ALLOWED_HOSTS = frozenset({"api.github.com", "raw.githubusercontent.com"})
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._\[\],\-]+$")


def _github_url(base: str, slug: str, file_name: str | None = None) -> str:
    """Construit une URL GitHub en validant hôte + segments de chemin.

    Lève ValueError si un composant ne passe pas la liste blanche — on ne
    suit jamais une URL arbitraire provenant d'une réponse HTTP.
    """
    host = urllib.parse.urlparse(base).netloc
    if host not in _ALLOWED_HOSTS:
        raise ValueError(f"Hôte non autorisé : {host}")
    if not re.fullmatch(r"[a-z0-9\-]+(/[a-z0-9\-]+)?", slug):
        raise ValueError(f"Slug de dépôt invalide : {slug!r}")
    path = f"{base}/{slug}"
    if file_name is not None:
        if not _SAFE_NAME.fullmatch(file_name):
            raise ValueError(f"Nom de fichier invalide : {file_name!r}")
        path += "/" + urllib.parse.quote(file_name)
    return path

# (slug dépôt, nom de famille affiché/CSS, dossier local)
FAMILIES: list[tuple[str, str, str]] = [
    # ── Sans-serif (lisibilité en projection) ────────────────────────────
    ("montserrat", "Montserrat", "Montserrat"),
    ("inter", "Inter", "Inter"),
    ("raleway", "Raleway", "Raleway"),
    ("nunito", "Nunito", "Nunito"),
    ("opensans", "Open Sans", "Open Sans"),
    ("lato", "Lato", "Lato"),
    ("roboto", "Roboto", "Roboto"),
    ("sourcesans3", "Source Sans 3", "Source Sans 3"),
    ("worksans", "Work Sans", "Work Sans"),
    ("rubik", "Rubik", "Rubik"),
    ("mulish", "Mulish", "Mulish"),
    ("manrope", "Manrope", "Manrope"),
    ("outfit", "Outfit", "Outfit"),
    ("jost", "Jost", "Jost"),
    ("urbanist", "Urbanist", "Urbanist"),
    ("figtree", "Figtree", "Figtree"),
    # ── Display / impact (titres, annonces) ──────────────────────────────
    ("anton", "Anton", "Anton"),
    ("archivoblack", "Archivo Black", "Archivo Black"),
    ("passionone", "Passion One", "Passion One"),
    ("teko", "Teko", "Teko"),
    ("alfaslabone", "Alfa Slab One", "Alfa Slab One"),
    # ── Serif (Écriture, citations) ──────────────────────────────────────
    ("playfairdisplay", "Playfair Display", "Playfair Display"),
    ("merriweather", "Merriweather", "Merriweather"),
    ("cormorantgaramond", "Cormorant Garamond", "Cormorant Garamond"),
    ("librebaskerville", "Libre Baskerville", "Libre Baskerville"),
    ("lora", "Lora", "Lora"),
    ("ebgaramond", "EB Garamond", "EB Garamond"),
    ("cinzel", "Cinzel", "Cinzel"),
    ("spectral", "Spectral", "Spectral"),
    ("cardo", "Cardo", "Cardo"),
    # ── Script / manuscrites (chants, décor) ─────────────────────────────
    ("dancingscript", "Dancing Script", "Dancing Script"),
    ("greatvibes", "Great Vibes", "Great Vibes"),
    ("pacifico", "Pacifico", "Pacifico"),
    ("caveat", "Caveat", "Caveat"),
    ("satisfy", "Satisfy", "Satisfy"),
    ("parisienne", "Parisienne", "Parisienne"),
    ("sacramento", "Sacramento", "Sacramento"),
]


def _assert_public_host(host: str) -> None:
    """Refuse tout hôte hors liste blanche ou résolvant vers une IP privée.

    Protection anti DNS-rebinding : chaque nom est résolu et toutes les
    adresses doivent être publiques (pas de loopback, RFC1918, link-local…).
    """
    if host not in _ALLOWED_HOSTS:
        raise ValueError(f"Hôte non autorisé : {host}")
    import ipaddress
    import socket

    for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
        host, 443
    ):
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global:
            raise ValueError(f"IP non publique pour {host} : {ip}")


class _StrictRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirections revalidées (https + hôte + IP publique) avant chaque saut."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != "https":
            raise ValueError(f"Redirection non-https refusée : {newurl}")
        _assert_public_host(parsed.netloc)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_StrictRedirectHandler())


def _fetch(url: str, timeout: int = 30) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Protocole non autorisé : {url}")
    _assert_public_host(parsed.netloc)
    request = urllib.request.Request(url, headers={"User-Agent": "project-on-fonts"})
    with _OPENER.open(request, timeout=timeout) as response:
        return response.read()


def _fetch_json(url: str):
    return json.loads(_fetch(url).decode("utf-8"))


def _pick_files(entries: list[dict], family_compact: str) -> list[dict]:
    """Choisit les TTF d'une famille : statiques Regular/Bold sinon variable."""
    by_name = {entry["name"]: entry for entry in entries}

    statics = []
    for suffix in ("-Regular", "-Bold"):
        name = f"{family_compact}{suffix}.ttf"
        if name in by_name:
            statics.append(by_name[name])
    if statics:
        return statics

    # Police variable (nom du type « Montserrat[wght].ttf »), sans italique.
    variable = [
        entry
        for entry in entries
        if entry["name"].endswith(".ttf")
        and "[" in entry["name"]
        and "Italic" not in entry["name"]
    ]
    return variable[:1]


def download_family(slug: str, family: str, folder: str) -> dict | None:
    """Télécharge une famille ; renvoie son entrée de manifeste (ou None)."""
    family_compact = family.replace(" ", "")
    target = FONTS_DIR / folder

    entries = None
    slug_path = ""
    for base in ("ofl", "apache"):
        try:
            entries = _fetch_json(_github_url(API_DIR, slug))
            slug_path = f"{base}/{slug}"
            break
        except ValueError as exc:
            print(f"  ✗ {family} : {exc}")
            return None
        except Exception:
            continue
    if not entries:
        print(f"  ✗ {family} : dépôt introuvable ({slug})")
        return None

    chosen = _pick_files(entries, family_compact)
    if not chosen:
        print(f"  ✗ {family} : aucun TTF trouvé dans {slug_path}")
        return None

    target.mkdir(parents=True, exist_ok=True)
    downloaded: list[str] = []
    try:
        for entry in chosen:
            data = _fetch(_github_url(RAW, slug, entry["name"]))
            (target / entry["name"]).write_bytes(data)
            downloaded.append(entry["name"])
        # Licence (OFL ou Apache) : toujours redistribuée avec la police.
        license_names = [
            e["name"]
            for e in entries
            if e["name"].upper().startswith(("OFL", "LICENSE", "APACHE"))
        ]
        if license_names:
            lic = _fetch(_github_url(RAW, slug, license_names[0]))
            (target / "OFL.txt").write_bytes(lic)
    except ValueError as exc:
        print(f"  ✗ {family} : {exc}")
        return None
    except Exception as exc:
        print(f"  ✗ {family} : échec du téléchargement ({exc})")
        return None

    print(f"  ✓ {family} : {', '.join(downloaded)}")
    return {"family": family, "folder": folder, "files": downloaded}


def main() -> int:
    if "--list" in sys.argv:
        for _slug, family, _folder in FAMILIES:
            print(family)
        return 0

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    failures: list[str] = []

    for index, (slug, family, folder) in enumerate(FAMILIES, start=1):
        print(f"[{index}/{len(FAMILIES)}] {family}…")
        entry = download_family(slug, family, folder)
        if entry is None:
            failures.append(family)
        else:
            manifest.append(entry)
        time.sleep(0.3)  # douceur envers l'API GitHub (60 req/h sans jeton)

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nManifeste : {MANIFEST_PATH} ({len(manifest)} familles)")
    if failures:
        print("Échecs (à retenter) :", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
