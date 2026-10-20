# pheno2sqlite - NPR CSV to SQLite Database Loader

Load Norwegian Patient Register (NPR) CSV files into an on-disk SQLite database for querying.

## Overview

This tool reads tabularized CSV files from `raw/npr/rawdata/` and loads them into a SQLite database (`db/npr.db`). The database can then be queried by other users/processes using standard SQL or pandas.

## Installation

### Prerequisites

- **Python 3.9+** with `pip` installed
- Access to the raw NPR CSV files (placed in `raw/npr/rawdata/`)

### Setup

Clone the repository and install dependencies:

```bash
# Clone the repository
git clone <repository-url>
cd pheno2sqlite

# (Recommended) Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# Install required dependencies using pyproject.toml file
pip install .
```


### Dependencies

The project requires the following Python packages:

| Package | Version | Purpose |
|---------|---------|---------|
| `pandas` | >= 1.3.0 | CSV parsing and data manipulation |
| `numpy` | >= 1.21.0 | Numerical operations |
| `pytest` | >= 7.0.0 | Testing (development only) |

Only the standard library `sqlite3` module is used for database access - no additional database driver is needed.

### Verify Installation

Run the tests to confirm everything is set up correctly:

```bash
python -m pytest tests/ -v
```

### Downloading the Data

The raw NPR CSV files should be placed in `raw/npr/rawdata/`. The expected files are:

```
raw/npr/rawdata/
├── avtaktivitet.csv
├── avtkoder.csv
├── phbuaktivitet.csv
├── phbukoder.csv
├── phvaktivitet.csv
├── phvkoder.csv
├── rehaktivitet.csv
├── rehkoder.csv
├── somaktivitet.csv
├── somkoder.csv
├── tsbaktivitet.csv
└── tsbkoder.csv
```

> **Note**: These files contain protected health data and are not included in the repository. Obtain them through the appropriate NPR data access process.

## Data

The 12 CSV files represent 6 domains of Norwegian health register data (2008 - Aug 2026):

| Domain | Activity Table | Codes Table | Description |
|--------|---------------|-------------|-------------|
| AVT | `avtaktivitet` | `avtkoder` | Avtalespesialister (private specialists) |
| PHBU | `phbuaktivitet` | `phbukoder` | Psykisk helse - BUP (child psychiatry) |
| PHV | `phvaktivitet` | `phvkoder` | Psykisk helse - Voksen (adult psychiatry) |
| REH | `rehaktivitet` | `rehkoder` | Rehabilitering (rehabilitation) |
| SOM | `somaktivitet` | `somkoder` | Somatikk (somatic care) |
| TSB | `tsbaktivitet` | `tsbkoder` | Tverrfaglig rusbehandling (substance abuse) |

## Usage

### Load all CSV files into the database

```bash
python src/main.py --force --verbose
```

### Load specific tables

```bash
python src/main.py --tables somaktivitet,somkoder --force
```

### Dry run (show what would happen)

```bash
python src/main.py --dry-run --verbose
```

### Options

| Option | Description |
|--------|-------------|
| `--input-dir` | Directory containing CSV files (default: `raw/npr/rawdata`) |
| `--output-db` | Output SQLite database path (default: `db/npr.db`) |
| `--tables` | Comma-separated table names to load (default: all) |
| `--force` | Drop and recreate existing tables |
| `--verbose` | Enable detailed debug logging |
| `--dry-run` | Show what would be done without executing |
| `--create-indexes` | Auto-create indexes on `*_id` and `pasientid` columns |

## Querying the Database

### Using Python with sqlite3

```python
import sqlite3

conn = sqlite3.connect('db/npr.db')

# List all tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

# Query a table
rows = conn.execute('SELECT * FROM somaktivitet LIMIT 10').fetchall()

# Aggregate query
counts = conn.execute('''
    SELECT aar, COUNT(*) 
    FROM somaktivitet 
    GROUP BY aar 
    ORDER BY aar
''').fetchall()

# Count participants with Alzheimer's per domain
count_ad = conn.execute('''
    SELECT 'som' AS domain, COUNT(DISTINCT k.lopenr) AS n_alzheimers
    FROM somkoder k JOIN somaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
    WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
    UNION ALL
    SELECT 'phv', COUNT(DISTINCT k.lopenr)
    FROM phvkoder k JOIN phvaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
    WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
''').fetchall()

conn.close()
```

### Using pandas

