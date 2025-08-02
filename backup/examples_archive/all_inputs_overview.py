"""
Complete overview of ALL inputs used in Phase 1.1.2 Parameter Combination Logic.

This shows every single parameter that contributes to the 691,200+ combinations.
"""

from src.gpu_parallel_processing.parameter_combinations import (
    DATE_RANGE,
    CONTRACTS,
    PREDICTOR_GRANULARITIES,
    MACD_CONFIGS,
    ATR_LOOKBACKS,
    STOP_LOSS_RANGES,
    SL_TP_RATIOS,
    BIAS_THRESHOLD_RANGES,
    NEUTRAL_STRATEGY_RANGES,
    BIAS_ADJUSTMENT_RANGES,
    BIAS_THRESHOLD_DEFAULTS,
    POSITION_THRESHOLD_DEFAULTS
)

def show_all_inputs():
    """Display every input parameter with explanations."""
    
    print("=" * 80)
    print("ALL INPUT PARAMETERS FOR PARAMETER COMBINATION GENERATION")
    print("=" * 80)
    
    # 1. Time Period
    print("\n1. TIME PERIOD CONFIGURATION")
    print("-" * 40)
    print(f"Date Range: {DATE_RANGE}")
    print("→ Purpose: Defines the backtesting period for all strategies")
    
    # 2. Market Contracts
    print("\n2. MARKET CONTRACTS")
    print("-" * 40)
    print(f"Contracts: {CONTRACTS}")
    print(f"Count: {len(CONTRACTS)}")
    print("→ Purpose: Energy trading contracts (power/gas markets)")
    print("→ Each contract represents a different market/expiry combination")
    
    # 3. Technical Indicator Timeframes
    print("\n3. PREDICTOR GRANULARITIES (Timeframes)")
    print("-" * 40)
    print(f"ATR/MACD Granularities: {PREDICTOR_GRANULARITIES['atr_macd_granularities']}")
    print(f"Swing Granularities: {PREDICTOR_GRANULARITIES['swing_granularities']}")
    print(f"ATR/MACD Count: {len(PREDICTOR_GRANULARITIES['atr_macd_granularities'])}")
    print(f"Swing Count: {len(PREDICTOR_GRANULARITIES['swing_granularities'])}")
    print("→ Purpose: Different timeframes for technical analysis")
    print("→ Creates timeframe combinations: 4 × 4 = 16 combinations")
    
    # 4. MACD Indicator Settings
    print("\n4. MACD CONFIGURATION")
    print("-" * 40)
    print("MACD Settings (Short, Long, Signal periods):")
    for i, config in enumerate(MACD_CONFIGS, 1):
        short, long, signal = config
        print(f"  Config {i}: {short}-{long}-{signal} periods")
        if config == (12, 26, 9):
            print("    → Standard MACD (most common)")
        elif config == (8, 21, 5):
            print("    → Fast MACD (more responsive)")
        elif config == (19, 39, 9):
            print("    → Slow MACD (less noise)")
    print(f"Count: {len(MACD_CONFIGS)}")
    print("→ Purpose: Different MACD sensitivities for trend detection")
    
    # 5. ATR Settings
    print("\n5. ATR (Average True Range) CONFIGURATION")
    print("-" * 40)
    print(f"ATR Lookback Periods: {ATR_LOOKBACKS}")
    print(f"Count: {len(ATR_LOOKBACKS)}")
    print("→ Purpose: Volatility measurement for position sizing")
    print("→ 21 periods = ~1 month of trading data")
    
    # 6. Risk Management
    print("\n6. RISK MANAGEMENT PARAMETERS")
    print("-" * 40)
    print(f"Stop Loss Ranges: {STOP_LOSS_RANGES}")
    print(f"Stop Loss / Take Profit Ratios: {SL_TP_RATIOS}")
    print(f"Stop Loss Count: {len(STOP_LOSS_RANGES)}")
    print(f"SL/TP Ratio Count: {len(SL_TP_RATIOS)}")
    print(f"Risk Combinations: {len(STOP_LOSS_RANGES)} × {len(SL_TP_RATIOS)} = {len(STOP_LOSS_RANGES) * len(SL_TP_RATIOS)}")
    print("→ Purpose: Risk management and position exit rules")
    print("→ Stop Loss: How much loss before exit (0.5x, 1.0x, 1.5x ATR)")
    print("→ SL/TP Ratio: Risk/reward ratio (1:1.5, 1:2.0)")
    
    # 7. Bias Classification Thresholds
    print("\n7. BIAS CLASSIFICATION THRESHOLDS")
    print("-" * 40)
    print("MACD Line Threshold Pairs:")
    for i, pair in enumerate(BIAS_THRESHOLD_RANGES['macd_line_pairs'], 1):
        print(f"  Pair {i}: {pair[0]} to {pair[1]}")
    
    print("\nMACD Histogram Threshold Pairs:")
    for i, pair in enumerate(BIAS_THRESHOLD_RANGES['macd_histogram_pairs'], 1):
        print(f"  Pair {i}: {pair[0]} to {pair[1]}")
    
    print(f"\nBias Combinations: {len(BIAS_THRESHOLD_RANGES['macd_line_pairs'])} × {len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs'])} = {len(BIAS_THRESHOLD_RANGES['macd_line_pairs']) * len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs'])}")
    print("→ Purpose: Define market bias (Bullish/Bearish/Neutral)")
    print("→ Wider ranges = Conservative (fewer bias changes)")
    print("→ Narrower ranges = Aggressive (more bias changes)")
    
    # 8. Strategy Thresholds - Neutral Base
    print("\n8. NEUTRAL STRATEGY THRESHOLDS (Base Values)")
    print("-" * 40)
    print(f"Neutral Buy Values: {NEUTRAL_STRATEGY_RANGES['buy_values']}")
    print(f"Neutral Sell Values: {NEUTRAL_STRATEGY_RANGES['sell_values']}")
    print(f"Buy Count: {len(NEUTRAL_STRATEGY_RANGES['buy_values'])}")
    print(f"Sell Count: {len(NEUTRAL_STRATEGY_RANGES['sell_values'])}")
    print("→ Purpose: Base buy/sell thresholds when market is neutral")
    print("→ 0.2 = Buy when price is in bottom 20% of recent range")
    print("→ 0.7 = Sell when price is in top 70% of recent range")
    
    # 9. Bias Adjustment Ranges
    print("\n9. BIAS ADJUSTMENT RANGES (Dynamic Modifications)")
    print("-" * 40)
    print("Buy Adjustments:")
    for key, values in BIAS_ADJUSTMENT_RANGES.items():
        if 'buy' in key:
            print(f"  {key}: {values}")
    
    print("\nSell Adjustments:")
    for key, values in BIAS_ADJUSTMENT_RANGES.items():
        if 'sell' in key:
            print(f"  {key}: {values}")
    
    # Calculate strategy combinations
    strategy_count = 1
    for key, values in BIAS_ADJUSTMENT_RANGES.items():
        strategy_count *= len(values)
    strategy_count *= len(NEUTRAL_STRATEGY_RANGES['buy_values'])
    strategy_count *= len(NEUTRAL_STRATEGY_RANGES['sell_values'])
    
    print(f"\nStrategy Combinations: {strategy_count}")
    print("→ Purpose: Adjust buy/sell thresholds based on market bias")
    print("→ Bullish bias: Might make buying easier (lower threshold)")
    print("→ Bearish bias: Might make selling easier (lower threshold)")
    
    # 10. Default Values (Reference)
    print("\n10. DEFAULT/BASELINE VALUES (Reference Only)")
    print("-" * 40)
    print("Bias Threshold Defaults:")
    for key, value in BIAS_THRESHOLD_DEFAULTS.items():
        print(f"  {key}: {value}")
    
    print("\nPosition Threshold Defaults:")
    for key, value in POSITION_THRESHOLD_DEFAULTS.items():
        print(f"  {key}: {value}")
    
    print("→ Purpose: Baseline/reference values for comparison")


