# ATS_2 Component Inventory and Mapping

## Overview
This document provides a comprehensive inventory of all components in the ATS_2 system, categorized by functionality and importance for ATS_3 refactoring.

## Core Production Components (Essential for ATS_3)

### 1. Main Workflow System
| Component | Location | Purpose | Criticality |
|-----------|----------|---------|-------------|
| `strategy_workflow.py` | Root | Complete trading pipeline | **Critical** |
| `bias_classifier.py` | `core/` | MACD-based bias classification | **Critical** |
| `target_calculator.py` | `core/` | Future trade targets | **Critical** |

### 2. Backtesting Framework
| Component | Location | Purpose | Criticality |
|-----------|----------|---------|-------------|
| `backtest_class.py` | `backtest/` | Core backtesting engine | **High** |
| `strategy_class.py` | `backtest/` | Strategy implementation | **High** |
| `support_functions.py` | `backtest/` | Utility functions | **Medium** |
| `calibration.py` | `backtest/` | Parameter optimization | **High** |

### 3. Parallel Processing System
| Component | Location | Purpose | Criticality |
|-----------|----------|---------|-------------|
| `backtest_multi_parallel_enhanced.py` | Root | Enhanced parallel backtesting | **High** |
| `strategy_parameter_sweep_cpu_parallel_fixed.py` | `combinations_generation/` | CPU-optimized sweeps | **High** |
| `combination_registry.py` | `combinations_generation/` | Parameter combination management | **Medium** |
| `complete_memory_solution.py` | `combinations_generation/` | Memory-efficient processing | **Medium** |

### 4. Analysis Framework
| Component | Location | Purpose | Criticality |
|-----------|----------|---------|-------------|
| `martinovo_zatvaranie_pnl_analysis.py` | `analysis/` | PnL investigation | **Medium** |
| `check_bid_ask_data_quality.py` | `analysis/` | Market data quality | **Medium** |
| `analyze_backtest_results.py` | `analysis/` | Performance analysis | **High** |
| `visualize_top20_trades_prices_with_computed_pnl.py` | `analysis/` | Visualization | **Low** |

## EnergyTrading Repository Components (Available Tools)

### 1. Database Infrastructure
| Component | Location | Purpose | Utility |
|-----------|----------|---------|---------|
| `DB_reader.py` | `EnergyTrading/Python/Database/` | Database connection | **Critical** |
| `DB_writer.py` | `EnergyTrading/Python/Database/` | Database writing | **High** |
| `utils.py` | `EnergyTrading/Python/Database/Timescale/` | TimescaleDB utilities | **High** |
| `TPData.py` | `EnergyTrading/Python/Database/` | Trading platform data | **Medium** |

### 2. Mathematical Libraries
| Component | Location | Purpose | Utility |
|-----------|----------|---------|---------|
| `technical_indicators.py` | `EnergyTrading/Python/Utilities/` | Technical analysis | **High** |
| `accumfeatures.py` | `EnergyTrading/Python/Math/` | Feature accumulation | **Medium** |
| `ti_class.py` | `EnergyTrading/Python/Math/` | Technical indicators class | **High** |
| `lm_class.py` | `EnergyTrading/Python/Math/` | Linear models | **Medium** |

### 3. Strategy Infrastructure
| Component | Location | Purpose | Utility |
|-----------|----------|---------|---------|
| `backtest_class.py` | `EnergyTrading/Python/Utilities/` | Base backtest framework | **Critical** |
| `strategy_class.py` | `EnergyTrading/Python/Utilities/` | Base strategy framework | **Critical** |
| `model_class.py` | `EnergyTrading/Python/Utilities/` | Model base class | **High** |
| `cost_functions.py` | `EnergyTrading/Python/Utilities/` | Cost calculation | **Medium** |

### 4. Data Processing
| Component | Location | Purpose | Utility |
|-----------|----------|---------|---------|
| `DataLoader_class.py` | `EnergyTrading/Python/Loaders/` | Data loading framework | **High** |
| `data_functions.py` | `EnergyTrading/Python/Utilities/` | Data processing utilities | **Medium** |
| `dfutils.py` | `EnergyTrading/Python/Utilities/` | DataFrame utilities | **Medium** |
| `date_functions.py` | `EnergyTrading/Python/Utilities/` | Date/time utilities | **Medium** |

### 5. Advanced Strategies
| Component | Location | Purpose | Utility |
|-----------|----------|---------|---------|
| `LeadLagXGB/` | `EnergyTrading/Python/Strategies/` | XGBoost lead-lag models | **Medium** |
| `Market_making/` | `EnergyTrading/Python/Strategies/` | Market making strategies | **Low** |
| `Hawkes_class.py` | `EnergyTrading/Python/Strategies/` | Hawkes process models | **Low** |
| `Intensity_class.py` | `EnergyTrading/Python/Strategies/` | Intensity-based strategies | **Low** |

## Archived Components (Available but Not Active)