```python
import pandas as pd
import sqlite3

conn = sqlite3.connect('db/npr.db')

# Read table into DataFrame
df = pd.read_sql('SELECT * FROM somaktivitet', conn)

# Join across tables (always join on BOTH lopenr AND nokkel)
joined = pd.read_sql('''
    SELECT a.*, k.kodenavn, k.kodeverdi
    FROM somaktivitet a
    JOIN somkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
    WHERE k.kodenavn = 'ICD-10'
    LIMIT 1000
''', conn)

conn.close()
```

### Using R with RSQLite

```r
library(DBI)
library(RSQLite)

# Connect to the database
con <- dbConnect(SQLite(), "db/npr.db")

# List all tables
tables <- dbListTables(con)
print(tables)

# Read a table into a data.frame
somaktivitet <- dbGetQuery(con, "SELECT * FROM somaktivitet LIMIT 100")

# Aggregate query
counts_by_year <- dbGetQuery(con, "
    SELECT aar, COUNT(*) AS n
    FROM somaktivitet
    GROUP BY aar
    ORDER BY aar
")
print(counts_by_year)

# Join across tables (always join on BOTH lopenr AND nokkel)
joined <- dbGetQuery(con, "
    SELECT a.*, k.kodenavn, k.kodeverdi
    FROM somaktivitet a
    JOIN somkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
    WHERE k.kodenavn = 'ICD-10'
    LIMIT 1000
")

# Always close the connection when done
dbDisconnect(con)
```

### Using R with dplyr + dbplyr (tidyverse style)

```r
library(DBI)
library(RSQLite)
library(dplyr)
library(dbplyr)

# Connect to the database
con <- dbConnect(SQLite(), "db/npr.db")

# Reference tables as lazy tibbles
somaktivitet <- tbl(con, "somaktivitet")
somkoder <- tbl(con, "somkoder")

# Query using dplyr verbs
counts_by_year <- somaktivitet %>%
    group_by(aar) %>%
    summarise(n = n()) %>%
    arrange(aar) %>%
    collect()  # Execute query and load into R
print(counts_by_year)

# Join across tables (always join on BOTH lopenr AND nokkel)
joined <- somaktivitet %>%
    inner_join(somkoder, by = c("lopenr" = "lopenr", "nokkel" = "nokkel")) %>%
    filter(kodenavn == "ICD-10") %>%
    head(1000) %>%
    collect()

# Always close the connection when done
dbDisconnect(con)
```

### Using command-line sqlite3

```bash
sqlite3 db/npr.db
# Then run SQL queries:
# SELECT * FROM somaktivitet LIMIT 10;
# SELECT aar, COUNT(*) FROM somaktivitet GROUP BY aar;
```

## Example SQL Queries

### 1. Return all unique participant identifiers

Get all unique `lopenr` (participant IDs) across all domains:

```sql
-- All unique participants in somatic care
SELECT DISTINCT lopenr
FROM somaktivitet
ORDER BY lopenr;

-- All unique participants across ALL domains (union)
SELECT DISTINCT lopenr FROM avtaktivitet
UNION
SELECT DISTINCT lopenr FROM phbuaktivitet
UNION
SELECT DISTINCT lopenr FROM phvaktivitet
UNION
SELECT DISTINCT lopenr FROM rehaktivitet
UNION
SELECT DISTINCT lopenr FROM somaktivitet
UNION
SELECT DISTINCT lopenr FROM tsbaktivitet
ORDER BY lopenr;

-- Count unique participants per domain
SELECT 'avt' AS domain, COUNT(DISTINCT lopenr) AS n_participants FROM avtaktivitet
UNION ALL SELECT 'phbu', COUNT(DISTINCT lopenr) FROM phbuaktivitet
UNION ALL SELECT 'phv', COUNT(DISTINCT lopenr) FROM phvaktivitet
UNION ALL SELECT 'reh', COUNT(DISTINCT lopenr) FROM rehaktivitet
UNION ALL SELECT 'som', COUNT(DISTINCT lopenr) FROM somaktivitet
UNION ALL SELECT 'tsb', COUNT(DISTINCT lopenr) FROM tsbaktivitet;
```

### 2. Participants with Alzheimer's dementia (ICD-10 G30.*, F00.*) and year of diagnosis