def show_combination_calculation():
    """Show exactly how the 691,200 combinations are calculated."""
    
    print("\n" + "=" * 80)
    print("COMBINATION CALCULATION BREAKDOWN")
    print("=" * 80)
    
    # Base parameters (from Phase 1.1.1)
    contracts = len(CONTRACTS)
    atr_macd_gran = len(PREDICTOR_GRANULARITIES['atr_macd_granularities'])
    swing_gran = len(PREDICTOR_GRANULARITIES['swing_granularities'])
    macd_configs = len(MACD_CONFIGS)
    atr_lookbacks = len(ATR_LOOKBACKS)
    stop_loss = len(STOP_LOSS_RANGES)
    sl_tp_ratios = len(SL_TP_RATIOS)
    
    base_combinations = contracts * atr_macd_gran * swing_gran * macd_configs * atr_lookbacks * stop_loss * sl_tp_ratios
    
    print("BASE PARAMETER COMBINATIONS:")
    print(f"  Contracts: {contracts}")
    print(f"  ATR/MACD Granularities: {atr_macd_gran}")
    print(f"  Swing Granularities: {swing_gran}")  
    print(f"  MACD Configurations: {macd_configs}")
    print(f"  ATR Lookbacks: {atr_lookbacks}")
    print(f"  Stop Loss Ranges: {stop_loss}")
    print(f"  SL/TP Ratios: {sl_tp_ratios}")
    print(f"  → Base Total: {contracts} × {atr_macd_gran} × {swing_gran} × {macd_configs} × {atr_lookbacks} × {stop_loss} × {sl_tp_ratios} = {base_combinations:,}")
    
    # Bias combinations (from Phase 1.1.2)
    bias_line = len(BIAS_THRESHOLD_RANGES['macd_line_pairs'])
    bias_hist = len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs'])
    bias_combinations = bias_line * bias_hist
    
    print(f"\nBIAS THRESHOLD COMBINATIONS:")
    print(f"  MACD Line Pairs: {bias_line}")
    print(f"  MACD Histogram Pairs: {bias_hist}")
    print(f"  → Bias Total: {bias_line} × {bias_hist} = {bias_combinations}")
    
    # Strategy combinations (from Phase 1.1.2)
    neutral_buy = len(NEUTRAL_STRATEGY_RANGES['buy_values'])
    neutral_sell = len(NEUTRAL_STRATEGY_RANGES['sell_values'])
    
    strategy_components = []
    strategy_count = neutral_buy * neutral_sell
    
    print(f"\nSTRATEGY THRESHOLD COMBINATIONS:")
    print(f"  Neutral Buy Values: {neutral_buy}")
    print(f"  Neutral Sell Values: {neutral_sell}")
    
    for key, values in BIAS_ADJUSTMENT_RANGES.items():
        count = len(values)
        strategy_count *= count
        print(f"  {key.replace('_', ' ').title()}: {count}")
    
    print(f"  → Strategy Total: {neutral_buy} × {neutral_sell} × adjustment combinations = {strategy_count}")
    
    # Final total
    total_combinations = base_combinations * bias_combinations * strategy_count
    
    print(f"\nFINAL TOTAL COMBINATIONS:")
    print(f"  {base_combinations:,} (base) × {bias_combinations} (bias) × {strategy_count} (strategy) = {total_combinations:,}")
    
    print(f"\n🎯 RESULT: {total_combinations:,} unique parameter combinations to test!")


