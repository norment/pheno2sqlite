"""Tests for multi-source (NPR/KPR) database handling and cross-DB queries."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Add src to path for imports - use absolute path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from config import DATASETS, resolve_source
from csv_loader import (
    extract_year,
    filename_to_table_name,
    load_all_csvs,
    should_force_text,
    table_name_for,
)
from database import DatabaseManager
from query import connect_combined, default_attachments, inventory, run_query


class TestDatasetRegistry(unittest.TestCase):
    """Test the dataset registry."""

    def test_known_sources(self):
        self.assertIn("npr", DATASETS)
        self.assertIn("kpr", DATASETS)
        self.assertIn("kuhr", DATASETS)

    def test_resolve_source(self):
        npr = resolve_source("npr")
        self.assertEqual(str(npr["db_file"]), "db/npr.db")
        kpr = resolve_source("kpr")
        self.assertEqual(str(kpr["db_file"]), "db/kpr.db")
        kuhr = resolve_source("kuhr")
        self.assertEqual(str(kuhr["db_file"]), "db/kuhr.db")

    def test_separate_db_files(self):
        self.assertNotEqual(
            str(resolve_source("npr")["db_file"]),
            str(resolve_source("kpr")["db_file"]),
        )
        self.assertNotEqual(
            str(resolve_source("npr")["db_file"]),
            str(resolve_source("kuhr")["db_file"]),
        )

    def test_unknown_source_raises(self):
        with self.assertRaises(KeyError):
            resolve_source("does-not-exist")


class TestKprTableNames(unittest.TestCase):
    """KPR filenames should map to clean table names."""

    def test_kpr_files(self):
        self.assertEqual(filename_to_table_name("diagnose.csv"), "diagnose")
        self.assertEqual(filename_to_table_name("regning.csv"), "regning")
        self.assertEqual(filename_to_table_name("takst.csv"), "takst")

    def test_no_collision_with_npr(self):
        npr_tables = {
            "avtaktivitet", "avtkoder", "phbuaktivitet", "phbukoder",
            "phvaktivitet", "phvkoder", "rehaktivitet", "rehkoder",
            "somaktivitet", "somkoder", "tsbaktivitet", "tsbkoder",
        }
        for fname in ("diagnose.csv", "regning.csv", "takst.csv"):
            self.assertNotIn(filename_to_table_name(fname), npr_tables)


class TestKuhrTableNames(unittest.TestCase):
    """KUHR yearly files should all map to the single 'kuhr' table."""

    def test_kuhr_files(self):
        cfg = resolve_source("kuhr")
        self.assertEqual(
            table_name_for("2006 Data fra KUHR 21-50907.dsv", cfg), "kuhr"
        )
        self.assertEqual(
            table_name_for("2023 Pr. 11.10.23 Data fra KUHR 21-50907.dsv", cfg),
            "kuhr",
        )

    def test_extract_year(self):
        self.assertEqual(extract_year("2006 Data fra KUHR 21-50907.dsv"), "2006")
        self.assertEqual(
            extract_year("2023 Pr. 11.10.23 Data fra KUHR 21-50907.dsv"), "2023"
        )

    def test_default_naming_unchanged(self):
        self.assertEqual(table_name_for("diagnose.csv"), "diagnose")
        self.assertEqual(
            table_name_for("diagnose.csv", resolve_source("kpr")), "diagnose"
        )


class TestSingleTableLoading(unittest.TestCase):
    """single_table datasets load all files into one table with a year column."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "kuhr.db"
        self.db = DatabaseManager(self.db_path)
        self.data_dir = Path(self.temp_dir) / "rawdata"
        self.data_dir.mkdir()
        for year in (2006, 2007):
            with open(
                self.data_dir / f"{year} Data fra KUHR 21-50907.dsv", "w"
            ) as f:
                f.write("pasientlopenummer;diagnoser\n")
                f.write(f"P{year};A00\n")
                f.write(f"P{year + 1};B00\n")

    def tearDown(self):
        self.db.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _cfg(self):
        return {
            "file_glob": "*.dsv",
            "single_table": True,
            "table_name": "kuhr",
            "year_column": "aar",
        }

    def test_single_table_with_year_column(self):
        results = load_all_csvs(self.data_dir, self.db, dataset_cfg=self._cfg())
        self.assertEqual(len(results), 2)
        self.assertEqual(self.db.list_tables("main"), ["kuhr"])
        self.assertIn("aar", self.db.get_table_columns("kuhr"))

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT aar, COUNT(*) FROM kuhr GROUP BY aar ORDER BY aar"
        ).fetchall()
        conn.close()
        self.assertEqual(rows, [(2006, 2), (2007, 2)])

    def test_reload_is_idempotent(self):
        load_all_csvs(self.data_dir, self.db, dataset_cfg=self._cfg())
        load_all_csvs(self.data_dir, self.db, dataset_cfg=self._cfg())
        conn = sqlite3.connect(self.db_path)
        n = conn.execute("SELECT COUNT(*) FROM kuhr").fetchone()[0]
        conn.close()
        self.assertEqual(n, 4)  # not 8

    def test_force_rebuilds_table(self):
        load_all_csvs(self.data_dir, self.db, dataset_cfg=self._cfg())
        load_all_csvs(self.data_dir, self.db, force=True, dataset_cfg=self._cfg())
        conn = sqlite3.connect(self.db_path)
        n = conn.execute("SELECT COUNT(*) FROM kuhr").fetchone()[0]
        conn.close()
        self.assertEqual(n, 4)

    def test_create_indexes_on_participant_and_year(self):
        load_all_csvs(
            self.data_dir, self.db, create_indexes=True, dataset_cfg=self._cfg()
        )
        conn = sqlite3.connect(self.db_path)
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='kuhr'"
            )
        }
        conn.close()
        self.assertIn("idx_kuhr_pasientlopenummer", indexes)
        self.assertIn("idx_kuhr_aar", indexes)


