"""Application-wide configuration constants for Project-On.

Centralise les valeurs magiques utilisées dans plusieurs modules
pour faciliter les ajustements sans chasser les occurrences dispersées.
"""

# ── Découpage des slides ──────────────────────────────────────────────────────
MAX_CHARS_PER_SLIDE: int = 280
MIN_CHARS_PER_SLIDE: int = 60

# ── Base de données ───────────────────────────────────────────────────────────
# Valeurs reprises en littéraux dans connection.py (PRAGMA n'accepte pas de
# paramètre lié) : garder ces deux nombres synchronisés manuellement.
DB_CACHE_SIZE_PAGES: int = -64000   # ~64 MB (négatif = kibibytes pour SQLite)
DB_MMAP_SIZE_BYTES: int = 268_435_456  # 256 MB

# ── Logs ──────────────────────────────────────────────────────────────────────
LOG_MAX_BYTES: int = 5_000_000   # 5 MB par fichier tournant
LOG_BACKUP_COUNT: int = 5        # nombre de fichiers de rotation conservés
CRASH_LOG_MAX_COUNT: int = 20    # nombre de rapports de crash conservés

# ── Soutien du projet ─────────────────────────────────────────────────────────
# Lien de don ouvert par le bouton « Soutenir » (sidebar, À propos, site).
# Remplacer par Ko-fi / PayPal.me / GitHub Sponsors selon le canal retenu.
DONATE_URL: str = "https://github.com/sponsors/elieNy7"
