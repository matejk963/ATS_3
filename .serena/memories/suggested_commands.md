# Suggested Commands for ATS_2 Development

## Data Exploration Commands

### File System Navigation
```bash
# Navigate to ATS_2 repository
cd source_repos/ATS_2

# List strategy directories
ls -la EnergyTrading/Python/Strategies/

# Find data files
find . -name "*.parquet" -type f
find . -name "*.csv" -type f
```

### Search for Data Loading Patterns
```bash
# Find files using data_lag variable
grep -r "data_lag" --include="*.py" .

# Find CSV/Parquet data loading
grep -r "pd.read_csv\|pd.read_parquet" --include="*.py" .

# Search for specific data files
grep -r "dem07_25_tr_ba_data" --include="*.py" .
```

## Testing and Validation Commands

### Run Backtest Scripts
```bash
# PowerShell execution (preferred)
pwsh -Command "python backtest_multi_parallel_enhanced.py"
pwsh -Command "python backtest/test/backtest_101.py"

# Individual strategy testing
pwsh -Command "python EnergyTrading/Python/Strategies/LeadLagXGB/running_production_test.py"
```

### Data Quality Checks
```bash
# Run analysis scripts
pwsh -Command "python analysis/check_bid_ask_data_quality.py"
pwsh -Command "python analysis/debug_mtm_calculation.py"
```

## Development Utilities

### Git Operations
```bash
git status
git add .
git commit -m "Description"
git push origin main
```

### Python Environment
```bash
# Install requirements
pwsh -Command "pip install -r requirements.txt"

# Create conda environment
conda env create -f environment.yml
conda activate ats_environment
```

### Data File Access
```bash
# Cross-platform data access
ls -la "/mnt/c/Users/krajcovic/Documents/Testing Data/"
ls -la "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/"
```

## Debugging Commands

### Python Debugging
```bash
# Run with debugging
pwsh -Command "python -i script_name.py"
pwsh -Command "python -m pdb script_name.py"
```

### Log Analysis
```bash
# Check logs directory
ls -la logs/

# Monitor real-time logs
tail -f logs/strategy_execution.log
```