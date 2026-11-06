"""Unit tests for the CSV loader module."""
import csv
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Add src to path for imports - use absolute path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from csv_loader import (
    convert_value,
    detect_delimiter,
    detect_encoding,
    filename_to_table_name,
    infer_column_type,
    infer_schema,
    is_null_value,
    load_csv_to_db,
    sanitize_column_name,
)
from database import DatabaseManager


class TestFilenameToTableName(unittest.TestCase):
    """Test filename to table name conversion."""

    def test_basic_conversion(self):
        self.assertEqual(filename_to_table_name("AVTaktivitet1.csv"), "avtaktivitet")
        self.assertEqual(filename_to_table_name("SOMkoder.csv"), "somkoder")
        self.assertEqual(filename_to_table_name("PHBUaktivitet1.csv"), "phbuaktivitet")

    def test_no_extension(self):
        self.assertEqual(filename_to_table_name("data.csv"), "data")

    def test_special_chars(self):
        self.assertEqual(filename_to_table_name("my-data file.csv"), "my_data_file")

    def test_trailing_digits_removed(self):
        self.assertEqual(filename_to_table_name("table123.csv"), "table")


class TestSanitizeColumnName(unittest.TestCase):
    """Test column name sanitization."""

    def test_basic(self):
        used = set()
        self.assertEqual(sanitize_column_name("Column Name", used), "column_name")

    def test_duplicate_names(self):
        used = set()
        first = sanitize_column_name("col", used)
        second = sanitize_column_name("col", used)
        self.assertEqual(first, "col")
        self.assertEqual(second, "col_1")

    def test_starts_with_digit(self):
        used = set()
        self.assertEqual(sanitize_column_name("123abc", used), "_123abc")

    def test_empty_name(self):
        used = set()
        self.assertEqual(sanitize_column_name("", used), "column")

    def test_special_characters(self):
        used = set()
        self.assertEqual(sanitize_column_name("a@b#c", used), "a_b_c")


class TestNullValue(unittest.TestCase):
    """Test NULL value detection."""

    def test_common_nulls(self):
        for val in ["", "NULL", "null", "NA", "N/A", "NaN", "None"]:
            self.assertTrue(is_null_value(val), f"{val} should be NULL")

    def test_non_nulls(self):
        for val in ["0", "abc", "123", "-1", "1.5", "F3201"]:
            self.assertFalse(is_null_value(val), f"{val} should not be NULL")


class TestInferColumnType(unittest.TestCase):
    """Test column type inference."""

    def test_integer(self):
        self.assertEqual(infer_column_type(["1", "2", "3"], "col"), "INTEGER")
        self.assertEqual(infer_column_type(["-1", "0", "42"], "col"), "INTEGER")

    def test_real(self):
        self.assertEqual(infer_column_type(["1.5", "2.0", "3.14"], "col"), "REAL")

    def test_text(self):
        self.assertEqual(infer_column_type(["abc", "def", "ghi"], "col"), "TEXT")
        self.assertEqual(infer_column_type(["1", "2", "abc"], "col"), "TEXT")

    def test_mixed_types(self):
        self.assertEqual(infer_column_type(["1", "2.5", "abc"], "col"), "TEXT")

    def test_all_null(self):
        self.assertEqual(infer_column_type(["", "NULL", "NA"], "col"), "TEXT")

    def test_code_column_forced_text(self):
        # ICD codes should stay TEXT even if numeric-looking
        self.assertEqual(
            infer_column_type(["F3201", "F329", "F33"], "hoveddiag"), "TEXT"
        )
        self.assertEqual(
            infer_column_type(["123", "456", "789"], "kode"), "TEXT"
        )

    def test_date_pattern(self):
        self.assertEqual(
            infer_column_type(["2020-01-01", "2021-06-15"], "dato"), "TEXT"
        )


class TestConvertValue(unittest.TestCase):
    """Test value conversion."""

    def test_integer_conversion(self):
        self.assertEqual(convert_value("42", "INTEGER"), 42)
        self.assertEqual(convert_value("-7", "INTEGER"), -7)
        self.assertIsNone(convert_value("abc", "INTEGER"))

    def test_real_conversion(self):
        self.assertEqual(convert_value("3.14", "REAL"), 3.14)
        self.assertEqual(convert_value("2,5", "REAL"), 2.5)  # European decimal
        self.assertIsNone(convert_value("abc", "REAL"))

    def test_text_conversion(self):
        self.assertEqual(convert_value("  hello  ", "TEXT"), "hello")
        self.assertEqual(convert_value("F3201", "TEXT"), "F3201")
        self.assertIsNone(convert_value("", "TEXT"))

    def test_null_conversion(self):
        for val in ["", "NULL", "NA", "N/A"]:
            self.assertIsNone(convert_value(val, "TEXT"))
            self.assertIsNone(convert_value(val, "INTEGER"))
            self.assertIsNone(convert_value(val, "REAL"))


