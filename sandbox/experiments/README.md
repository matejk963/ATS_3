# Comprehensive Parameter Combinations Test

This experiment demonstrates the corrected Phase 2 GPU pipeline processing real market data through **1,250 parameter combinations**.

## 🎯 Purpose

Test the corrected ATR and MACD implementations with real market data using various parameter combinations to validate:
- Algorithm correctness with different parameters
- GPU pipeline performance
- Real-world data processing capability

## 📊 Parameter Space

**Total Combinations: 1,250**

- **Candle Granularity**: [5, 10, 15, 20, 25] minutes (5 options)
- **ATR Periods**: [14, 21] (2 options)
- **MACD Parameters** (125 combinations):
  - Short EMA (se): [8, 9, 10, 11, 12] (5 options)
  - Long EMA (le): [16, 20, 26, 32, 38] (5 options)
  - Signal: [6, 9, 12, 15, 18] (5 options)

## 📁 Data Requirements

**Input Data**: 
The script automatically detects your environment and uses the appropriate path:
- **WSL**: `/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet`
- **PowerShell**: `C:\Users\krajcovic\Documents\Testing Data\backtest_data\dem07_25_tr_ba_data.parquet`
- Must contain a `price` column with datetime index

**Output Directory**:
Environment-specific output paths:
- **WSL**: `/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/interim_test/`
- **PowerShell**: `C:\Users\krajcovic\Documents\Testing Data\ATS_3_data\interim_test\`

## 🚀 Quick Start

### Method 1: Simple Runner (Recommended)
```bash
# Run from project root
pwsh -Command "python sandbox/experiments/run_combinations_test.py"
```

### Method 2: Direct Execution
```bash
# Run from project root  
pwsh -Command "python sandbox/experiments/comprehensive_parameter_combinations_test.py"
```

## 🔍 Environment Detection

The script automatically detects your execution environment and uses appropriate paths:

**Detection Logic:**
- **🪟 Native Windows** (`python.exe` from Windows): Uses `C:\` paths
- **🪟 PowerShell → WSL** (`pwsh -Command "python"`): Uses `C:\` paths  
- **🐧 Native WSL** (direct WSL execution): Uses `/mnt/c/` paths

**Smart Detection Features:**
- Detects PowerShell environment variables even when calling WSL Python
- Automatically selects correct path format for your execution method
- No manual configuration needed - it just works! ✨

## 📋 What the Test Does

1. **🔍 Detects Environment** and selects appropriate file paths automatically
2. **📥 Loads Real Market Data** from the parquet file (no sample data fallback)
3. **🔧 Generates 1,250 Parameter Combinations** programmatically
4. **⚡ Processes Each Combination** through the corrected Phase 2 GPU pipeline:
   - Computes ATR using the specified period
   - Computes MACD line, signal line, and histogram
5. **💾 Saves Results** to organized output folders:
   - `atr_results/` - ATR calculations for each combination
   - `macd_results/` - MACD calculations for each combination  
   - `combinations_metadata/` - Test summaries and metadata

## 📊 Output Structure

**Environment-specific base paths:**
- **WSL**: `/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/interim_test/`
- **PowerShell**: `C:\Users\krajcovic\Documents\Testing Data\ATS_3_data\interim_test\`

**Directory structure (same for both environments):**
```
{base_path}/
├── atr_results/
│   ├── atr_combo_0000.parquet
│   ├── atr_combo_0001.parquet
│   └── ... (1,250 files)
├── macd_results/
│   ├── macd_combo_0000.parquet
│   ├── macd_combo_0001.parquet
│   └── ... (1,250 files)
├── combinations_metadata/
│   ├── comprehensive_results.json
│   └── test_summary.json
└── performance_logs/
```

## ⚡ Performance Notes

- **Demo Mode**: By default, runs first 50 combinations (~5-10 minutes)
- **Full Mode**: Edit `comprehensive_parameter_combinations_test.py` line 314:
  ```python
  # Change from:
  test_combinations = combinations[:50]
  # To:
  test_combinations = combinations  # Full 1,250 combinations
  ```
- **Full run estimated time**: 2-4 hours depending on system performance

## 🔍 Monitoring Progress

The test provides real-time feedback:
- Individual combination processing status
- Progress updates every 10 combinations
- Processing time statistics
- Success/failure rates
- ETA for completion

## 📈 Expected Results

Each combination produces:
- **ATR Results**: DataFrame with columns `['datetime', 'nanotime', 'tradeid', 'atr']`
- **MACD Results**: DataFrame with columns `['datetime', 'nanotime', 'tradeid', 'macd', 'signal', 'histogram']`
- **Performance Metrics**: Processing time, data statistics, value ranges

## 🛠️ Customization

To modify the parameter space, edit `comprehensive_parameter_combinations_test.py`:

```python
def generate_parameter_combinations():
    # Modify these arrays to change parameter space
    candle_granularities = [5, 10, 15, 20, 25]  # minutes
    atr_periods = [14, 21]
    macd_se = [8, 9, 10, 11, 12]
    macd_le = [16, 20, 26, 32, 38] 
    macd_signal = [6, 9, 12, 15, 18]
```

## 🐛 Troubleshooting

**File Not Found Error**:
- Ensure the parquet file exists at the specified path
- Check Windows path formatting

**Import Errors**:
- The script now automatically detects project paths regardless of execution environment
- No need to manually set PYTHONPATH - imports are handled automatically
- Ensure all dependencies are installed

**Memory Issues**:
- Reduce the number of test combinations
- Close other applications to free memory

## 📊 Analysis

After running the test, you can analyze results by:
1. Loading individual parquet files for specific combinations
2. Reviewing `comprehensive_results.json` for overall performance metrics
3. Comparing different parameter combinations
4. Validating ATR and MACD calculations against expected values

## 🎯 Success Criteria

The test is successful if:
- Success rate > 90%
- All output files are created
- ATR and MACD values are within reasonable ranges
- No critical errors in processing

---

**Note**: This test validates the corrected Phase 2 GPU implementations maintain algorithm correctness while processing real market data through a comprehensive parameter space.