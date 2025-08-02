# Understanding `get_trades_data` in `Database\Timescale\utils.py`

This document explains how the `get_trades_data` function in `Database\Timescale\utils.py` fetches trade data from the database and provides an example of how to reproduce its functionality.

## 1. Function Overview: `get_trades_data`

The `get_trades_data` function is designed to retrieve and process trade data for a specified financial instrument over a given date range. It handles filtering by allowed broker IDs and removing duplicate entries.

**Function Signature:**
```python
def get_trades_data(instrument: str, start_date_str: str, end_date_str: str) -> pd.DataFrame:
```

**Parameters:**
-   `instrument` (str): The financial instrument identifier (e.g., 'deq1'). This is used to determine the market, tenor, and other instrument-specific parameters.
-   `start_date_str` (str): The start date for fetching trades, formatted as 'YYYY-MM-DD'.
-   `end_date_str` (str): The end date for fetching trades, formatted as 'YYYY-MM-DD'.

**Returns:**
-   `pd.DataFrame`: A DataFrame containing the processed trade data. The DataFrame will have a 'datetime' index and include columns from the trades table.

## 2. Data Fetching Mechanism

The `get_trades_data` function internally relies on the `TPData` class (from `Database.TPData`) to interact with the database. Here's the breakdown of the data fetching process:

1.  **Initialization of `TPData`:** An instance of `TPData` is created, and a database connection is established using `data_class.create_connection('timescaledb')`. This connects to the TimescaleDB database configured in the project.

2.  **Date Iteration:** The function iterates through each business day within the specified `start_date_str` and `end_date_str`.

3.  **Calling `TPData.get_trades_tsdb`:** For each day, `get_trades_data` calls `data_class.get_trades_tsdb()` with relevant parameters derived from the `instrument` and the current date.

4.  **`TPData.get_trades_tsdb` Query Construction:**
    -   Inside `TPData.get_trades_tsdb`, a SQL query is constructed using the `self.tsdb_trade_query` property. This query targets the `public.trades` table in the TimescaleDB.
    -   The query filters data based on:
        -   `instname`: Derived from the `market` and `venue_list`.
        -   `firstsequenceid`: Derived from the commodity and tenor.
        -   `secondsequenceitemid`: Used for spreads, typically 0 for single instruments.
        -   `firstsequenceitemid`: Derived from the tenor and product date.
        -   `datetime`: Filtered by the `bT` (begin time) and `eT` (end time) parameters, which represent the start and end of the trading day.

5.  **Database Execution:** The constructed SQL query and its parameters are passed to `self.db_connection.execute()`. The `self.db_connection` object is an instance of `Database` from `Database.DB_reader`, which handles the actual execution of the SQL query against the TimescaleDB and returns the results as a pandas DataFrame.

6.  **Post-processing:** After fetching, the raw trade data is further processed:
    -   Filtered by `allwd_broker_ids` (currently `[1441]`).
    -   Duplicate entries based on 'datetime' are removed, keeping the last occurrence.
    -   The DataFrame index is set to 'datetime'.

## 3. Reproducing Data Fetching

To reproduce the data fetching logic of `get_trades_data`, you can directly use the `TPData` class and its `get_trades_tsdb` method, along with the `Database` class for connection.

**Example:**

```python
import pandas as pd
from datetime import datetime, time

# Assuming these imports are available in your environment
from Database.TPData import TPData
from Database.DB_reader import Database # Although TPData handles this internally, good to know

# --- Parameters for reproduction ---
instrument = 'deq1'  # Example instrument
start_date_str = '2025-05-01'
end_date_str = '2025-05-01' # Fetching for a single day for simplicity

# --- Simulate internal logic of get_trades_data to get parameters for get_trades_tsdb ---
# This part is simplified for demonstration. In get_trades_data, these are derived dynamically.
# You would need to replicate the logic from variables_from_instrument, product_dates, etc.
# For a direct call to get_trades_tsdb, you need:
market = 'de'
tenor = 'q'
venue_list = ['eex']
prod = 'base'
start_date1 = datetime.strptime(start_date_str, '%Y-%m-%d').date() # This would be the product date
start_date2 = None # For single instruments, secondsequenceitemid is 0

bT = datetime.combine(start_date1, time(9, 0, 0, 0)) # Example start time
eT = datetime.combine(start_date1, time(17, 40, 0, 0)) # Example end time

# --- Actual data fetching using TPData ---
data_class = TPData()
data_class.create_connection('timescaledb') # Ensure your TimescaleDB is configured

# Call get_trades_tsdb directly
trades_df = data_class.get_trades_tsdb(
    market=market,
    tenor=tenor,
    venue_list=venue_list,
    start_date1=start_date1,
    bT=bT,
    eT=eT,
    prod=prod,
    start_date2=start_date2
)

print(trades_df.head())
print(trades_df.info())

# To see the raw SQL query that would be executed (conceptual, not directly runnable without DB_reader context):
# The query is constructed within TPData.get_trades_tsdb using self.tsdb_trade_query
# and parameters are formatted before being sent to the database.
# Example of the query structure:
# query_structure = data_class.tsdb_trade_query
# print(query_structure)
```

**Important Notes for Reproduction:**
-   Ensure your database connection details for 'timescaledb' are correctly configured in your project's configuration files (typically loaded via `Common.config_load.get_config_path()`).
-   The `instrument` parameter in `get_trades_data` is parsed to determine `market`, `tenor`, `tn`, etc. For direct calls to `get_trades_tsdb`, you need to provide these derived parameters explicitly.
-   The `bT` and `eT` (begin and end times) are typically set to cover the trading hours of a day.
