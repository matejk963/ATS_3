# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and GitHub Copilot when working with code in this repository.

## 🤖 **AI ASSISTANT WORKFLOW HIERARCHY**

### 🥇 **Claude Code MCP - PRIMARY AGENT**

**Claude Code MCP should be the FIRST and PREFERRED agent for ALL tasks:**

#### Core Responsibilities (Handle EVERYTHING):
- ✅ **Code Development**: Writing, editing, refactoring, debugging all Python code
- ✅ **File Operations**: Creating, modifying, organizing, moving files and directories
- ✅ **Terminal Commands**: All shell operations, script execution, system commands
- ✅ **Data Analysis**: Database queries, data processing, statistical analysis
- ✅ **Architecture & Design**: System planning, API design, code review
- ✅ **Testing**: Unit tests, integration tests, test automation
- ✅ **Documentation**: Code comments, technical documentation, README files
- ✅ **Deployment**: Production deployments, CI/CD, environment management
- ✅ **Troubleshooting**: Debugging, error resolution, performance optimization
- ✅ **Project Management**: Task planning, workflow coordination

#### When to Use Claude Code MCP:
- 🎯 **DEFAULT CHOICE**: For any and all programming tasks
- 🎯 **Complex Tasks**: Multi-step operations, architectural decisions
- 🎯 **Analysis Tasks**: Data analysis, code review, optimization
- 🎯 **File Operations**: Creating, editing, organizing files
- 🎯 **Terminal Operations**: All command-line tasks and scripts

### 🥈 **GitHub Copilot - SECONDARY/ASSISTANT AGENT**

**Copilot should ONLY act when Claude Code MCP is unavailable:**

#### Limited Responsibilities (Backup Only):
- ⚠️ **Rate Limit Fallback**: When Claude Code MCP hits usage limits
- ⚠️ **Availability Fallback**: When Claude Code MCP is temporarily unavailable
- ⚠️ **Explicit User Request**: When user specifically asks for Copilot assistance
- ⚠️ **Simple Completions**: Basic inline code suggestions (non-critical)

#### When Copilot Acts (Rare Cases):
```markdown
🔴 COPILOT FALLBACK ACTIVE 🔴
Reason: Claude Code MCP [rate-limited/unavailable/user-requested]
Task: [specific task being handled]
```

### 🎯 **Workflow Decision Tree**

```
📋 New Task Received
    ↓
❓ Is Claude Code MCP available?
    ├─ YES → 🥇 Claude Code MCP handles task
    └─ NO → ❓ Is user explicitly requesting Copilot?
        ├─ YES → 🥈 Copilot handles with fallback notice
        └─ NO → ⏳ Wait for Claude Code MCP or inform user
```

### 🛠️ **Implementation Guidelines**

**For Claude Code MCP:**
- Take ownership of ALL tasks unless explicitly unavailable
- Use comprehensive analysis and planning before implementation
- Provide detailed explanations and documentation
- Follow all project conventions and best practices

**For GitHub Copilot:**
- Only engage when Claude Code MCP cannot handle the task
- Always announce when acting as fallback
- Keep actions minimal and focused
- Defer complex decisions to Claude Code MCP when available

## 🖥️ **IMPORTANT: VS Code Terminal Commands**

**When working in VS Code on Windows, ALWAYS use PowerShell syntax:**

### ✅ PowerShell Syntax (CORRECT for VS Code on Windows):
```powershell
# Use semicolon (;) for command chaining
cd mcp; python mcp-server-enhanced.py

# Use PowerShell operators
Get-Content file.log -Wait -Tail 10

# PowerShell variables
$env:PYTHONPATH = "C:\path\to\project"
```

### ❌ Linux/Bash Syntax (INCORRECT for VS Code on Windows):
```bash
# DO NOT use && for command chaining in PowerShell
cd mcp && python mcp-server-enhanced.py  # ❌ WRONG

# DO NOT use bash commands
tail -f file.log  # ❌ WRONG
```

