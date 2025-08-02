# Data Fetcher Implementation Plan

**Goal:** Build `src/core/data_fetcher.py` with flexible contract-specific date handling

## Phase 1: Core Infrastructure & Testing

1. **Test TPData connectivity** - Verify `TPData` imports and connects properly from EnergyTrading utilities
2. **Create delivery date calculator** - Function to convert tenor/contract to first delivery date
3. **Build date range resolver** - Convert lookback days to start/end dates from delivery date
4. **Create DataFetcher class** - Clean interface with flexible input system

## Phase 2: Enhanced Input System

5. **Implement unified contract configuration** - Single contract list used for both trades and orders (no separate aux lists)
6. **Add input validation** - Ensure contract specifications are valid
7. **Port core data pipeline** - Adapt trade/orderbook fetching logic from legacy

## Phase 3: Data Processing & Export

8. **Implement trade data fetching** - Per-contract trade aggregation with filtering
9. **Add order book integration** - Bid/ask data alignment with trades using same contract keys
10. **Create data merger** - Combine trades, orders, and mid prices using consistent dictionary keys
11. **Create parquet export** - Individual files per contract with consistent naming
12. **Add data validation** - Compare outputs with legacy system results

## Key Features

- **Contract-specific date ranges** - Support both explicit dates and lookback-based periods per contract
- **Unified contract configuration** - Single contract list for both trades and orders to ensure data alignment
- **Parallel processing** - Maintain data alignment across trade and order book data
- **Clean interface** - Preserve legacy functionality while providing modern, configurable API
- **Data merge patterns** - Consistent dictionary keys enabling proper trade/order/mid price combination

## Input Design

### Contract Configuration Options

**Option 1: Explicit date ranges per contract**
```python
contracts = [
    {
        'market': 'de', 'tenor': 'm', 'contract': '07_25',
        'start_date': '2025-04-01', 'end_date': '2025-06-30'
    },
    {
        'market': 'fr', 'tenor': 'q', 'contract': '2_25', 
        'start_date': '2024-10-01', 'end_date': '2024-12-31'
    }
]
```

**Option 2: Lookback from delivery date**
```python
contracts = [
    {
        'market': 'de', 'tenor': 'm', 'contract': '07_25',
        'lookback_days': 90  # 90 days before July 1, 2025
    },
    {
        'market': 'fr', 'tenor': 'q', 'contract': '2_25',
        'lookback_days': 120  # 120 days before Q2 2025 start
    }
]
```

## Foundation Code

Based on `source_repos/ATS_2/backtest/data_fetch.py` patterns:
- TPData database connections (Oracle/PostgreSQL)
- Trade data fetching with broker ID and trading hours filtering
- Order book data integration with timestamp alignment
- Volume-weighted price aggregation
- Parquet export with consistent naming: `{contract}_tr_ba_data.parquet`

## Production Output Design ✅

**Validated through UAT testing - Production ready implementation**

### Performance Benchmarks
- **Individual contract fetch**: 6.56-15.29 seconds per contract
- **Batch processing efficiency**: 35.88 seconds for 3 contracts (parallel processing)
- **Export performance**: Sub-second parquet file generation
- **Database connectivity**: Dual Oracle/PostgreSQL with automatic connection management

### Data Structure Specifications

**Combined Output Format**: Single parquet file per contract with integrated data
```
Columns (9 total):
├── Trade Data (6 columns)
│   ├── price: float64 - Trade execution price
│   ├── volume: int64 - Trade volume
│   ├── action: float64 - Buy/sell direction (-1.0/1.0)
│   ├── broker_id: float64 - EEX broker identifier (1441)
│   ├── count: int64 - Trade sequence counter
│   └── tradeid: object - Unique trade identifier
├── Order Data (2 columns)
│   ├── b_price: float64 - Best bid price
│   └── a_price: float64 - Best ask price
└── Mid Prices (1 derived column)
    └── mid_price: float64 - Calculated (bid + ask) / 2
```

### Production Data Volumes (Validated)
- **Trade records**: 17,810 total across 3 test contracts
  - German Monthly contracts: 6,061-11,309 trades per contract
  - French Quarterly contracts: 440 trades per contract
- **Order records**: 76,064 total across 3 test contracts
  - High-frequency orderbook updates (6,855-42,558 per contract)
- **File sizes**: 106KB-815KB per contract (efficient compression)

### Export Specifications

**Primary Format**: Parquet with pyarrow engine
```python
# File naming convention
file_pattern = "{market}{tenor}{contract}_tr_ba_data.parquet"

# Examples:
# dem07_25_tr_ba_data.parquet  (German Monthly July 2025)
# frq2_25_tr_ba_data.parquet   (French Quarterly Q2 2025)
# dem08_25_tr_ba_data.parquet  (German Monthly August 2025)
```

**Data Integration Pattern**:
- **Unified timestamps**: All data indexed by datetime
- **Synchronized records**: Trades aligned with nearest orderbook snapshots
- **Mid price calculation**: Real-time (bid + ask) / 2 computation
- **Cross-platform compatibility**: Automatic path resolution for WSL/Windows

### API Integration for Other Agents

**DataFetcher Usage**:
```python
from src.core.data_fetcher import DataFetcher

# Initialize with trading parameters
fetcher = DataFetcher(
    trading_hours=(9, 17),
    allowed_broker_ids=[1441]
)

# Fetch single contract
result = fetcher.fetch_contract_data({
    'market': 'de', 'tenor': 'm', 'contract': '07_25',
    'lookback_days': 5
})

# Batch processing multiple contracts
results = fetcher.fetch_multiple_contracts([
    {'market': 'de', 'tenor': 'm', 'contract': '07_25', 'lookback_days': 5},
    {'market': 'fr', 'tenor': 'q', 'contract': '2_25', 
     'start_date': '2025-01-20', 'end_date': '2025-01-22'}
])

# Export to parquet files
fetcher.export_to_parquet(results, output_directory)
```

**Expected Output Structure**:
```python
# Per-contract results
{
    'dem07_25': {
        'trades': DataFrame(11309 rows × 6 columns),
        'orders': DataFrame(42558 rows × 2 columns), 
        'mid_prices': Series(42558 values)
    },
    'frq2_25': {
        'trades': DataFrame(440 rows × 6 columns),
        'orders': DataFrame(6855 rows × 2 columns),
        'mid_prices': Series(6855 values)
    }
}
```

**Integration Notes for Other Agents**:
- **File reading**: Use `pd.read_parquet()` to load exported files
- **Data alignment**: All timestamps are synchronized across trades/orders
- **Filtering**: Data pre-filtered for EEX broker (1441) and trading hours (9-17)
- **Quality assurance**: All contracts validated with real market data