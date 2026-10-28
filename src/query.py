"""Ad-hoc cross-source querying for separately-stored SQLite databases.

The NPR (``db/npr.db``), KPR (``db/kpr.db``) and KUHR (``db/kuhr.db``)
databases are deliberately kept in *separate files* for data-governance /
ethics reasons (data are approved per-user and per-source). They are never
merged on disk.

A user who is approved for several sources can still query them *together* in
a single SQLite session by ATTACH-ing one database onto another. The
attachment is session-scoped and read-only by default, so nothing is merged or
written back to disk.

KUHR is stored as a single ``kuhr`` table with the delivery year in an
``aar`` column.

Examples
--------
Inventory of everything visible in the combined session::

    python src/query.py

Run a query that joins NPR, KPR and KUHR data::

    python src/query.py "SELECT COUNT(*) FROM main.somaktivitet"
    python src/query.py "SELECT n.lopenr, k.* FROM main.somaktivitet n \
        JOIN kpr.diagnose k ON n.lopenr = k.lopenr LIMIT 10"
    python src/query.py "SELECT n.lopenr FROM main.somaktivitet n \
        JOIN kuhr.kuhr k ON n.lopenr = k.lopenr AND k.aar = 2015 LIMIT 10"

Programmatic use::

    from query import connect_combined
    conn, attached = connect_combined(
        "db/npr.db", {"kpr": "db/kpr.db", "kuhr": "db/kuhr.db"}
    )
"""
import argparse
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from config import DATASETS, DEFAULT_SOURCE, resolve_source

logger = logging.getLogger(__name__)

DEFAULT_PRIMARY = resolve_source(DEFAULT_SOURCE)["db_file"]


def _to_uri(db_path: Path, read_only: bool = True) -> str:
    """Build a 'file:' URI, optionally read-only."""
    resolved = Path(db_path).expanduser().resolve()
    mode = "ro" if read_only else "rw"
    return f"file:{resolved}?mode={mode}"


def connect_combined(
    primary: Path = DEFAULT_PRIMARY,
    attached: Optional[Mapping[str, Path]] = None,
    read_only: bool = True,
) -> Tuple[sqlite3.Connection, Dict[str, Path]]:
    """Open ``primary`` and ATTACH the databases in ``attached``.

    Args:
        primary: Path to the primary (``main``) database.
        attached: Mapping of ``alias -> path`` for companion databases. The
            alias becomes the SQL schema name (e.g. ``kpr``).
        read_only: Attach/primary opened with ``mode=ro`` (default). Set
            ``False`` to allow writes.

    Returns:
        ``(connection, {alias: path})``. The connection has ``main`` plus one
        attached schema per entry in ``attached``.
    """
    primary = Path(primary)
    if not primary.exists():
        raise FileNotFoundError(f"Primary database does not exist: {primary}")

    conn = sqlite3.connect(_to_uri(primary, read_only=read_only), uri=True)

    used: Dict[str, Path] = {"main": primary}
    for alias, path in (attached or {}).items():
        path = Path(path)
        if not path.exists():
            logger.warning(f"Skipping missing database for '{alias}': {path}")
            continue
        if alias == "main":
            raise ValueError("Alias 'main' is reserved for the primary database")
        conn.execute(f'ATTACH DATABASE ? AS "{alias}"', (_to_uri(path, read_only),))
        used[alias] = path
        logger.debug(f"Attached {path} as '{alias}'")

    return conn, used


def default_attachments(
    primary_source: str = DEFAULT_SOURCE,
    require_exists: bool = True,
) -> Dict[str, Path]:
    """Attach every other registered source whose database file exists."""
    out: Dict[str, Path] = {}
    for name, cfg in DATASETS.items():
        if name == primary_source:
            continue
        db_file = Path(cfg["db_file"])
        if require_exists and not db_file.exists():
            continue
        out[name] = db_file
    return out


def _schemas(conn: sqlite3.Connection) -> List[str]:
    """Return attached schema names (excluding 'temp')."""
    rows = conn.execute("PRAGMA database_list").fetchall()
    return [r[1] for r in rows if r[1] not in ("temp",)]


