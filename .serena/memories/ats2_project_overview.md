# ATS_2 Project Overview

## Project Purpose
ATS_2 (Algorithmic Trading System 2) is an energy trading platform focused on German power markets, implementing various trading strategies including:
- Lead-lag strategies between different energy contracts
- Bid-ask convergence strategies  
- Market making strategies
- XGBoost and regression-based prediction models

## Tech Stack
- **Python 3.x** - Primary language
- **pandas** - Data manipulation and analysis
- **numpy** - Numerical computations
- **XGBoost** - Machine learning models
- **parquet/fastparquet** - Data storage format
- **Jupyter notebooks** - Analysis and experimentation
- **PostgreSQL/TimescaleDB** - Database backend (via MCP server)

## Key Components

### Trading Strategies
- **LeadLag strategies** - Multiple variants using different ML approaches
- **BA_convergence** - Bid-ask spread convergence trading
- **Market_making** - Market making algorithms
- **SpotTraining** - Spot market focused strategies

### Infrastructure
- **Backtesting framework** - Comprehensive backtesting with parallel processing
- **Calibration system** - Parameter optimization for strategies
- **Data loaders** - Market data ingestion and processing
- **Risk management** - Position and risk calculation tools

### Energy Market Focus
- **German Power Market** - Primary focus on DEM, DEQ, DEW, FRM contracts
- **Intraday trading** - High-frequency trading during market hours (8 AM - 6 PM)
- **Cross-border trading** - European energy market interactions

## Directory Structure
```
ATS_2/
├── backtest/ - Core backtesting framework
├── EnergyTrading/Python/ - Main trading system
│   ├── Strategies/ - Individual trading strategies
│   ├── Database/ - Data access layer
│   ├── Loaders/ - Data loading utilities
│   └── Common/ - Shared utilities
├── analysis/ - Performance analysis tools
├── combinations_generation/ - Strategy parameter generation
└── docs/ - Documentation
```