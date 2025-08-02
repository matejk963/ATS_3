# Instructions for Using `DB_reader.py` to Access a Database

This guide is for AI agents or developers who need to use the `DB_reader.py` module to access and interact with databases in the EnergyTrading project.

## 1. Overview
- `DB_reader.py` provides a `Database` class for connecting to, querying, and managing data in various databases (PostgreSQL, Oracle, TimescaleDB, etc.).
- It uses SQLAlchemy and pandas for database operations and data handling.

## 2. Prerequisites
- Ensure all dependencies are installed (see `pyproject.toml` or `environment.yml`).
- The database connection configuration must be available as a JSON file, typically loaded via `Common.config_load.get_config_path()`.
- Required enums and config loaders are imported from `Enums.py` and `Common/config_load.py`.

## 3. Basic Usage

### a. Import and Initialize
```python
from Database.DB_reader import Database

db = Database(database='PostgreSQL')  # or 'oracle', 'timescaledb', etc.
```
- The `database` argument must match a key in your config JSON.

### b. Running a Query
```python
sql = "SELECT * FROM your_table WHERE column = :value"
params = {"value": 123}
df = db.execute(sql, params)
```
- Returns a pandas DataFrame with the results.

### c. Selecting Data by Table
```python
df = db.select('your_table', cols='col1,col2', range=30)
```
- Returns data for the last 30 days by default.

### d. Get Spot Price Data
```python
df = db.getSpotPriceData(['de', 'at'], range=7)
```
- Returns spot price data for specified markets.

## 4. Notes
- All connections are managed automatically; you do not need to manually connect/disconnect.
- For advanced usage (upserts, deletes, custom queries), see the method docstrings in `DB_reader.py`.
- Errors are printed to stdout; handle exceptions as needed in your code.

## 5. Example
```python
from Database.DB_reader import Database

db = Database(database='PostgreSQL')
df = db.execute('SELECT * FROM my_table')
print(df.head())
```

---
For more details, refer to the source code and docstrings in `DB_reader.py`.
