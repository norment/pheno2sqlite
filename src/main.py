"""CLI entry point for loading source CSV files (NPR, KPR, ...) into SQLite."""
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from config import DATASETS, DEFAULT_SOURCE, resolve_source
from csv_loader import load_all_csvs
from database import DatabaseManager

SOURCE_CHOICES = sorted(DATASETS) + ["all"]


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Load Norwegian health-register CSV files (NPR, KPR, ...) into "
            "on-disk SQLite databases. Each source is written to its own "
            "dedicated database file and databases are never merged."
        ),
        epilog=(
            "Examples:\n"
            "  python src/main.py --source npr --force --verbose\n"
            "  python src/main.py --source kpr --force --verbose\n"
            "  python src/main.py --source all --force --verbose\n"
            "  python src/main.py --source kpr --show-schema\n"
            "  python src/main.py --input-dir raw/kpr/rawdata --output-db db/kpr.db --force"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--source",
        choices=SOURCE_CHOICES,
        default=DEFAULT_SOURCE,
        help=(
            "Which dataset(s) to load (default: %(default)s). "
            "'all' loads every registered source into its own database file."
        ),
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Override the input CSV directory (single source only).",
    )
    parser.add_argument(
        "--output-db",
        type=Path,
        default=None,
        help="Override the output SQLite database path (single source only).",
    )
    parser.add_argument(
        "--tables",
        type=str,
        default=None,
        help="Comma-separated list of table names to load (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop and recreate existing tables before loading",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually loading data",
    )
    parser.add_argument(
        "--create-indexes",
        action="store_true",
        help="Auto-create indexes on *_id and pasientid columns",
    )
    parser.add_argument(
        "--show-schema",
        action="store_true",
        help="Print tables and columns of the target database(s) and exit",
    )

    return parser.parse_args()


def parse_tables_filter(tables_str: Optional[str]) -> Optional[List[str]]:
    """Parse comma-separated table names into a list."""
    if not tables_str:
        return None
    return [t.strip().lower() for t in tables_str.split(",") if t.strip()]


def resolve_targets(args: argparse.Namespace, logger: logging.Logger):
    """Resolve (source, input_dir, output_db) triples from CLI args.

    Returns a list of tuples, or None if the arguments are invalid.
    """
    if args.source == "all":
        if args.input_dir or args.output_db:
            logger.error(
                "--input-dir/--output-db cannot be combined with --source all "
                "(each source has its own input directory and database file)."
            )
            return None
        sources = sorted(DATASETS)
    else:
        sources = [args.source]

    targets = []
    seen_dbs = {}
    for source in sources:
        cfg = resolve_source(source)
        input_dir = args.input_dir if args.input_dir else cfg["input_dir"]
        output_db = args.output_db if args.output_db else cfg["db_file"]

        # Safety guard: a single DB file must not be shared by two sources,
        # otherwise data from different approvals would be co-mingled.
        resolved = str(Path(output_db).resolve())
        if resolved in seen_dbs and seen_dbs[resolved] != source:
            logger.error(
                f"Refusing to write sources '{seen_dbs[resolved]}' and "
                f"'{source}' into the same database '{output_db}'. "
                f"Databases must be kept separate."
            )
            return None
        seen_dbs[resolved] = source

        targets.append((source, Path(input_dir), Path(output_db)))
    return targets


def show_schema(output_db: Path, logger: logging.Logger) -> int:
    """Print the schema of an existing database."""
    if not output_db.exists():
        logger.error(f"Database does not exist: {output_db}")
        return 1
    try:
        db = DatabaseManager(output_db)
    except Exception as e:
        logger.error(f"Failed to open database {output_db}: {e}")
        return 1
    try:
        schema = db.get_schema("main")
        logger.info(f"Schema for {output_db}: {len(schema)} table(s)")
        for table, columns in schema.items():
            logger.info(f"  {table} ({len(columns)} columns)")
            for name, type_ in columns:
                logger.info(f"      {name} {type_}")
        return 0
    finally:
        db.close()


def load_one(
    source: str,
    input_dir: Path,
    output_db: Path,
    args: argparse.Namespace,
    tables_filter: Optional[List[str]],
    logger: logging.Logger,
) -> int:
    """Load a single source into its dedicated database. Returns exit code."""
    if not input_dir.exists():
        logger.error(f"Input directory does not exist: {input_dir}")
        return 1

    # Dry run - just show what would happen
    if args.dry_run:
        from csv_loader import discover_csv_files, filename_to_table_name

        files = discover_csv_files(input_dir)
        logger.info(f"DRY RUN [{source}] - would load the following files:")
        for filepath in files:
            table_name = filename_to_table_name(filepath.name)
            if tables_filter and table_name not in tables_filter:
                continue
            logger.info(f"  {filepath.name} -> table '{table_name}'")
        logger.info(f"  Output database: {output_db}")
        logger.info(f"  Force mode: {args.force}")
        logger.info(f"  Create indexes: {args.create_indexes}")
        return 0

    # Open database connection
    logger.info(f"Opening database [{source}]: {output_db}")
    try:
        db = DatabaseManager(output_db)
    except Exception as e:
        logger.error(f"Failed to open database {output_db}: {e}")
        return 1

    try:
        # Load all CSVs
        results = load_all_csvs(
            input_dir,
            db,
            force=args.force,
            verbose=args.verbose,
            create_indexes=args.create_indexes,
            tables_filter=tables_filter,
        )

        # Print summary
        logger.info("=" * 60)
        logger.info(f"LOAD SUMMARY [{source}]")
        logger.info("=" * 60)
        total_rows = 0
        for result in results:
            total_rows += result.rows_loaded
            logger.info(
                f"  {result.table_name:20s} | "
                f"{result.rows_loaded:>10,} rows | "
                f"{len(result.columns):>3} cols | "
                f"{result.rows_skipped:>6,} skipped"
            )
        logger.info("=" * 60)
        logger.info(f"TOTAL: {total_rows:,} rows across {len(results)} tables")
        logger.info(f"Database: {output_db}")

        # Show available tables
        logger.info("\nAvailable tables:")
        for result in results:
            logger.info(f"  - {result.table_name}")

        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=args.verbose)
        return 1
    finally:
        db.close()


def main() -> int:
    """Main entry point. Returns exit code."""
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    targets = resolve_targets(args, logger)
    if targets is None:
        return 2

    # Schema inspection mode - do not load anything
    if args.show_schema:
        exit_code = 0
        for source, _input_dir, output_db in targets:
            exit_code |= show_schema(output_db, logger)
        return exit_code

    # Parse table filter
    tables_filter = parse_tables_filter(args.tables)

    # Load each source into its own database file
    exit_code = 0
    for source, input_dir, output_db in targets:
        exit_code |= load_one(
            source, input_dir, output_db, args, tables_filter, logger
        )

    if len(targets) > 1:
        logger.info("=" * 60)
        logger.info("ALL SOURCES LOADED (databases kept separate)")
        for source, _input_dir, output_db in targets:
            logger.info(f"  {source}: {output_db}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
