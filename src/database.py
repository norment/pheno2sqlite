"""SQLite database management for the NPR CSV loader."""
import logging
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
        # explicit transactions via BEGIN/COMMIT for batch operations)
        conn = sqlite3.connect(str(self.db_path))
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