class TestCodeColumnDetection(unittest.TestCase):
    """ICPC-2 and ICD-10 code columns must be forced to TEXT."""

    def test_icpc_columns(self):
        for name in ("icpc", "icpc_kode", "icpc2", "diagnosekode"):
            self.assertTrue(should_force_text(name), name)

    def test_icd_columns(self):
        for name in ("hoveddiag", "kodeverdi", "kodenavn"):
            self.assertTrue(should_force_text(name), name)

    def test_plain_numeric_not_forced(self):
        for name in ("belop", "antall", "aar", "diffdager_inndato"):
            self.assertFalse(should_force_text(name), name)


class TestAttachAndJoin(unittest.TestCase):
    """Test ATTACH-based cross-database queries."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.npr_db = Path(self.temp_dir) / "npr.db"
        self.kpr_db = Path(self.temp_dir) / "kpr.db"
        self._make_npr(self.npr_db)
        self._make_kpr(self.kpr_db)

    def _make_npr(self, path: Path):
        db = DatabaseManager(path)
        db.create_table("somaktivitet", {"lopenr": "TEXT", "nokkel": "TEXT", "aar": "INTEGER"})
        db.begin_transaction()
        db.insert_rows(
            "somaktivitet",
            ["lopenr", "nokkel", "aar"],
            [("P1", "N1", 2010), ("P2", "N2", 2012), ("P3", "N3", 2015)],
        )
        db.commit()
        db.close()

    def _make_kpr(self, path: Path):
        db = DatabaseManager(path)
        db.create_table("diagnose", {"lopenr": "TEXT", "icpc": "TEXT"})
        db.begin_transaction()
        db.insert_rows(
            "diagnose",
            ["lopenr", "icpc"],
            [("P1", "P76"), ("P2", "F32")],
        )
        db.commit()
        db.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_attach_and_cross_join(self):
        conn, used = connect_combined(self.npr_db, {"kpr": self.kpr_db})
        try:
            self.assertIn("main", used)
            self.assertIn("kpr", used)
            rows = conn.execute(
                "SELECT s.lopenr, d.icpc "
                "FROM main.somaktivitet s "
                "JOIN kpr.diagnose d ON s.lopenr = d.lopenr "
                "ORDER BY s.lopenr"
            ).fetchall()
            self.assertEqual(rows, [("P1", "P76"), ("P2", "F32")])
        finally:
            conn.close()

    def test_attach_is_read_only_by_default(self):
        conn, _ = connect_combined(self.npr_db, {"kpr": self.kpr_db})
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO kpr.diagnose VALUES ('PX', 'A00')")
        finally:
            conn.close()

    def test_inventory_lists_both_schemas(self):
        conn, _ = connect_combined(self.npr_db, {"kpr": self.kpr_db})
        try:
            inv = inventory(conn)
            self.assertIn("main", inv)
            self.assertIn("kpr", inv)
            self.assertEqual(inv["main"]["somaktivitet"], 3)
            self.assertEqual(inv["kpr"]["diagnose"], 2)
        finally:
            conn.close()

    def test_database_manager_attach(self):
        db = DatabaseManager(self.npr_db)
        try:
            alias = db.attach(self.kpr_db, read_only=True)
            self.assertEqual(alias, "kpr")
            rows = db.conn.execute(
                "SELECT COUNT(*) FROM kpr.diagnose"
            ).fetchone()
            self.assertEqual(rows[0], 2)
            db.detach("kpr")
        finally:
            db.close()

    def test_database_manager_get_schema(self):
        db = DatabaseManager(self.kpr_db)
        try:
            schema = db.get_schema("main")
            self.assertIn("diagnose", schema)
            cols = dict(schema["diagnose"])
            self.assertEqual(cols["lopenr"], "TEXT")
            self.assertEqual(cols["icpc"], "TEXT")
        finally:
            db.close()


class TestDefaultAttachments(unittest.TestCase):
    """Default attachments should exclude the primary and missing files."""

    def test_excludes_primary(self):
        attached = default_attachments(primary_source="npr", require_exists=False)
        self.assertNotIn("npr", attached)
        self.assertIn("kpr", attached)


if __name__ == "__main__":
    unittest.main()