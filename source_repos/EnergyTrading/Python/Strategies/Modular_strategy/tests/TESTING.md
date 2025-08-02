# Closing Logic Testing Documentation

## Overview
This document provides a comprehensive guide to the test suite for the modular closing logic system in the EnergyTrading platform. The test suite ensures the correctness and robustness of all closing logic implementations used in trading strategies.

## Test Categories

### 1. Core Functionality Tests
These tests validate the basic functionality of each closing logic implementation:
- MtmAggClosingLogic
- IdleClosingLogic
- OriginalClosingLogic

### 2. Edge Case Tests
These tests verify that the closing logic implementations handle exceptional and boundary conditions correctly:
- NaN price handling
- Zero or negative burnout periods
- Price rounding behavior
- Market volume constraints

### 3. Integration Tests
These tests validate how different components of the system work together across multiple trading scenarios.

## Test Coverage Matrix

| Category | Test Case | StdLogic | IdleLogic | OrigLogic | Description |
|----------|-----------|----------|-----------|-----------|-------------|
| **Long Positions** | Stop Loss | ✓ | ✓ | ✓ | Tests stop loss triggering for long positions |
| | Take Profit | ✓ | ✓ | ✓ | Tests take profit behavior for long positions |
| | Time Expiry | ✓ | ✓ | ✓ | Tests time-based closing for long positions |
| | Trailing Price | ✓ | ✓ | ✓ | Tests trailing price updates for long positions |
| | Burnout Period | ✓ | ✓ | ✓ | Tests burnout period behavior for long positions |
| | MAKEBEST vs AGGLOSS | ✓ | N/A | ✓ | Tests aggressive vs passive closing decisions |
| | Passive Pricing | N/A | ✓ | N/A | Tests passive price placement in wide markets |
| **Short Positions** | Stop Loss | ✓ | ✓ | ✓ | Tests stop loss triggering for short positions |
| | Take Profit | ✓ | ✓ | ✓ | Tests take profit behavior for short positions |
| | Time Expiry | ✓ | ✓ | ✓ | Tests time-based closing for short positions |
| | Trailing Price | ✓ | ✓ | ✓ | Tests trailing price updates for short positions |
| | Burnout Period | ✓ | N/A | ✓ | Tests burnout period behavior for short positions |
| | MAKEBEST vs AGGLOSS | ✓ | N/A | ✓ | Tests aggressive vs passive closing decisions |
| | Passive Pricing | N/A | ✓ | N/A | Tests passive price placement in wide markets |
| **Edge Cases** | NaN Prices | ✓ | ✓ | ✓ | Tests handling of NaN prices in market data |
| | Zero Burnout | ✓ | ✓ | ✓ | Tests behavior with zero burnout period |
| | Negative MTM | ✓ | ✓ | ✓ | Tests handling of negative MTM calculations |
| | Price Rounding | ✓ | ✓ | ✓ | Tests price rounding behavior |
| | Non-Integer Volume | ✓ | ✓ | ✓ | Tests handling of fractional volumes |
| | Trade Execution Constraints | ✓ | ✓ | ✓ | Tests behavior with market volume constraints |
| **Advanced** | Multiple Day Handling | ✓ | ✓ | ✓ | Tests position handling across trading days |
| | Hard Stop Loss | ✓ | ✓ | ✓ | Tests daily hard stop loss behavior |
| | Position Update Sequence | ✓ | ✓ | ✓ | Tests sequence of position updates/closings |

## Running Tests

### Basic Test Execution
To run all tests with default settings:

```bash
cd /Users/martin/Documents/GitHub/EnergyTrading/Python
python -m Strategies.Modular_strategy.tests.run_closing_logic_tests
```

### Running Specific Test Cases
To run only a specific test case:

```bash
cd /Users/martin/Documents/GitHub/EnergyTrading/Python
python -m unittest Strategies.Modular_strategy.tests.test_closing_logics_extended.TestExtendedClosingLogics.test_trailing_price_update_long
```

### Running Tests with Coverage Analysis
To run tests with coverage reporting (requires `coverage` package):

```bash
cd /Users/martin/Documents/GitHub/EnergyTrading/Python
coverage run -m Strategies.Modular_strategy.tests.run_closing_logic_tests
coverage report -m
```

## Test Strategy Development Guidelines

When developing new tests or extending existing ones:

1. **Isolation**: Each test should test one specific behavior or functionality
2. **Descriptiveness**: Test names should clearly describe what they're testing
3. **Completeness**: Cover all edge cases and error conditions
4. **Documentation**: Add detailed comments explaining the test scenarios
5. **Maintenance**: Keep tests in sync with implementation changes

## Test Result Interpretation

The test runner provides detailed reporting on test execution:

- **Test Count**: Total number of tests executed
- **Pass/Fail Summary**: Number of tests passed, failed, or with errors
- **Execution Time**: Total time taken to run the test suite
- **Failure Details**: Stack traces and details for any failing tests

## Adding New Tests

To add new test cases:

1. Add the test method to the appropriate test class
2. Ensure the method name starts with `test_`
3. Include assertions to verify expected behavior
4. Update this documentation to include the new test case

## Troubleshooting Common Test Issues

### Position Not Closing When Expected
- Check if burnout period is preventing closing
- Verify market prices are crossing the specified execution price
- Check bid/ask volumes are sufficient for execution

### Wrong Closing Reason
- Review the closing logic decision tree
- Check parameter settings impacting behavior (e.g., makeagg_ratio)
- Verify that test data is setting up the intended market condition

### Test Times Out
- Check if there are infinite loops in the implementation
- Ensure that position updates are working correctly
- Verify that the test environment is properly initialized