Alzheimer's disease is coded as **G30** (Alzheimer's disease) and **F00** (Dementia in Alzheimer's disease) in ICD-10. The codes are stored in the `*koder` tables with `kodenavn = 'ICD-10'`.

```sql
-- Participants with Alzheimer's (G30*) in somatic care, with year
SELECT DISTINCT
    k.lopenr,
    a.aar AS diagnosis_year,
    k.kodeverdi AS icd10_code
FROM somkoder k
JOIN somaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10'
  AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
ORDER BY k.lopenr, a.aar;

-- Same query but across ALL domains (union of all activity/code pairs)
SELECT DISTINCT k.lopenr, a.aar AS diagnosis_year, k.kodeverdi AS icd10_code
FROM somkoder k JOIN somaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION
SELECT DISTINCT k.lopenr, a.aar, k.kodeverdi
FROM phvkoder k JOIN phvaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION
SELECT DISTINCT k.lopenr, a.aar, k.kodeverdi
FROM phbukoder k JOIN phbuaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%'
UNION
SELECT DISTINCT k.lopenr, a.aar, k.kodeverdi
FROM avtkoder k JOIN avtaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION
SELECT DISTINCT k.lopenr, a.aar, k.kodeverdi
FROM rehkoder k JOIN rehaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION
SELECT DISTINCT k.lopenr, a.aar, k.kodeverdi
FROM tsbkoder k JOIN tsbaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
ORDER BY k.lopenr, diagnosis_year;

-- Count participants with Alzheimer's per domain
SELECT 'som' AS domain, COUNT(DISTINCT k.lopenr) AS n_alzheimers
FROM somkoder k JOIN somaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION ALL
SELECT 'phv', COUNT(DISTINCT k.lopenr)
FROM phvkoder k JOIN phvaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10' AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%');
```

### 3. All diagnoses and corresponding timepoints for a given participant

For a specific participant (replace `'Fm000000'` with the actual `lopenr`):

```sql
-- All diagnoses for one participant in somatic care
SELECT
    a.aar AS year,
    a.diffdager_inndato AS days_since_epoch_in,
    a.diffdager_utdato AS days_since_epoch_out,
    k.kodenavn AS code_system,
    k.kodeverdi AS diagnosis_code
FROM somaktivitet a
JOIN somkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE a.lopenr = 'Fm000000'
  AND k.kodenavn = 'ICD-10'
ORDER BY a.aar, a.diffdager_inndato;

-- All diagnoses for one participant across ALL domains (replace lopenr 'Fm000000' with a real one)
SELECT 'som' AS domain, a.aar AS year, k.kodenavn AS code_system, k.kodeverdi AS diagnosis_code
FROM somaktivitet a JOIN somkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE a.lopenr = 'Fm000000' AND k.kodenavn = 'ICD-10'
UNION ALL
SELECT 'phv', a.aar, k.kodenavn, k.kodeverdi
FROM phvaktivitet a JOIN phvkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE a.lopenr = 'Fm000000' AND k.kodenavn = 'ICD-10'
UNION ALL
SELECT 'phbu', a.aar, 'ICD-10', k.kodeverdi
FROM phbuaktivitet a JOIN phbukoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE a.lopenr = 'Fm000000'
UNION ALL
SELECT 'avt', a.aar, k.kodenavn, k.kodeverdi
FROM avtaktivitet a JOIN avtkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE a.lopenr = 'Fm000000' AND k.kodenavn = 'ICD-10'
UNION ALL
SELECT 'reh', a.aar, k.kodenavn, k.kodeverdi
FROM rehaktivitet a JOIN rehkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE a.lopenr = 'Fm000000' AND k.kodenavn = 'ICD-10'
UNION ALL
SELECT 'tsb', a.aar, k.kodenavn, k.kodeverdi
FROM tsbaktivitet a JOIN tsbkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE a.lopenr = 'Fm000000' AND k.kodenavn = 'ICD-10'
ORDER BY domain, year;
```

### 4. Additional useful queries

#### Count records per year per domain

```sql
SELECT 'som' AS domain, aar, COUNT(*) AS n_records
FROM somaktivitet
GROUP BY aar
UNION ALL
SELECT 'phv', aar, COUNT(*)
FROM phvaktivitet
GROUP BY aar
UNION ALL
SELECT 'phbu', aar, COUNT(*)
FROM phbuaktivitet
GROUP BY aar
ORDER BY domain, aar;
```

#### Most common ICD-10 diagnoses in somatic care

```sql
SELECT k.kodeverdi AS icd10_code, COUNT(DISTINCT k.lopenr) AS n_participants
FROM somkoder k
WHERE k.kodenavn = 'ICD-10'
GROUP BY k.kodeverdi
ORDER BY n_participants DESC
LIMIT 20;
```

#### Participants with a specific diagnosis (e.g., diabetes E10-E14)

```sql
SELECT DISTINCT k.lopenr, MIN(a.aar) AS first_year, MAX(a.aar) AS last_year
FROM somkoder k
JOIN somaktivitet a ON k.lopenr = a.lopenr AND k.nokkel = a.nokkel
WHERE k.kodenavn = 'ICD-10'
  AND (k.kodeverdi LIKE 'E10%' OR k.kodeverdi LIKE 'E11%'
       OR k.kodeverdi LIKE 'E12%' OR k.kodeverdi LIKE 'E13%'
       OR k.kodeverdi LIKE 'E14%')
GROUP BY k.lopenr
ORDER BY k.lopenr;
```

#### Participants with both mental health (F*) and somatic diagnoses

```sql
SELECT DISTINCT som.lopenr
FROM somkoder som_k
JOIN somaktivitet som ON som_k.lopenr = som.lopenr AND som_k.nokkel = som.nokkel
WHERE som_k.kodenavn = 'ICD-10' AND som_k.kodeverdi LIKE 'F%'
INTERSECT
SELECT DISTINCT phv.lopenr
FROM phvkoder phv_k
JOIN phvaktivitet phv ON phv_k.lopenr = phv.lopenr AND phv_k.nokkel = phv.nokkel
WHERE phv_k.kodenavn = 'ICD-10' AND phv_k.kodeverdi LIKE 'F%';
```

#### Participants with no recorded diagnoses (activity but no codes)

```sql
SELECT a.lopenr
FROM somaktivitet a
LEFT JOIN somkoder k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE k.nokkel IS NULL
GROUP BY a.lopenr
LIMIT 100;
```

### Understanding the data model

- **`lopenr`**: Participant identifier (pseudonymized). Same participant has the same `lopenr` across all tables.
- **`nokkel`**: Record key that links an activity record to its associated codes. Join on `(lopenr, nokkel)`.
- **`aar`**: Year of the activity/contact.
- **`diffdager_inndato` / `diffdager_utdato`**: Days since a reference date (likely 1970-01-01) for admission and discharge dates. To convert to a date: `DATE('1970-01-01', '+' || diffdager_inndato || ' days')`.
- **`kodenavn`**: Code system name - `'ICD-10'` for diagnoses, `'NCSP'` for procedures, `'NCMP'` for medications.
- **`kodeverdi`**: The actual code value (e.g., `'F3201'`, `'G309'`, `'NBJ12'`).
- **`kodetype` / `kodenr`**: Internal code type and number identifiers.

### Converting days-since-epoch to actual dates

```sql
-- Convert diffdager_inndato to a proper date
SELECT
    lopenr,
    aar,
    DATE('1970-01-01', '+' || diffdager_inndato || ' days') AS admission_date,
    DATE('1970-01-01', '+' || diffdager_utdato || ' days') AS discharge_date
FROM somaktivitet
LIMIT 10;
```

## Database Schema

All tables use only three SQLite types: `INTEGER`, `REAL`, and `TEXT`.

- **Activity tables** (`*aktivitet`): Patient activity records with columns like `lopenr` (patient ID), `nokkel` (record key), `aar` (year), and various clinical codes
- **Codes tables** (`*koder`): Reference codes with columns like `lopenr`, `nokkel`, `kodenavn` (code system name), `kodetype`, `kodenr`, `kodeverdi` (the actual code value)

## Performance

- **24.5M rows** loaded across 12 tables in ~2 minutes
- Uses WAL mode for concurrent read access
- Batch inserts with explicit transactions for speed
- `errors='replace'` for robust handling of encoding issues

## Security

⚠️ **This contains sensitive Norwegian health data (NPR)**

- The database file (`db/npr.db`) should have restricted file permissions
- Only run on secure infrastructure (e.g., TSD)
- Do not share the database file outside the secure environment
- The tool does not log actual data values, only filenames and row counts

## Development

### Running tests

```bash
python -m pytest tests/ -v
```

### Project structure

```
├── src/
│   ├── config.py          # Configuration constants
│   ├── csv_loader.py      # CSV parsing, schema inference, loading
│   ├── database.py        # SQLite connection and table management
│   └── main.py            # CLI entry point
├── tests/
│   └── test_csv_loader.py # Unit tests
├── raw/npr/rawdata/       # Input CSV files
└── db/npr.db              # Output database
```

## License

See LICENSE file.
