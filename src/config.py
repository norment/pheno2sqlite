"""Configuration constants for the CSV to SQLite loaders (NPR, KPR, ...)."""
from pathlib import Path

# Directory paths
DB_DIR = Path("db")

# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------
# Each source ("dataset") has its own input directory and its own *dedicated*
# SQLite file. Database files are deliberately kept separate for
# data-governance / ethics reasons (per-user approvals). They are NOT merged.
# An authorized user who may access both sources can query them together in a
# single session by ATTACH-ing the other database (see src/query.py and the
# "Querying both sources" section of the README).
DATASETS = {
    "npr": {
        "input_dir": Path("raw/npr/rawdata"),
        "db_file": DB_DIR / "npr.db",
        "description": (
            "Norwegian Patient Register (NPR) - specialist health care "
            "(ICD-10 / NCSP / NCMP codes)"
        ),
        "code_systems": ("ICD-10", "NCSP", "NCMP"),
    },
    "kpr": {
        "input_dir": Path("raw/kpr/rawdata"),
        "db_file": DB_DIR / "kpr.db",
        "description": (
            "Kontroll og utbetaling av helserefusjoner (KPR) - primary care "
            "claims (ICPC-2 codes)"
        ),
        "code_systems": ("ICPC-2",),
    },
}

DEFAULT_SOURCE = "npr"

# Backward-compatible aliases (NPR)
RAW_DATA_DIR = DATASETS["npr"]["input_dir"]
DB_FILE = DATASETS["npr"]["db_file"]

# KPR aliases
KPR_RAW_DATA_DIR = DATASETS["kpr"]["input_dir"]
KPR_DB_FILE = DATASETS["kpr"]["db_file"]


def resolve_source(source: str) -> dict:
    """Return the dataset config dict for a source name.

    Raises:
        KeyError: if the source is not registered.
    """
    if source not in DATASETS:
        raise KeyError(
            f"Unknown source '{source}'. Known sources: "
            f"{', '.join(sorted(DATASETS))}"
        )
    return DATASETS[source]


# CSV parsing settings
CHUNK_SIZE = 50000          # rows per batch for insertion (larger = faster)
SAMPLE_SIZE = 1000          # rows for schema inference
MALFORMED_ROW_WARN_LIMIT = 100  # maximum malformed rows to log before silent

# Maximum number of databases that may be ATTACHed in one connection.
# SQLite's compiled-in default is 10 for older versions, 125 for newer ones.
MAX_ATTACHED_DATABASES = 10

# Encoding detection order
ENCODING_ORDER = ["utf-8-sig", "utf-8", "utf-16", "latin-1", "cp1252", "iso-8859-1"]

# NULL value representations
NULL_VALUES = {
    "", "NULL", "null", "NA", "N/A", "NaN", "nan", "None", "none",
    "Nil", "nil", "-", "--", "N/A ", " ",
}

# Column name sanitization
MAX_COLUMN_NAME_LENGTH = 64

# SQLite pragmas
PRAGMAS = {
    "journal_mode": "WAL",
    "busy_timeout": 5000,
    "synchronous": "OFF",       # Faster writes (WAL provides durability)
    "foreign_keys": "ON",
    "cache_size": -200000,       # 200MB cache for large inserts
    "temp_store": "MEMORY",     # Keep temp tables in memory
}

# Type inference constants
INTEGER_PATTERN = r"^-?\d+$"
REAL_PATTERN = r"^-?\d*\.\d+$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}:\d{2}(\.\d+)?)?$"

# Columns that should always be TEXT even if numeric-looking (e.g., codes).
# ICD-10 codes (e.g. 'F3201') and ICPC-2 codes (e.g. 'P76') must never be
# coerced to numbers.
ALWAYS_TEXT_COLUMN_SUFFIXES = (
    "_code", "_kode", "_diag", "_icd", "_icpc", "_diagkode", "_takstkode",
)
ALWAYS_TEXT_COLUMN_NAMES = {
    "hoveddiag", "bidiag", "diagnose", "icd10", "icd", "kode",
    "icpc", "icpc2", "icpc_kode", "kodeverdi", "kodenavn", "takstkode",
}
# Substrings that mark a column as code-like regardless of position/affixes.
ALWAYS_TEXT_COLUMN_SUBSTRINGS = ("kode", "diag", "icpc")