def show_data_flow():
    """Show how these inputs flow through the system."""
    
    print("\n" + "=" * 80)
    print("DATA FLOW: HOW INPUTS BECOME TRADING STRATEGIES")
    print("=" * 80)
    
    print("\n📊 INPUT STAGE:")
    print("   ↓ Market Data (contracts, timeframes)")
    print("   ↓ Technical Indicators (MACD, ATR settings)")
    print("   ↓ Risk Management (stop loss, take profit)")
    print("   ↓ Bias Classification (threshold ranges)")  
    print("   ↓ Strategy Logic (buy/sell thresholds)")
    
    print("\n🔄 COMBINATION STAGE (Phase 1.1.2):")
    print("   ↓ Generate bias threshold combinations (25)")
    print("   ↓ Generate strategy threshold combinations (96)")
    print("   ↓ Combine with base parameters (288)")
    print("   ↓ Create cartesian product of all parameters")
    
    print("\n🧪 TESTING STAGE (Future Phases):")
    print("   ↓ For each combination:")
    print("     • Load historical data for contract")
    print("     • Apply technical indicators with specified settings")
    print("     • Classify market bias using thresholds")
    print("     • Generate buy/sell signals using strategy thresholds")
    print("     • Execute trades with risk management rules")
    print("     • Calculate performance metrics")
    
    print("\n🏆 OPTIMIZATION STAGE (Future Phases):")
    print("   ↓ Rank all 691,200+ combinations by performance")
    print("   ↓ Identify best parameters for each market condition")
    print("   ↓ Create ensemble of top-performing strategies")
    print("   ↓ Deploy optimized trading system")


if __name__ == "__main__":
    show_all_inputs()
    show_combination_calculation()
    show_data_flow()
    
    print("\n" + "=" * 80)
    print("This comprehensive overview shows ALL inputs that contribute to")
    print("the massive parameter space that will be systematically tested")
    print("to find optimal energy trading strategies!")
    print("=" * 80)