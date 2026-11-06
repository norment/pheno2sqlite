# mobapheno2sqlite - MoBa Study NPR, KPR & KUHR CSV to SQLite Database Loaders

Load Norwegian Patient Register (NPR), Kontroll og utbetaling av helserefusjoner (KPR/KUHR) and similar CSV files into separate on-disk SQLite databases for querying.
This tool is not aimed at replacing other tools for handling MoBa study phenotyping information such as phenotools (https://github.com/psychgen/phenotools),
but to serve as a way to make flexible SQL database style quires within single or across multiple datasources (e.g., KPR, KUHR, LMR, MBR, NPR, SSB, mobaQ).
The current implementation has been developed and tested on NPR, KPR and KUHR data.
It also does not filter out withdrawn participants who should not be used for analyses.

## Overview

This tool reads tabularized CSV files from Norwegian health registers and loads each data source into its **own dedicated SQLite database**:

| Source | Input directory | SQLite database | Code systems |
|--------|-----------------|-----------------|--------------|
| **NPR** - Norwegian Patient Register (specialist care) | `raw/npr/2026-10-19/rawdata/` | `db/npr.db` | ICD-10, NCSP, NCMP |
| **KPR** - Kontroll og utbetaling av helserefusjoner (primary-care claims) | `raw/kpr/2026-10-19/rawdata/` | `db/kpr.db` | ICPC-2 |
| **KUHR** - Kontroll og utbetaling av helserefusjoner (primary-care claims) | `raw/kuhr/2023-10-23/rawdata/` | `db/kuhr.db` | ICPC-2 |

Databases are **deliberately kept separate** for data-governance / ethics reasons (data are approved per user and per source) and are **never merged on disk**. An authorized user who may access several sources can still query them *together* in a single session using SQLite's `ATTACH DATABASE` (see the "Querying multiple sources" section below).

Each database can be queried independently using standard SQL, `pandas`, or R, exactly as before.

## Installation

### Prerequisites

- **Python 3.9+** with `pip` installed
- Access to the raw NPR/KPR/KUHR CSV files (placed in `raw/<registry>/<date>/rawdata/`). A script to symlink source directories is `link_phenodirs.sh` and is provided to symlink the phenotype directories into `raw/`. Modify it as needed.

### Setup

Clone the repository and install dependencies:

```bash
# Clone the repository
git clone <repository-url>
cd mobapheno2sqlite

# (Recommended) Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# Install required dependencies using pyproject.toml file
pip install .

# link registry information in TSD p697
bash link_phenodirs.sh
```

On specific infrastructure such as TSD hosted by USIT at University of Oslo, you may want to preload specific software modules before creating the virtual environment:

```bash
module load Python/3.12.3-GCCcore-13.3.0 SciPy-bundle/2024.05-gfbf-2024a
```


### Dependencies

The project requires the following Python packages:

| Package | Version | Purpose |
|---------|---------|---------|
| `pandas` | >= 2.0.0 | CSV parsing and data manipulation |
| `numpy` | >= 1.21.0 | Numerical operations |
| `pytest` | >= 7.0.0 | Testing (development only) |
| `pytest-cov` | >= 4.0 | Testing (development only) |

Only the standard library `sqlite3` module is used for database access - no additional database driver is needed.

### Verify Installation

Run the tests to confirm everything is set up correctly:

```bash
python -m pytest tests/ -v
```

### Downloading the Data

The raw NPR CSV files should be placed in `raw/npr/2026-10-19/rawdata/`. The expected files are:

```
raw/npr/2026-10-19/rawdata/
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

The raw KUHR files should be placed in `raw/kuhr/2023-10-23/rawdata/` as one delimiter-separated (`.dsv`) file per delivery year:

```
raw/kuhr/2023-10-23/rawdata/
├── 2006 Data fra KUHR 21-50907.dsv
├── 2007 Data fra KUHR 21-50907.dsv
├── ...
└── 2023 Pr. 11.10.23 Data fra KUHR 21-50907.dsv
```

> **Note**: These files contain protected health data and are not included in the repository. Obtain them through the appropriate KUHR data access process.

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

### KUHR

The KUHR delivery is a set of delimiter-separated (`.dsv`) files, one per year (2006 - 2023). All years share an identical schema, so they are loaded into a **single table** named `kuhr`, with the delivery year injected into an `aar` column (matching the NPR convention):

| Table | Year column | Source files |
|-------|-------------|--------------|
| `kuhr` | `aar` | `2006 Data fra KUHR 21-50907.dsv` … `2023 Pr. 11.10.23 Data fra KUHR 21-50907.dsv` |

KUHR claims carry ICPC-2 codes; code-like columns are forced to `TEXT` (see [Database Schema](#database-schema)). Re-loading a year replaces that year's rows (idempotent), and `--force` rebuilds the whole table. Note that KUHR's participant identifier column is named `pasientlopenummer` (NPR/KPR use `lopenr`), so cross-source joins match `pasientlopenummer` to `lopenr`.

## Usage

### Load all CSV files into the database

```bash
python src/main.py --force --verbose
```

### Load a specific source (e.g. KUHR)

```bash
# KUHR: one .dsv file per year -> single 'kuhr' table with an 'aar' column
python src/main.py --source kuhr --force --verbose
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
| `--create-indexes` | Auto-create indexes on `*_id`, participant-id (`lopenr`/`pasientlopenummer`/`pasientid`) and year (`aar`) columns |

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

## Querying multiple sources

The NPR (`db/npr.db`), KPR (`db/kpr.db`) and KUHR (`db/kuhr.db`) databases live in **separate files** and are never merged on disk (see [Security](#security)). A user approved for *several* sources can still query them **together** in one SQLite session by **ATTACH-ing** the other databases onto one. The attachment is:

- **session-scoped** - it exists only for the lifetime of the connection and is never written back to disk;
- **read-only by default** - a joint query cannot accidentally modify any source;
- **per-user** - only a user/process that can read *all* the files can attach them, so per-source approvals are respected.

Inside a session the primary database is `main`; each attached database is exposed under an alias (here `kpr` and `kuhr`). Cross-source queries join on the shared pseudonymized participant id — `lopenr` in NPR and KPR, and `pasientlopenummer` in KUHR. KUHR is stored as a single `kuhr` table with the delivery year in an `aar` column, so filter by year, e.g. `kuhr.kuhr WHERE aar = 2015`.

> **Performance:** cross-source joins on `lopenr` can be slow because each database is built independently and columns are unindexed by default. Run the loader with `--create-indexes` (or create indexes on `lopenr`/`nokkel` yourself) before running many joins.

### Option A - bundled helper: `src/query.py`

`src/query.py` opens one source as `main`, automatically ATTACHes every other existing source as a **read-only** companion, and runs a single SQL statement (or prints an inventory):

```bash
# Inventory of every table visible in the combined session
# (main + kpr + kuhr, whichever databases exist)
python src/query.py

# Count rows in an attached (KPR) table
python src/query.py "SELECT COUNT(*) FROM kpr.regning"

# Count rows in an attached (KUHR) table for a single delivery year
python src/query.py "SELECT COUNT(*) FROM kuhr.kuhr WHERE aar = 2015"

# Cross-source join: NPR specialist care + KPR primary-care claims
python src/query.py "SELECT n.lopenr, r.aar AS kpr_year FROM main.somaktivitet n JOIN kpr.regning r ON n.lopenr = r.lopenr LIMIT 5"

# Cross-source join: NPR specialist care + KUHR primary-care claims (slow)
python src/query.py "SELECT n.lopenr FROM main.somaktivitet n JOIN kuhr.kuhr k ON n.lopenr = k.pasientlopenummer AND k.aar = 2015 LIMIT 2"

# Three-way join across all sources (slow)
python src/query.py "SELECT n.lopenr FROM main.somaktivitet n JOIN kpr.regning r ON n.lopenr = r.lopenr JOIN kuhr.kuhr k ON n.lopenr = k.pasientlopenummer AND k.aar = 2015 LIMIT 2"

# Make KUHR the primary database (others are then attached as 'npr', 'kpr')
python src/query.py --primary kuhr "SELECT COUNT(*) FROM npr.somaktivitet"

# Control attachments explicitly
python src/query.py --no-attach --attach kpr=db/kpr.db --attach kuhr=db/kuhr.db \
    "SELECT COUNT(*) FROM kuhr.kuhr WHERE aar = 2015"
```

### Option B - Python (`sqlite3`)

```python
import sqlite3

# Open the primary database read-only and ATTACH the other sources read-only
conn = sqlite3.connect("file:db/npr.db?mode=ro", uri=True)
conn.execute("ATTACH DATABASE 'file:db/kpr.db?mode=ro'  AS kpr")
conn.execute("ATTACH DATABASE 'file:db/kuhr.db?mode=ro' AS kuhr")

# What is visible now?
print(conn.execute("PRAGMA database_list").fetchall())

# Cross-source join on the shared participant id (lopenr)
rows = conn.execute(
    "SELECT n.lopenr, n.aar AS npr_year, r.aar AS kpr_year "
    "FROM main.somaktivitet n "
    "JOIN kpr.regning r ON n.lopenr = r.lopenr LIMIT 10"
).fetchall()
print(rows)

# Two-way join NPR + KUHR
kuhr_rows = conn.execute(
    "SELECT n.lopenr FROM main.somaktivitet n "
    "JOIN kuhr.kuhr k ON n.lopenr = k.pasientlopenummer AND k.aar = 2015 LIMIT 10"
).fetchall()
print(kuhr_rows)

conn.close()
```

### Option C - pandas

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("file:db/npr.db?mode=ro", uri=True)
conn.execute("ATTACH DATABASE 'file:db/kpr.db?mode=ro'  AS kpr")
conn.execute("ATTACH DATABASE 'file:db/kuhr.db?mode=ro' AS kuhr")

df = pd.read_sql(
    "SELECT a.lopenr, a.aar AS npr_year, r.aar AS kpr_year, "
    "       k.kodeverdi AS icd10, d.diagnosekode AS icpc "
    "FROM main.somaktivitet a "
    "JOIN main.somkoder  k ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel "
    "JOIN kpr.regning    r ON r.lopenr = a.lopenr "
    "LEFT JOIN kpr.diagnose d ON d.lopenr = r.lopenr AND d.nokkel = r.nokkel "
    "WHERE k.kodenavn = 'ICD-10' LIMIT 100",
    conn,
)
print(df.head())

# Bring KUHR (one year at a time) into the same frame
kuhr = pd.read_sql(
    "SELECT DISTINCT a.lopenr FROM main.somaktivitet a "
    "JOIN kuhr.kuhr k ON a.lopenr = k.pasientlopenummer AND k.aar = 2015 LIMIT 100",
    conn,
)
print(kuhr.head())

conn.close()
```

### Option D - R (RSQLite)

```r
library(DBI)
library(RSQLite)

con <- dbConnect(SQLite(), "db/npr.db")

# Attach the KPR and KUHR databases (plain paths; use a 'file:...?mode=ro' URI
# if your driver supports URI filenames for read-only access).
dbExecute(con, "ATTACH DATABASE 'db/kpr.db'  AS kpr")
dbExecute(con, "ATTACH DATABASE 'db/kuhr.db' AS kuhr")

print(dbGetQuery(con, "PRAGMA database_list"))

joined <- dbGetQuery(con, "
    SELECT n.lopenr, n.aar AS npr_year, r.aar AS kpr_year
    FROM main.somaktivitet n
    JOIN kpr.regning    r ON n.lopenr = r.lopenr
    LIMIT 10
")
print(joined)

kuhr_join <- dbGetQuery(con, "
    SELECT n.lopenr
    FROM main.somaktivitet n
    JOIN kuhr.kuhr k ON n.lopenr = k.pasientlopenummer AND k.aar = 2015
    LIMIT 10
")
print(kuhr_join)

dbDisconnect(con)
```

### Option E - command-line `sqlite3`

```bash
sqlite3 db/npr.db
# Inside the interactive shell:
ATTACH DATABASE 'file:db/kpr.db?mode=ro'  AS kpr;
ATTACH DATABASE 'file:db/kuhr.db?mode=ro' AS kuhr;

SELECT n.lopenr, r.aar
FROM main.somaktivitet n
JOIN kpr.regning r ON n.lopenr = r.lopenr
LIMIT 5;

SELECT n.lopenr
FROM main.somaktivitet n
JOIN kuhr.kuhr k ON n.lopenr = k.pasientlopenummer AND k.aar = 2015
LIMIT 5;
```

### Cross-source query examples

Participants present in **both** specialist care (NPR ICD-10 `F*`) and primary care (KPR ICPC-2 `P*`):

```sql
ATTACH DATABASE 'file:db/kpr.db?mode=ro' AS kpr;

SELECT DISTINCT a.lopenr
FROM main.somkoder k
JOIN main.somaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE k.kodenavn = 'ICD-10' AND k.kodeverdi LIKE 'F%'
INTERSECT
SELECT DISTINCT d.lopenr
FROM kpr.diagnose d
WHERE d.diagnosekode LIKE 'P%';
```

Participants appearing in **all three** sources for a given year:

```sql
ATTACH DATABASE 'file:db/kpr.db?mode=ro'  AS kpr;
ATTACH DATABASE 'file:db/kuhr.db?mode=ro' AS kuhr;

SELECT DISTINCT n.lopenr
FROM main.somaktivitet n
JOIN kpr.regning    r ON r.lopenr = n.lopenr
JOIN kuhr.kuhr k ON k.pasientlopenummer = n.lopenr AND k.aar = 2015
LIMIT 50;
```

Within-source KPR joins (year `aar` lives in `regning`; join `diagnose`/`takst` to it on `(lopenr, nokkel)`):

```sql
-- KPR: ICPC-2 diagnoses with the year of the claim
SELECT r.aar, d.diagnosekode
FROM kpr.regning r
JOIN kpr.diagnose d ON d.lopenr = r.lopenr AND d.nokkel = r.nokkel
LIMIT 10;
```

Combined NPR + KPR + KUHR timeline for the same individuals (filter KUHR by year with `kuhr.aar`):

```sql
ATTACH DATABASE 'file:db/kpr.db?mode=ro' AS kpr;

SELECT n.lopenr, n.aar AS npr_year, k.kodeverdi AS icd10_code,
       r.aar AS kpr_year, d.diagnosekode AS icpc2_code, t.takstkode AS tariff_code
FROM main.somaktivitet n
JOIN main.somkoder   k ON k.lopenr = n.lopenr AND k.nokkel = n.nokkel
LEFT JOIN kpr.regning r ON r.lopenr = n.lopenr
LEFT JOIN kpr.diagnose d ON d.lopenr = r.lopenr AND d.nokkel = r.nokkel
LEFT JOIN kpr.takst   t ON t.lopenr = r.lopenr AND t.nokkel = r.nokkel
WHERE k.kodenavn = 'ICD-10'
LIMIT 50;
```

Count participants/contacts per source for the same individuals:

```sql
ATTACH DATABASE 'file:db/kpr.db?mode=ro'  AS kpr;
ATTACH DATABASE 'file:db/kuhr.db?mode=ro' AS kuhr;

SELECT 'NPR'  AS source, COUNT(DISTINCT lopenr) AS n_participants FROM main.somaktivitet
UNION ALL
SELECT 'KPR',  COUNT(DISTINCT lopenr) FROM kpr.regning
UNION ALL
SELECT 'KUHR', COUNT(DISTINCT pasientlopenummer) FROM kuhr.kuhr WHERE aar = 2015;
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

### 3. Alzheimer's dementia across primary and specialist care (KPR/KUHR ICPC-2 `P70` + NPR ICD-10 `G30`/`F00`)

A broader Alzheimer's definition also captures contacts in **primary care**, where diagnoses are recorded as **ICPC-2** codes rather than ICD-10:

| Source | Database | Table(s) | Code column | Code system | Code |
|--------|----------|----------|-------------|-------------|------|
| **KPR** | `db/kpr.db` | `diagnose` (+ `regning` for `aar`) | `diagnosekode` | `diagnosetabell = 'ICPC-2'` | `P70%` |
| **KUHR** | `db/kuhr.db` | `kuhr` | `diagnoser` | `diagnosekodeverk = 'ICPC-2'` | `P70%` |
| **NPR** | `db/npr.db` | `*koder` (+ `*aktivitet` for `aar`) | `kodeverdi` | `kodenavn = 'ICD-10'` | `G30%`, `F00%` |

`P70` is *Dementia* (including Alzheimer's dementia) in ICPC-2; the `%` wildcard picks up all subcodes (`P700`, `P700000`, `P704`, …).

Two schema details matter:

- **KUHR's `diagnoser` is a comma-separated list** of up to several ICPC-2 codes per claim (`'P70, K86, T90'`), not a single code. A plain `LIKE 'P70%'` therefore misses `P70` when it is not the first code, so match both the start of the string and the post-comma position: `diagnoser LIKE 'P70%' OR diagnoser LIKE '%, P70%'`.
- **KPR's `diagnosekode` is one code per row**, joined to `regning` on `(lopenr, nokkel)` to obtain the claim year `aar`.

#### 3a. Union - any participant with Alzheimer's in *either* care level

```sql
ATTACH DATABASE 'file:db/kpr.db?mode=ro' AS kpr;
ATTACH DATABASE 'file:db/kuhr.db?mode=ro' AS kuhr;

WITH primary_care AS (
    -- KPR: one ICPC-2 code per row ('P70', 'P700', 'P704', ...)
    SELECT d.lopenr AS participant_id, 'KPR' AS source, r.aar AS year,
           d.diagnosekode AS code
    FROM kpr.diagnose d
    JOIN kpr.regning  r ON r.lopenr = d.lopenr AND r.nokkel = d.nokkel
    WHERE d.diagnosetabell LIKE 'ICPC-2%'
      AND d.diagnosekode   LIKE 'P70%'

    UNION ALL

    -- KUHR: 'diagnoser' is a comma-separated list ('P70, K86, T90')
    SELECT pasientlopenummer, 'KUHR', aar, diagnoser
    FROM kuhr.kuhr
    WHERE diagnosekodeverk LIKE 'ICPC-2%'
      AND (diagnoser LIKE 'P70%' OR diagnoser LIKE '%, P70%')
),
specialist_care AS (
    SELECT k.lopenr AS participant_id, 'NPR-som' AS domain,
           a.aar AS year, k.kodeverdi AS code
    FROM main.somkoder k
    JOIN main.somaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
    WHERE k.kodenavn = 'ICD-10'
      AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')

    UNION ALL
    SELECT k.lopenr, 'NPR-phv', a.aar, k.kodeverdi
    FROM main.phvkoder k
    JOIN main.phvaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
    WHERE k.kodenavn = 'ICD-10'
      AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')

    UNION ALL
    SELECT k.lopenr, 'NPR-avt', a.aar, k.kodeverdi
    FROM main.avtkoder k
    JOIN main.avtaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
    WHERE k.kodenavn = 'ICD-10'
      AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')

    UNION ALL
    SELECT k.lopenr, 'NPR-reh', a.aar, k.kodeverdi
    FROM main.rehkoder k
    JOIN main.rehaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
    WHERE k.kodenavn = 'ICD-10'
      AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')

    UNION ALL
    SELECT k.lopenr, 'NPR-tsb', a.aar, k.kodeverdi
    FROM main.tsbkoder k
    JOIN main.tsbaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
    WHERE k.kodenavn = 'ICD-10'
      AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')

    UNION ALL
    -- PHBU has no kodenavn column: all codes are ICD-10
    SELECT k.lopenr, 'NPR-phbu', a.aar, k.kodeverdi
    FROM main.phbukoder k
    JOIN main.phbuaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
    WHERE k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%'
)
SELECT participant_id,
       MIN(year) AS first_year,
       MAX(year) AS last_year,
       GROUP_CONCAT(DISTINCT source) AS primary_care_sources,
       GROUP_CONCAT(DISTINCT domain) AS specialist_care_domains
FROM (
    SELECT participant_id, year, source, NULL AS domain FROM primary_care
    UNION ALL
    SELECT participant_id, year, NULL, domain FROM specialist_care
)
GROUP BY participant_id
ORDER BY participant_id;
```

Each participant appears once; `primary_care_sources` / `specialist_care_domains` are `NULL` when the participant was found in only one care level, which makes it easy to see *where* the Alzheimer's code came from.

#### 3b. Intersection - participants confirmed in *both* care levels

Primary-care `P70` plus a specialist-care `G30`/`F00` confirmation (a stricter, better-supported Alzheimer's phenotype):

```sql
ATTACH DATABASE 'file:db/kpr.db?mode=ro'  AS kpr;
ATTACH DATABASE 'file:db/kuhr.db?mode=ro' AS kuhr;

CREATE TEMP TABLE pc_p70 AS
SELECT d.lopenr AS participant_id, 'KPR' AS source, r.aar AS year
FROM kpr.diagnose d
JOIN kpr.regning r ON r.lopenr = d.lopenr AND r.nokkel = d.nokkel
WHERE d.diagnosetabell LIKE 'ICPC-2%' AND d.diagnosekode LIKE 'P70%'
UNION ALL
SELECT pasientlopenummer, 'KUHR', aar
FROM kuhr.kuhr
WHERE diagnosekodeverk LIKE 'ICPC-2%'
  AND (diagnoser LIKE 'P70%' OR diagnoser LIKE '%, P70%');

CREATE TEMP TABLE npr_ad AS
SELECT k.lopenr AS participant_id, 'NPR-som' AS domain, a.aar AS year
FROM main.somkoder k
JOIN main.somaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE k.kodenavn = 'ICD-10'
  AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION ALL
SELECT k.lopenr, 'NPR-phv', a.aar
FROM main.phvkoder k
JOIN main.phvaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE k.kodenavn = 'ICD-10'
  AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION ALL
SELECT k.lopenr, 'NPR-avt', a.aar
FROM main.avtkoder k
JOIN main.avtaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE k.kodenavn = 'ICD-10'
  AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION ALL
SELECT k.lopenr, 'NPR-reh', a.aar
FROM main.rehkoder k
JOIN main.rehaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE k.kodenavn = 'ICD-10'
  AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION ALL
SELECT k.lopenr, 'NPR-tsb', a.aar
FROM main.tsbkoder k
JOIN main.tsbaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE k.kodenavn = 'ICD-10'
  AND (k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%')
UNION ALL
SELECT k.lopenr, 'NPR-phbu', a.aar
FROM main.phbukoder k
JOIN main.phbuaktivitet a ON a.lopenr = k.lopenr AND a.nokkel = k.nokkel
WHERE k.kodeverdi LIKE 'G30%' OR k.kodeverdi LIKE 'F00%';

-- Temp indexes make the cross-source joins fast
CREATE INDEX temp.idx_pc_p70 ON pc_p70(participant_id);
CREATE INDEX temp.idx_npr_ad ON npr_ad(participant_id);

SELECT p.participant_id,
       MIN(p.year) AS first_primary_care_year,
       MAX(p.year) AS last_primary_care_year,
       MIN(n.year) AS first_specialist_year,
       MAX(n.year) AS last_specialist_year,
       GROUP_CONCAT(DISTINCT p.source) AS primary_care_sources,
       GROUP_CONCAT(DISTINCT n.domain) AS specialist_care_domains
FROM pc_p70 p
JOIN npr_ad n ON n.participant_id = p.participant_id
GROUP BY p.participant_id
ORDER BY p.participant_id;
```

#### 3c. Summary counts for the three definitions

Run this in the **same session** as 3b - it re-uses the `pc_p70` and `npr_ad` temp tables, so the databases are already attached (re-running `ATTACH` would fail with `database kpr is already in use`):

```sql
SELECT 'primary care P70 only' AS criterion,
       COUNT(DISTINCT participant_id) AS n_participants FROM pc_p70
UNION ALL
SELECT 'specialist care G30/F00 only', COUNT(DISTINCT participant_id) FROM npr_ad
UNION ALL
SELECT 'both (intersection)', COUNT(*) FROM (
    SELECT DISTINCT participant_id FROM pc_p70
    INTERSECT
    SELECT DISTINCT participant_id FROM npr_ad
)
UNION ALL
SELECT 'either (union)', COUNT(DISTINCT participant_id) FROM (
    SELECT participant_id FROM pc_p70
    UNION
    SELECT participant_id FROM npr_ad
);
```

> **Note:** the `%` wildcard is deliberate - `G30%`/`F00%` cover all ICD-10 subcodes (`G300`, `G309`, `F000`, `F001`, …) and `P70%` covers the ICPC-2 subcodes (`P700`, `P700000`, `P704`, …). If you need the exact code *and* its subcodes only, use `kodeverdi IN ('G30','F00') OR kodeverdi LIKE 'G30_%' OR kodeverdi LIKE 'F00_%'` instead. Also note that `diagnoser` in KUHR may contain trailing/leading spaces, so `TRIM()` the individual codes if you split the list yourself.

> **Performance:** the cross-source joins are the slow part (roughly a minute on the full delivery). Run the loaders with `--create-indexes` first, and keep the temp tables + temp indexes shown in 3b rather than joining the raw tables repeatedly.

The same query can be run without leaving the shell via the bundled helper (which ATTACHes the other sources read-only automatically):

```bash
python src/query.py "SELECT COUNT(DISTINCT d.lopenr) FROM kpr.diagnose d WHERE d.diagnosekode LIKE 'P70%'"
python src/query.py "SELECT COUNT(DISTINCT pasientlopenummer) FROM kuhr.kuhr WHERE diagnosekodeverk LIKE 'ICPC-2%' AND (diagnoser LIKE 'P70%' OR diagnoser LIKE '%, P70%')"
```

### 4. All diagnoses and corresponding timepoints for a given participant

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

### 5. Additional useful queries

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
- **KUHR table** (`kuhr`): one row per claim across all years, with the delivery year in an `aar` column and ICPC-2 code columns forced to `TEXT`

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
├── raw/npr/2026-10-19/rawdata/       # Input CSV files
├── raw/kuhr/2023-10-23/rawdata/      # KUHR yearly .dsv files
└── db/npr.db              # Output database
```

## License

See LICENSE file.
