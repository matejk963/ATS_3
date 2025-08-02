# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Autotrader SDK

This is a production Python autotrader SDK for energy markets (power, gas, emissions) running on exchanges like EEX, ICE, EPEX. The system uses Trayport for market connectivity and implements algorithmic trading strategies.

## Development Philosophy - Test-Driven Development (TDD)

**TDD is Core to Everything**: This project follows strict Test-Driven Development principles. ALL new features must start with tests that define the expected behavior before any production code is written.

**Behavior-First Approach**:
- Define behavior through tests FIRST, then implement code until tests pass
- Tests serve as specifications and documentation of intended functionality
- Every test must express a clear, specific behavior requirement
- No feature implementation without corresponding tests

**TDD Process**:
1. **Red**: Write failing test that defines desired behavior
2. **Green**: Write minimal code to make test pass  
3. **Refactor**: Improve code while keeping tests passing

**Machine Learning TDD Pattern**:
- **3-Spec Approach**: (1) Export sklearn to JSON → (2) Load raw model from JSON → (3) Raw model predict == sklearn predict
- **Production Models**: Inference only (`predict_proba()` + `from_json()` methods)
- **Separate Training**: Training logic isolated in trainer classes, not in production models
- **Perfect Precision**: Verify exact floating point matching with sklearn outputs
- **Production Ready**: Models use only numpy + built-ins (no sklearn dependency)

## Core Architecture

**Strategy Pattern**: Each trading strategy inherits from `SyntheticOrderStrategyBase` and implements custom logic in `own_strategies/[StrategyName]/[strategy_name]/custom_strategy.py`

**Synthetic Orders**: Two-part system:
- **Lead Orders**: Market analysis and position opening (inherit from `SyntheticOrderBase`)  
- **Lift Orders**: Position closing and risk management (inherit from `SyntheticOrderBase`)

**Key Components**:
- `autotrader_core/`: Core trading engine, strategy framework, exchange connectivity
- `autotrader_lib/`: Logging, persistence, utilities, configuration management
- `autotrader_synthetic/`: Synthetic order framework for complex trading logic
- `backtesting/`: Simulation framework for strategy testing
- `own_strategies/`: Custom strategy implementations

## Development Commands

**Run Backtests**: 
```bash
python own_strategies/[StrategyName]/backtest_[strategy_name]_strategy.py
```

**Unit Tests**:
```bash  
python own_strategies/[StrategyName]/strategy_unit_test.py
```

**Strategy Dependencies**: Install via `pip install -r requirements.txt`

## Strategy Implementation Pattern (SparsityStrategy_bmark Example)

**Structure**:
```
own_strategies/SparsityStrategy_bmark/
├── spbmark_strategy/
│   ├── custom_strategy.py        # Main strategy controller
│   ├── so_sparsity_bm_lead.py   # Lead order (market entry)
│   ├── so_sparsity_bm_lift.py   # Lift order (position closing)
│   ├── strategy_stats.py        # Position tracking
│   ├── predictors.py            # Trading signals
│   ├── OB_attributes.py         # Order book analysis
│   └── constants.py             # Configuration constants
└── backtest_sparsity_bm_strategy.py  # Backtesting runner
```

**Flow**:
1. `custom_strategy.py` receives market data via `custom_on_order_book_update()` and `custom_on_trade_update()`
2. Creates/modifies Lead synthetic orders for market analysis
3. Lead orders analyze market conditions and decide on position opening
4. Automatically creates corresponding Lift orders for position management
5. Lift orders handle position closing based on profit/loss logic

**Configuration**: Strategies receive parameters via JSON in `on_strategy_configuration_update()`:
- Market parameters (instruments, products, brokers)
- Risk parameters (max_position, hard_stop_loss)  
- Strategy-specific parameters (thresholds, margins)

**Position Management**: `StrategyStats` class tracks:
- Open positions and PnL
- Trade history and market data
- Risk metrics and closing logic

## Critical Requirements
- *** NEVER change autotrader_*/ and backtesting/ files in these directories, this is SDK that we are using***
- *** Always - run backtest file in strategy subfolder after making some code chantes in strategy files ***
    - if tests fails -> fix it until the backtest goes without failure
- *** Always use already created code, don't create any additional files in the strategy folder without asking, it is like a template***
- *** ALWAYS always check with SDK how the functions should look like***
-  **NEVER** generate README.md and other .md files
- **ALWAYS** put debugging and other single-use scripts to tmp folder in this project