def inventory(conn: sqlite3.Connection) -> Dict[str, Dict[str, int]]:
    """Return {schema: {table: row_count}} for all attached schemas."""
    result: Dict[str, Dict[str, int]] = {}
    for schema in _schemas(conn):
        tables = conn.execute(
            f"SELECT name FROM {schema}.sqlite_master "
            f"WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        entry: Dict[str, int] = {}
        for (table,) in tables:
            try:
                count = conn.execute(
                    f'SELECT COUNT(*) FROM {schema}."{table}"'
                ).fetchone()[0]
            except sqlite3.Error:
                count = -1
            entry[table] = count
        result[schema] = entry
    return result


def print_inventory(conn: sqlite3.Connection) -> None:
    """Print tables and row counts for every schema in the session."""
    inv = inventory(conn)
    for schema, tables in inv.items():
        print(f"[{schema}] {len(tables)} table(s)")
        for table, count in tables.items():
            print(f"    {schema}.{table:<24s} {count:>12,} rows")


def run_query(conn: sqlite3.Connection, sql: str) -> None:
    """Execute a single read-only query and print the result."""
    cursor = conn.execute(sql)
    if cursor.description is None:
        print(f"OK ({cursor.rowcount} rows affected)")
        return
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    print(" | ".join(columns))
    print("-+-".join("-" * len(c) for c in columns))
    for row in rows:
        print(" | ".join("" if v is None else str(v) for v in row))
    print(f"\n({len(rows)} row(s))")


def parse_attach_spec(specs: Optional[Iterable[str]]) -> Dict[str, Path]:
    """Parse ``--attach alias=path`` specs into a mapping."""
    out: Dict[str, Path] = {}
    for spec in specs or []:
        if "=" not in spec:
            raise ValueError(f"Invalid --attach value (expected alias=path): {spec!r}")
        alias, path = spec.split("=", 1)
        out[alias.strip()] = Path(path.strip())
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a SQL query across separately-stored source databases by "
            "ATTACH-ing them into one read-only session."
        ),
        epilog=(
            "Examples:\n"
            "  python src/query.py\n"
            "  python src/query.py \"SELECT COUNT(*) FROM main.somaktivitet\"\n"
            "  python src/query.py \"SELECT COUNT(*) FROM kuhr.kuhr WHERE aar = 2015\"\n"
            "  python src/query.py --primary npr \\\n"
            "      --attach kpr=db/kpr.db --attach kuhr=db/kuhr.db \\\n"
            "      \"SELECT * FROM main.somaktivitet s JOIN kpr.diagnose d \"\n"
            "      \"ON s.lopenr = d.lopenr LIMIT 5\""
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("sql", nargs="?", help="SQL query to run (optional)")
    parser.add_argument(
        "--primary",
        choices=sorted(DATASETS),
        default=DEFAULT_SOURCE,
        help="Source used as the primary ('main') database (default: %(default)s)",
    )
    parser.add_argument(
        "--primary-db",
        type=Path,
        default=None,
        help="Explicit path to the primary database (overrides --primary)",
    )
    parser.add_argument(
        "--attach",
        action="append",
        metavar="ALIAS=PATH",
        help="Attach an extra database (repeatable). Default: all other sources.",
    )
    parser.add_argument(
        "--no-attach",
        action="store_true",
        help="Do not automatically attach other registered sources",
    )
    parser.add_argument(
        "--read-write",
        action="store_true",
        help="Open databases read-write (default: read-only)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    primary = args.primary_db or resolve_source(args.primary)["db_file"]

    if args.no_attach and args.attach:
        # Explicit attachments still take precedence over --no-attach
        pass

    attached: Dict[str, Path]
    if args.attach:
        attached = parse_attach_spec(args.attach)
    elif args.no_attach:
        attached = {}
    else:
        attached = default_attachments(primary_source=args.primary)

    try:
        conn, used = connect_combined(
            primary, attached, read_only=not args.read_write
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        print(
            f"Session: main={used['main']} "
            + " ".join(f"{a}={p}" for a, p in used.items() if a != "main")
        )
        if args.sql:
            run_query(conn, args.sql)
        else:
            print_inventory(conn)
        return 0
    except sqlite3.Error as e:
        print(f"SQL error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())