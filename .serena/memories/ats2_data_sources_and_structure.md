# ATS_2 Data Sources and Repository Structure

## Key Data Sources Found

### 1. Files with "data_lag" Variable Definitions
Multiple files throughout the repository contain `data_lag` variable definitions, primarily for backtesting and strategy calibration:

**Main Files:**
- `/source_repos/ATS_2/backtest_multi_parallel_enhanced.py` - Main parallel backtest script
- `/source_repos/ATS_2/backtest/calibration.py` - Calibration framework
- Multiple strategy files in `/source_repos/ATS_2/EnergyTrading/Python/Strategies/*/`

### 2. Real Market Data File Paths

**Primary Market Data File:**
- `dem07_25_tr_ba_data.parquet` - Main bid/ask trading data used across multiple scripts
  - Windows path: `C:\\Users\\krajcovic\\Documents\\Testing Data\\backtest_data\\dem07_25_tr_ba_data.parquet`
  - WSL/Linux path: `/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet`

**Historical Data Paths (from various calibration scripts):**
- `s:\\Algo\\Files\\andrej\\Data\\int_data_lag_*.csv` - Historical lag data
- `s:\\Algo\\Files\\andrej\\Data\\int_data_lead_*.csv` - Historical lead data  
- `z:\\andrej\\Data\\int_data_*.csv` - Alternative data source paths

### 3. Data File Formats and Content
The market data contains:
- **bid_price, ask_price** - Bid/ask spread data
- **trd_price** - Trade prices
- **volume** - Trading volumes
- **datetime** - Timestamp information
- **mid_price** - Mid-price calculations

### 4. Key Directories for Data Loading

**Main Directories:**
- `/source_repos/ATS_2/backtest/` - Contains main backtesting framework
- `/source_repos/ATS_2/EnergyTrading/Python/Strategies/` - Various trading strategies
- `/source_repos/ATS_2/analysis/` - Analysis scripts using the data

**Strategy Directories with Data Loading:**
- `BA_convergence/` - Bid-ask convergence strategies
- `LeadLagFromDatamart/` - Lead-lag strategies from datamart
- `LeadLagRegression_strategy/` - Regression-based lead-lag
- `LeadLagXGB/` - XGBoost-based lead-lag
- `LeadLag_strategy/` - General lead-lag strategies
- `SpotTraining/` - Spot market training strategies

### 5. Data Processing Patterns
- Data is typically loaded with `pd.read_csv()` or `pd.read_parquet()`
- Datetime columns are parsed and converted to proper format
- Trading hours are filtered (typically 8 AM to 6 PM)
- Data is merged between lag and lead instruments for lead-lag strategies