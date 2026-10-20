"""Configuration constants for the NPR CSV to SQLite loader."""
from pathlib import Path

# Directory paths
RAW_DATA_DIR = Path("raw/npr/rawdata")
DB_DIR = Path("db")
DB_FILE = DB_DIR / "npr.db"

# CSV parsing settings
CHUNK_SIZE = 50000          # rows per batch for insertion (larger = faster)
SAMPLE_SIZE = 1000          # rows for schema inference
MALFORMED_ROW_WARN_LIMIT = 100  # maximum malformed rows to log before silent

# Encoding detection order
ENCODING_ORDER = ["utf-8-sig", "utf-8", "latin-1", "cp1252", "iso-8859-1"]

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

# Columns that should always be TEXT even if numeric-looking (e.g., codes)
ALWAYS_TEXT_COLUMN_SUFFIXES = ("_code", "_kode", "_diag", "_icd", "_diagkode")
ALWAYS_TEXT_COLUMN_NAMES = {"hoveddiag", "bidiag", "diagnose", "icd10", "icd", "kode"}