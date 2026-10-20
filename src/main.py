"""CLI entry point for loading NPR CSV files into SQLite."""
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from config import DB_FILE, RAW_DATA_DIR
from csv_loader import load_all_csvs
from database import DatabaseManager


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
        description="Load NPR CSV files into an on-disk SQLite database.",
        epilog=(
            "Examples:\n"
            "  python src/main.py --force --verbose\n"
            "  python src/main.py --tables somaktivitet,somkoder --output-db custom.db\n"
            "  python src/main.py --dry-run --verbose"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=RAW_DATA_DIR,
        help=f"Directory containing CSV files (default: {RAW_DATA_DIR})",
    )
    parser.add_argument(
        "--output-db",
        type=Path,
        default=DB_FILE,
        help=f"Output SQLite database path (default: {DB_FILE})",
    )
    parser.add_argument(
        "--tables",
        type=str,
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

    return parser.parse_args()


def parse_tables_filter(tables_str: Optional[str]) -> Optional[List[str]]:
    """Parse comma-separated table names into a list."""
    if not tables_str:
        return None
    return [t.strip().lower() for t in tables_str.split(",") if t.strip()]


def main() -> int:
    """Main entry point. Returns exit code."""
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Validate input directory
    if not args.input_dir.exists():
        logger.error(f"Input directory does not exist: {args.input_dir}")
        return 1

    # Parse table filter
    tables_filter = parse_tables_filter(args.tables)

    # Dry run - just show what would happen
    if args.dry_run:
        from csv_loader import discover_csv_files, filename_to_table_name

        files = discover_csv_files(args.input_dir)
        logger.info("DRY RUN - would load the following files:")
        for filepath in files:
            table_name = filename_to_table_name(filepath.name)
            if tables_filter and table_name not in tables_filter:
                continue
            logger.info(f"  {filepath.name} -> table '{table_name}'")
        logger.info(f"Output database: {args.output_db}")
        logger.info(f"Force mode: {args.force}")
        logger.info(f"Create indexes: {args.create_indexes}")
        return 0

    # Open database connection
    logger.info(f"Opening database: {args.output_db}")
    try:
        db = DatabaseManager(args.output_db)
    except Exception as e:
        logger.error(f"Failed to open database: {e}")
        return 1

    try:
        # Load all CSVs
        results = load_all_csvs(
            args.input_dir,
            db,
            force=args.force,
            verbose=args.verbose,
            create_indexes=args.create_indexes,
            tables_filter=tables_filter,
        )

        # Print summary
        logger.info("=" * 60)
        logger.info("LOAD SUMMARY")
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
        logger.info(f"Database: {args.output_db}")

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


if __name__ == "__main__":
    sys.exit(main())
