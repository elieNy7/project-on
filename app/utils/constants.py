"""Application-wide configuration constants for Project-On.

Centralise les valeurs magiques utilisées dans plusieurs modules
pour faciliter les ajustements sans chasser les occurrences dispersées.
"""

# ── Découpage des slides ──────────────────────────────────────────────────────
MAX_CHARS_PER_SLIDE: int = 280
OPTIMAL_CHARS_PER_SLIDE: int = 200
MIN_CHARS_PER_SLIDE: int = 60

# ── Playlist ──────────────────────────────────────────────────────────────────
MAX_UNDO_LEVELS: int = 20

# ── Base de données ───────────────────────────────────────────────────────────
DB_CACHE_SIZE_PAGES: int = -64000   # ~64 MB (négatif = kibibytes pour SQLite)
DB_MMAP_SIZE_BYTES: int = 268_435_456  # 256 MB

# ── Logs ──────────────────────────────────────────────────────────────────────
LOG_MAX_BYTES: int = 5_000_000   # 5 MB par fichier tournant
LOG_BACKUP_COUNT: int = 5        # nombre de fichiers de rotation conservés
CRASH_LOG_MAX_COUNT: int = 20    # nombre de rapports de crash conservés
