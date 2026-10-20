"""CSV loading and schema inference for the NPR CSV to SQLite loader."""
import csv
import logging
import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from config import (
    ALWAYS_TEXT_COLUMN_NAMES,
    ALWAYS_TEXT_COLUMN_SUFFIXES,
    CHUNK_SIZE,
    DATE_PATTERN,
    ENCODING_ORDER,
    INTEGER_PATTERN,
    MALFORMED_ROW_WARN_LIMIT,
    NULL_VALUES,
    REAL_PATTERN,
    SAMPLE_SIZE,
)

logger = logging.getLogger(__name__)


class LoadResult:
    """Result of loading a single CSV file."""

    def __init__(self, table_name: str, filepath: Path):
        self.table_name = table_name
        self.filepath = filepath
        self.rows_loaded = 0
        self.rows_skipped = 0
        self.columns: Dict[str, str] = {}
        self.encoding = "unknown"
        self.delimiter = ";"

    def __repr__(self) -> str:
        return (
            f"LoadResult(table={self.table_name}, "
            f"rows_loaded={self.rows_loaded}, "
            f"rows_skipped={self.rows_skipped}, "
            f"columns={len(self.columns)})"
        )


def discover_csv_files(data_dir: Path) -> List[Path]:
    """Find all .csv files in the directory, sorted alphabetically."""
    if not data_dir.exists():
        logger.error(f"Data directory does not exist: {data_dir}")
        return []

    files = sorted(data_dir.glob("*.csv"))
    logger.info(f"Found {len(files)} CSV files in {data_dir}")
    return files


