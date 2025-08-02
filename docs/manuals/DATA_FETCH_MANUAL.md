# Data Fetch Pipeline Output

**Single parquet file per contract** containing combined trade and order data.

**Structure:** 9 columns total
- **6 trade columns:** price, volume, action, broker_id, count, tradeid
- **2 order columns:** b_price (bid), a_price (ask) 
- **1 calculated column:** mid_price

**File format:** `{market}{tenor}{contract}_tr_ba_data.parquet`
**Example:** `dem07_25_tr_ba_data.parquet` (815KB, 53,867 rows)
- `de` = German market, `m` = Monthly, `07_25` = July 2025

**Output path:** `/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_data/temp/`

**Index:** DatetimeIndex with synchronized timestamps across all data types.