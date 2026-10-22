"""SQLite database management for the CSV loaders (NPR, KPR, ...)."""
import logging
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import DB_FILE, PRAGMAS

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database connection and table operations."""

    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        """Create connection with production-ready pragmas."""
        # Use default isolation_level (None means autocommit, but we'll use
        # explicit transactions via BEGIN/COMMIT for batch operations).
        # ``uri=True`` allows read-only ATTACH of companion databases
        # (e.g. 'file:/path/kpr.db?mode=ro'); ordinary paths without a
        # 'file:' prefix are still treated as plain filenames.
        conn = sqlite3.connect(str(self.db_path), uri=True)
        for key, value in PRAGMAS.items():
            try:
                conn.execute(f"PRAGMA {key}={value}")
            except sqlite3.Error as e:
                logger.warning(f"Failed to set PRAGMA {key}={value}: {e}")
        return conn

    def create_table(self, table_name: str, columns: Dict[str, str]) -> None:
        """
        Create table if it doesn't exist.

        Args:
            table_name: Sanitized table name
            columns: Mapping of column_name -> sql_type (INTEGER/REAL/TEXT)
        """
        col_defs = [
            f'"{name}" {type_}'
            for name, type_ in columns.items()
        ]
        if not col_defs:
            raise ValueError(f"No columns provided for table {table_name}")

        sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)})'
        try:
            self.conn.execute(sql)
            self.conn.commit()
            logger.debug(f"Created table {table_name} with {len(col_defs)} columns")
        except sqlite3.Error as e:
            logger.error(f"Failed to create table {table_name}: {e}")
            raise

    def drop_table(self, table_name: str) -> None:
        """Drop a table if it exists."""
        try:
            self.conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            self.conn.commit()
            logger.debug(f"Dropped table {table_name} (if existed)")
        except sqlite3.Error as e:
            logger.error(f"Failed to drop table {table_name}: {e}")
            raise

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
        result = self.conn.execute(query, (table_name,)).fetchone()
        return result is not None

    def begin_transaction(self) -> None:
        """Begin an explicit transaction for batch inserts."""
        self.conn.execute("BEGIN")

    def commit(self) -> None:
        """Commit the current transaction."""
        self.conn.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.conn.rollback()

    def insert_rows(
        self,
        table_name: str,
        columns: List[str],
        rows: List[Tuple],
    ) -> int:
        """
        Insert rows in batch using executemany.
        Uses plain INSERT (not OR REPLACE) for speed.
        Caller is responsible for managing transactions.

        Args:
            table_name: Target table name
            columns: List of column names (must match DB schema)
            rows: List of tuples to insert

        Returns:
            Number of rows inserted
        """
        if not rows:
            return 0

        placeholders = ",".join(["?"] * len(columns))
        col_str = ",".join([f'"{c}"' for c in columns])
        sql = f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders})'

        try:
            cursor = self.conn.executemany(sql, rows)
            return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Failed to insert into {table_name}: {e}")
            if rows:
                sample = rows[0]
                logger.debug(f"First row sample: {sample}")
            raise

    def get_table_columns(self, table_name: str) -> List[str]:
        """Get column names for a table."""
        try:
            cursor = self.conn.execute(f'PRAGMA table_info("{table_name}")')
            return [row[1] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get columns for {table_name}: {e}")
            return []

    def get_row_count(self, table_name: str) -> int:
        """Get row count for a table."""
        try:
            cursor = self.conn.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            return cursor.fetchone()[0]
        except sqlite3.Error:
            return 0

    def create_index(
        self, table_name: str, column_name: str, index_name: Optional[str] = None
    ) -> None:
        """Create an index on a column for faster queries."""
        if not index_name:
            index_name = f"idx_{table_name}_{column_name}"
        try:
            self.conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                f'ON "{table_name}" ("{column_name}")'
            )
            self.conn.commit()
            logger.debug(f"Created index {index_name} on {table_name}.{column_name}")
        except sqlite3.Error as e:
            logger.warning(f"Failed to create index {index_name}: {e}")

    # ------------------------------------------------------------------
    # Multi-source support (attach companion databases / inspect schemas)
    # ------------------------------------------------------------------

    def list_tables(self, schema: str = "main") -> List[str]:
        """List user tables in the given schema ("main" or an attached alias)."""
        schema = self._safe_identifier(schema, "schema")
        try:
            cursor = self.conn.execute(
                f"SELECT name FROM {schema}.sqlite_master "
                f"WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                f"ORDER BY name"
            )
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to list tables in schema {schema}: {e}")
            return []

    def get_schema(self, schema: str = "main") -> Dict[str, List[Tuple[str, str]]]:
        """Return {table_name: [(column, type), ...]} for a schema."""
        schema = self._safe_identifier(schema, "schema")
        out: Dict[str, List[Tuple[str, str]]] = {}
        for table in self.list_tables(schema):
            try:
                cursor = self.conn.execute(f'PRAGMA {schema}.table_info("{table}")')
                out[table] = [(row[1], row[2]) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.warning(f"Failed to read schema for {schema}.{table}: {e}")
        return out

    @staticmethod
    def _safe_identifier(name: str, kind: str = "identifier") -> str:
        """Validate a SQLite identifier we intend to interpolate (schema name)."""
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name or ""):
            raise ValueError(f"Unsafe {kind}: {name!r}")
        return name

    @staticmethod
    def _to_uri(db_path: Path, read_only: bool = True) -> str:
        """Build a 'file:' URI for ATTACH, optionally read-only."""
        resolved = Path(db_path).expanduser().resolve()
        mode = "ro" if read_only else "rw"
        return f"file:{resolved}?mode={mode}"

    def attach(
        self,
        db_path: Path,
        alias: Optional[str] = None,
        read_only: bool = True,
    ) -> str:
        """ATTACH a companion database for cross-source queries.

        The attached database lives only in this connection's session; nothing
        is written back or merged. Read-only by default so a joint query cannot
        accidentally modify the companion source.

        Args:
            db_path: Path to the SQLite file to attach.
            alias: Schema name to expose it under (default: file stem).
            read_only: Attach with ``mode=ro`` (default) or ``mode=rw``.

        Returns:
            The schema alias used for the attached database.
        """
        if alias is None:
            alias = Path(db_path).stem
        alias = self._safe_identifier(alias, "alias")
        uri = self._to_uri(db_path, read_only=read_only)
        try:
            self.conn.execute(f'ATTACH DATABASE ? AS "{alias}"', (uri,))
            logger.info(
                f"Attached {db_path} as '{alias}' "
                f"({'read-only' if read_only else 'read-write'})"
            )
            return alias
        except sqlite3.Error as e:
            logger.error(f"Failed to attach {db_path} as '{alias}': {e}")
            raise

    def detach(self, alias: str) -> None:
        """DETACH a previously attached database."""
        alias = self._safe_identifier(alias, "alias")
        try:
            self.conn.execute(f'DETACH DATABASE "{alias}"')
        except sqlite3.Error as e:
            logger.warning(f"Failed to detach '{alias}': {e}")

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            try:
                self.conn.commit()
            except sqlite3.Error:
                pass
            self.conn.close()
            logger.debug(f"Closed database connection to {self.db_path}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # Don't suppress exceptions
