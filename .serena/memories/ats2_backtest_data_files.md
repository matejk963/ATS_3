# ATS_2 Backtest and Historical Data Files

## Real Trading Data Sources

### Primary Market Data File
**File:** `dem07_25_tr_ba_data.parquet`
- **Cross-platform paths handled in code:**
  - Windows: `C:\\Users\\krajcovic\\Documents\\Testing Data\\backtest_data\\dem07_25_tr_ba_data.parquet`
  - WSL/Linux: `/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet`
- **Contains:** Bid/ask/trade data with OHLC-style price information
- **Used by:** Multiple backtest scripts for strategy testing

### Historical Data Files (Network Drives)
Multiple CSV files containing historical energy trading data:

**Lag Data Files:**
- `int_data_lag_dem2_*.csv` - DEM2 contract lag data
- `int_data_lag_deq1_*.csv` - DEQ1 contract lag data  
- `int_data_lag_frm1_*.csv` - FRM1 contract lag data
- `int_data_lag_dew1_*.csv` - DEW1 contract lag data
- `int_data_lag_production_sample.csv` - Production sample data

**Lead Data Files:**
- `int_data_lead_dem1_*.csv` - DEM1 contract lead data
- `int_data_lead_production_sample.csv` - Production lead sample

**Time Periods Covered:**
- `jan_feb`, `mar_apr`, `may_june`, `july`, `aug`, `sep_oct`, `nov`, `dec`
- Various test and production samples

### Data Structure
**Common Columns:**
- `datetime` - Timestamp
- `bid_price` - Bid prices
- `ask_price` - Ask prices
- `trd_price` - Trade prices (when available)
- `volume` - Trading volume
- `mid_price` - Calculated mid price
- Contract-specific fields for energy trading

### Swing Point Detection Suitable Data
The `dem07_25_tr_ba_data.parquet` file is ideal for swing point detection as it contains:
- High-frequency bid/ask data
- Trade prices for validation
- Datetime index for time series analysis
- Energy trading market data (German power market - DEM contracts)

## Network Drive Locations
- **S: Drive:** `s:\\Algo\\Files\\andrej\\Data\\` - Primary data storage
- **Z: Drive:** `z:\\andrej\\Data\\` - Alternative data location