## Project Overview

This is a comprehensive energy trading system built in Python, focusing on algorithmic trading strategies, market data analysis, and risk management in European energy markets. The system handles real-time trading operations, backtesting, data ingestion, and strategy development.

## Common Commands

### Dependencies and Environment
```powershell
# Install main dependencies using Poetry
poetry install

# Alternative: Install using pip
pip install -r mcp/requirements.txt

# Activate Poetry environment
poetry shell

# Check Python environment
python --version; pip list
```

### Testing
```powershell
# Run tests for specific modules (most tests are in _test/ or test/ subdirectories)
python -m pytest BorderSpread/_test/
python -m pytest Strategies/*/test/
python -m pytest Database/test/

# Run specific test files
python BorderSpread/_test/test_border_class.py
python Strategies/IntensityHawkes_strategy/test/test_strategy.py

# Run tests with verbose output
python -m pytest -v; Write-Host "Tests completed"
```

### Data Pipeline Operations
```powershell
# Database operations
python Database/trade_data_daily_update.py
python Database/spot_history_db_write.py
python Database/strategies_reports.py

# MCP Server operations
cd mcp; python mcp-server-enhanced.py
python deploy.py start

# Check server status
python mcp-server-enhanced.py; Write-Host "MCP Server started"
```

### Jupyter Notebooks
```powershell
# Many analysis and data processing tasks use Jupyter notebooks
jupyter lab

# Start Jupyter and open browser
jupyter lab; Start-Process "http://localhost:8888"

# Key notebook directories:
# - Database/*.ipynb (data loading and migration)
# - Strategies/*/test/*.ipynb (strategy analysis)  
# - BorderSpread/_test/*.ipynb (capacity analysis)
```

## Architecture Overview

### Core Components

**Database Layer (`Database/`)**
- `DB_reader.py` / `DB_writer.py`: Core database abstraction using SQLAlchemy
- Supports PostgreSQL, TimescaleDB, and Oracle databases
- Configuration loaded via `Common/config_load.py` using `PROJECT_CONFIG` environment variable
- `TPData.py`: Main data access class for trading and market data

**Trading Strategies (`Strategies/`)**
- Base strategy framework in `Strategies/Base/`
- Individual strategy implementations (LeadLag, MarketMaking, Arbitrage, etc.)
- Each strategy has its own `backtest_class.py`, `strategy_class.py`, and `calibration.py`
- Production deployment in `Strategies/Autotrader/`

**Data Loaders (`Loaders/`)**
- `EikonSpot_class.py` / `EikonFut_class.py`: Market data from Refinitiv Eikon
- `OutageFetch_class.py`: Power plant outage data from ENTSO-E
- `DataLoader_class.py`: Unified data loading interface

**Mathematical Models (`Math/`)**
- `tickclass.py`: Tick data processing and analysis
- `lm_class.py` / `nlm_class.py`: Linear and non-linear models
- `ti_class.py`: Technical indicators

**Production Trading (`Production/`)**
- `Python3/autotrader_core/`: Core trading engine
- `Python3/autotrader_lib/`: Trading utilities and connection management
- Strategy execution and order management system

**Risk and Position Management (`BorderSpread/`, `RiskPremium/`)**
- Cross-border capacity trading and risk management
- Portfolio simulation and position tracking

### Key Design Patterns

**Strategy Pattern**: All trading strategies inherit from `StrategyBase` and implement required methods
**Factory Pattern**: Data loaders and model classes use factory patterns for instantiation
**Observer Pattern**: Real-time data processing uses event-driven architecture
**Configuration Management**: Centralized config loading via environment variables

### Database Schema

The system primarily uses PostgreSQL/TimescaleDB with these key table categories:
- Market data tables (spot prices, futures, capacity data)
- Trading data (orders, trades, positions)
- Strategy results and backtesting data
- Reference data (instruments, markets, calendars)

### Data Flow