### 1. Complex Implementation (Pre-cleanup)
| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| `src/` directory | `archived_project/` | Original complex modules | **Archived** |
| UAT notebooks | `archived_project/` | User acceptance tests | **Archived** |
| Development logs | `archived_project/` | Historical documentation | **Archived** |
| Alternative workflows | `archived_project/` | Earlier implementations | **Archived** |

### 2. Legacy GPU Implementation
| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| GPU optimization files | `combinations_generation_legacy/` | GPU-accelerated processing | **Legacy** |
| CUDA implementations | `combinations_generation_legacy/docs/` | GPU-specific code | **Legacy** |
| RTX4080 stress tests | `combinations_generation_legacy/` | Hardware-specific tests | **Legacy** |

## Configuration and Setup

### 1. Environment Configuration
| Component | Location | Purpose | Importance |
|-----------|----------|---------|------------|
| `environment.yml` | Root | Conda dependencies | **Critical** |
| `tasks.json` | `config/` | Project task definitions | **Medium** |
| `.vscode/settings.json` | Not present | IDE configuration | **Low** |
| `pyproject.toml` | EnergyTrading | Poetry configuration | **Low** |

### 2. Documentation
| Component | Location | Purpose | Importance |
|-----------|----------|---------|------------|
| `README.md` | Root | Project overview | **High** |
| `project_diary.md` | Root | Development history | **High** |
| `CLAUDE.md` | Root | Development instructions | **High** |
| `simple_setup.md` | `docs/` | Setup instructions | **Medium** |

## Testing Infrastructure

### 1. Unit Tests
| Component | Location | Purpose | Coverage |
|-----------|----------|---------|---------|
| `test_strategy_development.py` | `tests/` | Strategy testing | **Medium** |
| `test_performance_ratios.py` | `tests/` | Performance metrics | **Medium** |
| `test_parallel_backtest.py` | `tests/` | Parallel processing | **Medium** |
| `test_file_saving.py` | `tests/` | File operations | **Low** |

### 2. Integration Tests
| Component | Location | Purpose | Coverage |
|-----------|----------|---------|---------|
| Notebook tests | `notebooks/` | End-to-end validation | **High** |
| Backtest validation | `backtest/test/` | Strategy validation | **High** |
| Data quality tests | `analysis/` | Data validation | **Medium** |

## Utility and Support Components

### 1. File Management
| Component | Location | Purpose | Utility |
|-----------|----------|---------|---------|
| `universal_path_handler.py` | Root | Cross-platform paths | **Medium** |
| `file_utils.py` | `EnergyTrading/Python/Utilities/` | File operations | **Medium** |
| `Storage.py` | `EnergyTrading/Python/Utilities/` | Data storage | **Low** |

### 2. Error Handling and Monitoring
| Component | Location | Purpose | Utility |
|-----------|----------|---------|---------|
| `CaptureExceptions.py` | `EnergyTrading/Python/Utilities/` | Exception handling | **Medium** |
| `DataValidator.py` | `EnergyTrading/Python/Utilities/` | Data validation | **Medium** |
| MCP server | `mcp/` | Model context protocol | **Low** |

## Refactoring Priority Matrix

### Priority 1 (Must Have for ATS_3)
- Main workflow system
- Bias classifier and target calculator
- Core backtesting framework
- Database infrastructure
- Technical indicators

### Priority 2 (High Value)
- Parallel processing system
- Analysis framework
- Mathematical libraries
- Strategy infrastructure
- Environment configuration

### Priority 3 (Nice to Have)
- Advanced strategies
- Visualization tools
- Legacy GPU implementations
- Utility components
- MCP integration

### Priority 4 (Archive/Reference)
- Complex archived implementation
- Historical documentation
- Legacy test files
- Obsolete configurations

## Component Dependencies

### Critical Path Dependencies
```
Database (DB_reader) → Data Processing → Feature Engineering → Bias Classification → Position Signals
                                                                                           ↓
Performance Analysis ← Results Processing ← Optimization ← Backtesting Engine ← Strategy Logic
```

### Supporting Dependencies
```
Technical Indicators → Feature Engineering
Math Libraries → Strategy Logic
Utilities → All Components
Configuration → Environment Setup
```

## Recommendations for ATS_3

### 1. Core Architecture
- **Keep**: Simplified workflow approach
- **Enhance**: Modular design with clear interfaces
- **Add**: Comprehensive testing framework

### 2. Component Selection
- **Migrate**: All Priority 1 components
- **Refactor**: Priority 2 components with improved design
- **Evaluate**: Priority 3 components based on use cases
- **Archive**: Priority 4 components for reference

### 3. Development Strategy
- **Phase 1**: Core system migration and testing
- **Phase 2**: Enhanced backtesting and optimization
- **Phase 3**: Advanced features and real-time capabilities
- **Phase 4**: Integration with EnergyTrading ecosystem

This inventory provides the foundation for systematic refactoring and ensures no critical components are overlooked in the ATS_3 development process.