class TestDetectEncoding(unittest.TestCase):
    """Test encoding detection."""

    def test_utf8(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("col1;col2\n1;2\n")
            f.flush()
            encoding = detect_encoding(Path(f.name))
            self.assertEqual(encoding, "utf-8-sig")
        os.unlink(f.name)

    def test_utf8_with_bom(self):
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(b"\xef\xbb\xbfcol1;col2\n1;2\n")
            f.flush()
            encoding = detect_encoding(Path(f.name))
            self.assertEqual(encoding, "utf-8-sig")
        os.unlink(f.name)

    def test_latin1(self):
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write("col1;col2\næ;ø\n".encode("latin-1"))
            f.flush()
            encoding = detect_encoding(Path(f.name))
            self.assertEqual(encoding, "latin-1")
        os.unlink(f.name)


class TestDetectDelimiter(unittest.TestCase):
    """Test delimiter detection."""

    def test_semicolon(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("col1;col2;col3\n1;2;3\n")
            f.flush()
            delimiter = detect_delimiter(Path(f.name), "utf-8")
            self.assertEqual(delimiter, ";")
        os.unlink(f.name)

    def test_comma(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("col1,col2,col3\n1,2,3\n")
            f.flush()
            delimiter = detect_delimiter(Path(f.name), "utf-8")
            self.assertEqual(delimiter, ",")
        os.unlink(f.name)

    def test_tab(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("col1\tcol2\tcol3\n1\t2\t3\n")
            f.flush()
            delimiter = detect_delimiter(Path(f.name), "utf-8")
            self.assertEqual(delimiter, "\t")
        os.unlink(f.name)


class TestInferSchema(unittest.TestCase):
    """Test schema inference from CSV files."""

    def test_basic_schema(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id;name;value\n1;abc;1.5\n2;def;2.5\n")
            f.flush()
            names, types = infer_schema(Path(f.name), "utf-8", ";")
            self.assertEqual(names, ["id", "name", "value"])
            self.assertEqual(types["id"], "INTEGER")
            self.assertEqual(types["name"], "TEXT")
            self.assertEqual(types["value"], "REAL")
        os.unlink(f.name)

    def test_icd_codes_stay_text(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("hoveddiag;antall\nF3201;3\nF329;4\n")
            f.flush()
            names, types = infer_schema(Path(f.name), "utf-8", ";")
            self.assertEqual(types["hoveddiag"], "TEXT")
            self.assertEqual(types["antall"], "INTEGER")
        os.unlink(f.name)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("")
            f.flush()
            names, types = infer_schema(Path(f.name), "utf-8", ";")
            self.assertEqual(names, [])
            self.assertEqual(types, {})
        os.unlink(f.name)


class TestLoadCsvToDb(unittest.TestCase):
    """Test end-to-end CSV loading into database."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close()
        # Clean up temp files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_basic_csv(self):
        csv_path = Path(self.temp_dir) / "testdata.csv"
        with open(csv_path, "w") as f:
            f.write("id;name;value\n1;abc;1.5\n2;def;2.5\n3;ghi;3.5\n")

        result = load_csv_to_db(csv_path, self.db)
        self.assertEqual(result.table_name, "testdata")
        self.assertEqual(result.rows_loaded, 3)
        self.assertEqual(result.rows_skipped, 0)

        # Verify data in database
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM testdata").fetchone()[0]
        self.assertEqual(count, 3)

        # Verify types
        row = conn.execute("SELECT * FROM testdata LIMIT 1").fetchone()
        self.assertEqual(row[0], 1)  # id as int
        self.assertEqual(row[1], "abc")  # name as str
        self.assertEqual(row[2], 1.5)  # value as float
        conn.close()

    def test_load_with_force(self):
        csv_path = Path(self.temp_dir) / "testdata.csv"
        with open(csv_path, "w") as f:
            f.write("id;name\n1;abc\n2;def\n")

        # Load twice with force
        load_csv_to_db(csv_path, self.db)
        result = load_csv_to_db(csv_path, self.db, force=True)
        self.assertEqual(result.rows_loaded, 2)

        # Verify only 2 rows (not 4)
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM testdata").fetchone()[0]
        self.assertEqual(count, 2)
        conn.close()

    def test_load_with_malformed_rows(self):
        csv_path = Path(self.temp_dir) / "testdata.csv"
        with open(csv_path, "w") as f:
            f.write("id;name\n1;abc\n2\n3;def\n")  # Row 2 has only 1 column

        result = load_csv_to_db(csv_path, self.db)
        self.assertEqual(result.rows_loaded, 2)
        self.assertEqual(result.rows_skipped, 1)

    def test_load_with_nulls(self):
        csv_path = Path(self.temp_dir) / "testdata.csv"
        with open(csv_path, "w") as f:
            f.write("id;name;value\n1;abc;\n2;;2.5\n3;def;3.5\n")

        result = load_csv_to_db(csv_path, self.db)
        self.assertEqual(result.rows_loaded, 3)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM testdata WHERE id=1").fetchone()
        self.assertIsNone(row[2])  # value is NULL
        row = conn.execute("SELECT * FROM testdata WHERE id=2").fetchone()
        self.assertIsNone(row[1])  # name is NULL
        conn.close()


if __name__ == "__main__":
    unittest.main()