def detect_encoding(filepath: Path) -> str:
    """Detect file encoding by trying each in order."""
    # Read samples from beginning, middle, and end of file
    file_size = filepath.stat().st_size
    sample_size = min(65536, file_size)  # 64KB per sample

    samples = []
    with open(filepath, "rb") as f:
        # Beginning
        samples.append(f.read(sample_size))

        # Middle (if file is large enough)
        if file_size > sample_size * 2:
            f.seek(file_size // 2)
            samples.append(f.read(sample_size))

        # End
        if file_size > sample_size:
            f.seek(max(0, file_size - sample_size))
            samples.append(f.read(sample_size))

    # Combine all samples
    combined = b"".join(samples)

    # First, check if it's UTF-8 (with or without BOM)
    # UTF-8 is preferred if ALL samples decode cleanly
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            combined.decode(encoding)
            return encoding
        except (UnicodeDecodeError, LookupError):
            continue

    # If UTF-8 fails, try Latin-1/ISO-8859-1 which never fails
    # This is common for Norwegian data with special characters
    for encoding in ("latin-1", "cp1252", "iso-8859-1"):
        try:
            combined.decode(encoding)
            return encoding
        except (UnicodeDecodeError, LookupError):
            continue

    # Fallback to latin-1 which never fails
    logger.warning(f"Could not detect encoding for {filepath}, using latin-1")
    return "latin-1"


def detect_delimiter(filepath: Path, encoding: str) -> str:
    """Detect CSV delimiter using csv.Sniffer with fallback to semicolon."""
    try:
        with open(filepath, "r", encoding=encoding, errors="replace", newline="") as f:
            sample = f.read(65536)  # Read first 64KB

        # Try sniffer first
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
            return dialect.delimiter
        except csv.Error:
            pass

        # Fallback: count occurrences
        counts = {d: sample.count(d) for d in ";,\t|"}
        if counts:
            best = max(counts, key=counts.get)
            if counts[best] > 0:
                return best

    except Exception as e:
        logger.warning(f"Error detecting delimiter for {filepath}: {e}")

    # Default to semicolon (common for Norwegian data)
    return ";"


def sanitize_column_name(name: str, used_names: set) -> str:
    """Sanitize a column name for SQLite use."""
    # Lowercase and replace non-alphanumeric with underscore
    clean = re.sub(r"[^a-zA-Z0-9]", "_", name).lower()
    clean = re.sub(r"_+", "_", clean).strip("_")

    # Ensure it doesn't start with a digit
    if clean and clean[0].isdigit():
        clean = f"_{clean}"

    # Ensure non-empty
    if not clean:
        clean = "column"

    # Deduplicate
    base = clean
    counter = 1
    while clean in used_names:
        clean = f"{base}_{counter}"
        counter += 1

    used_names.add(clean)
    return clean


def filename_to_table_name(filename: str) -> str:
    """Convert 'AVTaktivitet1.csv' -> 'avtaktivitet'."""
    # Remove extension
    name = Path(filename).stem

    # Lowercase
    name = name.lower()

    # Remove trailing digits (e.g., 'aktivitet1' -> 'aktivitet')
    name = re.sub(r"\d+$", "", name)

    # Replace non-alphanumeric with underscore
    name = re.sub(r"[^a-zA-Z0-9]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")

    return name


def is_null_value(value: str) -> bool:
    """Check if a value should be treated as NULL."""
    return value in NULL_VALUES


def should_force_text(column_name: str) -> bool:
    """Check if a column should always be TEXT (e.g., code columns)."""
    if column_name in ALWAYS_TEXT_COLUMN_NAMES:
        return True
    return any(column_name.endswith(suffix) for suffix in ALWAYS_TEXT_COLUMN_SUFFIXES)


def infer_column_type(values: List[str], column_name: str) -> str:
    """Infer SQLite type for a column based on sample values."""
    # Force TEXT for code-like columns
    if should_force_text(column_name):
        return "TEXT"

    # Filter out NULL values
    non_null = [v for v in values if not is_null_value(v)]

    if not non_null:
        return "TEXT"  # All NULLs - default to TEXT

    # Check if all values are integers
    if all(re.match(INTEGER_PATTERN, v) for v in non_null):
        return "INTEGER"

    # Check if all values are floats (but not integers)
    if all(re.match(REAL_PATTERN, v) for v in non_null):
        return "REAL"

    # Check if all values are dates (keep as TEXT for SQLite)
    if all(re.match(DATE_PATTERN, v) for v in non_null):
        return "TEXT"

    # Mixed types or other - use TEXT
    return "TEXT"


def infer_schema(
    filepath: Path,
    encoding: str,
    delimiter: str,
    sample_size: int = SAMPLE_SIZE,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Infer column names and types from a CSV file.

    Returns:
        (column_names, column_types) where column_types maps name -> SQL type
    """
    column_names: List[str] = []
    column_types: Dict[str, str] = {}
    used_names: set = set()

    try:
        with open(filepath, "r", encoding=encoding, errors="replace", newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)

            # Read header
            try:
                header = next(reader)
            except StopIteration:
                logger.warning(f"Empty file: {filepath}")
                return [], {}

            # Sanitize column names
            for i, name in enumerate(header):
                clean_name = sanitize_column_name(name, used_names)
                column_names.append(clean_name)

            # Sample rows for type inference
            sample_values: Dict[str, List[str]] = {name: [] for name in column_names}
            for row_idx, row in enumerate(reader):
                if row_idx >= sample_size:
                    break

                # Pad or truncate row to match header length
                for i, name in enumerate(column_names):
                    if i < len(row):
                        sample_values[name].append(row[i])
                    else:
                        sample_values[name].append("")

            # Infer types
            for name in column_names:
                column_types[name] = infer_column_type(sample_values[name], name)

            logger.debug(
                f"Inferred schema for {filepath.name}: "
                f"{len(column_names)} columns, "
                f"types: {column_types}"
            )

    except Exception as e:
        logger.error(f"Error inferring schema for {filepath}: {e}")
        raise

    return column_names, column_types


def convert_value(value: str, sql_type: str) -> object:
    """Convert a CSV string value to the appropriate Python type."""
    if is_null_value(value):
        return None

    if sql_type == "INTEGER":
        try:
            return int(value)
        except ValueError:
            return None
    elif sql_type == "REAL":
        try:
            # Handle European decimal comma
            return float(value.replace(",", "."))
        except ValueError:
            return None
    else:  # TEXT
        # Strip whitespace but preserve internal spaces
        return value.strip() if value else None


def load_csv_to_db(
    filepath: Path,
    db,
    force: bool = False,
    verbose: bool = False,
    create_indexes: bool = False,
) -> LoadResult:
    """
    Load a single CSV file into the database.

    Args:
        filepath: Path to the CSV file
        db: DatabaseManager instance
        force: Drop existing table before loading
        verbose: Enable detailed logging
        create_indexes: Auto-create indexes on *_id columns

    Returns:
        LoadResult with statistics
    """
    result = LoadResult(filename_to_table_name(filepath.name), filepath)

    # Detect encoding and delimiter
    result.encoding = detect_encoding(filepath)
    result.delimiter = detect_delimiter(filepath, result.encoding)

    if verbose:
        logger.info(
            f"Loading {filepath.name}: encoding={result.encoding}, "
            f"delimiter='{result.delimiter}'"
        )

    # Infer schema
    column_names, column_types = infer_schema(
        filepath, result.encoding, result.delimiter
    )

    if not column_names:
        logger.warning(f"No columns found in {filepath.name}, skipping")
        return result

    result.columns = column_types

    # Handle table creation
    if force and db.table_exists(result.table_name):
        db.drop_table(result.table_name)

    db.create_table(result.table_name, column_types)

    # Stream and insert data
    malformed_count = 0
    batch: List[Tuple] = []

    # Begin a single transaction for the entire file load
    db.begin_transaction()

    try:
        with open(filepath, "r", encoding=result.encoding, errors="replace", newline="") as f:
            reader = csv.reader(f, delimiter=result.delimiter)

            # Skip header
            try:
                next(reader)
            except StopIteration:
                logger.warning(f"Empty file (header only): {filepath.name}")
                db.commit()
                return result

            for row_idx, row in enumerate(reader, start=1):
                # Skip completely empty rows
                if not row or all(v == "" for v in row):
                    continue

                # Handle row length mismatch
                if len(row) != len(column_names):
                    malformed_count += 1
                    if malformed_count <= MALFORMED_ROW_WARN_LIMIT:
                        logger.warning(
                            f"Row {row_idx} in {filepath.name} has "
                            f"{len(row)} columns, expected {len(column_names)}. "
                            f"Skipping."
                        )
                    result.rows_skipped += 1
                    continue

                # Convert values
                converted = tuple(
                    convert_value(row[i], column_types[name])
                    for i, name in enumerate(column_names)
                )

                batch.append(converted)

                # Insert in batches
                if len(batch) >= CHUNK_SIZE:
                    db.insert_rows(result.table_name, column_names, batch)
                    result.rows_loaded += len(batch)
                    batch = []

                    if verbose and result.rows_loaded % (CHUNK_SIZE * 10) == 0:
                        logger.info(
                            f"  {result.table_name}: {result.rows_loaded} rows loaded"
                        )

            # Insert remaining batch
            if batch:
                db.insert_rows(result.table_name, column_names, batch)
                result.rows_loaded += len(batch)

        # Commit the transaction for this file
        db.commit()

    except Exception as e:
        # Rollback on error to keep database consistent
        db.rollback()
        logger.error(f"Error loading {filepath.name}: {e}")
        raise

    # Create indexes if requested
    if create_indexes:
        for name in column_names:
            if name.endswith("_id") or name == "pasientid":
                db.create_index(result.table_name, name)

    if malformed_count > MALFORMED_ROW_WARN_LIMIT:
        logger.warning(
            f"{filepath.name}: {malformed_count} malformed rows skipped "
            f"(showing first {MALFORMED_ROW_WARN_LIMIT})"
        )

    logger.info(
        f"Loaded {result.table_name}: {result.rows_loaded} rows, "
        f"{result.rows_skipped} skipped, {len(column_names)} columns"
    )

    return result


def load_all_csvs(
    data_dir: Path,
    db,
    force: bool = False,
    verbose: bool = False,
    create_indexes: bool = False,
    tables_filter: Optional[List[str]] = None,
) -> List[LoadResult]:
    """Load all CSV files from a directory into the database."""
    files = discover_csv_files(data_dir)
    results: List[LoadResult] = []

    for filepath in files:
        table_name = filename_to_table_name(filepath.name)

        # Apply table filter if specified
        if tables_filter and table_name not in tables_filter:
            logger.debug(f"Skipping {table_name} (not in filter)")
            continue

        try:
            result = load_csv_to_db(
                filepath,
                db,
                force=force,
                verbose=verbose,
                create_indexes=create_indexes,
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to load {filepath.name}: {e}")
            # Continue with other files

    return results