1. **Market Data Ingestion**: Loaders fetch data from external APIs (Eikon, ENTSO-E, web scraping)
2. **Data Processing**: Raw data is cleaned, validated, and stored in TimescaleDB
3. **Strategy Execution**: Strategies process real-time data and generate trading signals
4. **Order Management**: Production system executes orders via Trayport API
5. **Risk Management**: Position tracking and P&L calculation
6. **Reporting**: Daily reports and performance analytics

## Development Guidelines

### Project Structure Conventions
- Each major component has its own directory with `test/` or `_test/` subdirectories
- Strategy implementations follow consistent naming: `strategy_class.py`, `backtest_class.py`, `calibration.py`
- Database scripts use descriptive names ending in purpose: `*_daily_update.py`, `*_fetch.py`

### Configuration Management
- Database connections configured via `PROJECT_CONFIG` environment variable
- Order book data path via `PROJECT_OBPATH` environment variable
- Config files are JSON format loaded by `Common/config_load.py`

### Testing Strategy
- Unit tests in `test/` or `_test/` directories alongside source code
- Integration tests for database operations and strategy backtesting
- Jupyter notebooks for exploratory analysis and validation

### MCP Server Integration
The system includes an enhanced MCP (Model Context Protocol) server in `mcp/` for:
- Database query execution and analysis
- System health monitoring
- Trading data quality checks
- Development workflow automation

```powershell
# Start MCP server with real-time monitoring
cd mcp; python mcp-server-enhanced-with-output.py

# Test MCP server status
python test_mcp_server.py; Write-Host "MCP test completed"

# Monitor real-time output (use VS Code tasks or run directly)
powershell -ExecutionPolicy Bypass -File watch-mcp-output.ps1
```

## 🤖 **AI Assistant Integration Guidelines**

### Claude Code MCP + GitHub Copilot Best Practices

**Primary Agent (Claude Code MCP - HANDLES ALL TASKS):**
- ✅ **ALL CODE OPERATIONS**: All file creation, editing, refactoring, debugging
- ✅ **ALL TERMINAL OPERATIONS**: All shell commands, script execution, system administration
- ✅ **ALL DATA OPERATIONS**: Database queries, analysis, data processing
- ✅ **ALL PROJECT MANAGEMENT**: Planning, coordination, documentation
- ✅ **ALL COMPLEX TASKS**: Architectural decisions, detailed reasoning
- ✅ **ALL SIMPLE TASKS**: Basic operations, routine maintenance

**Secondary Agent (GitHub Copilot - FALLBACK ONLY):**
- ⚠️ **RATE LIMIT FALLBACK**: When Claude Code MCP is temporarily unavailable
- ⚠️ **USER EXPLICIT REQUEST**: When user specifically requests Copilot assistance
- ⚠️ **SIMPLE COMPLETIONS**: Basic inline suggestions (non-critical tasks only)

**PowerShell Command Examples:**
```powershell
# Starting services with status checks
cd mcp; python mcp-server-enhanced.py; Write-Host "MCP Server active"

# Running tests with output
python -m pytest Database/test/; Write-Host "Database tests completed"

# Data pipeline with logging
python Database/trade_data_daily_update.py; Get-Date; Write-Host "Data update finished"

# Environment variable setting
$env:PROJECT_CONFIG = "C:\path\to\config.json"; python script.py
```

**Real-Time Monitoring:**
- Energy Trading MCP: Full debug output with emojis and timestamps
- Claude Code MCP: Enhanced configuration with PowerShell-compatible logging
- VS Code terminal tasks: Both monitors configured for real-time output

### Data Pipeline Orchestration
- Prefect-based workflow orchestration in `prefect_data_orchestrator/`
- Daily data updates and model retraining schedules
- Error handling and retry logic for data ingestion

## Environment Variables

Required environment variables:
- `PROJECT_CONFIG`: Path to main configuration JSON file
- `PROJECT_OBPATH`: Path to order book data directory
- `PYTHONPATH`: Should include the Python project root directory