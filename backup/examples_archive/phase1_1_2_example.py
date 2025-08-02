"""
Practical example demonstrating Phase 1.1.2 Parameter Combination Logic.

This example shows how bias and strategy threshold combinations are generated
and how they would be used in a trading strategy context.
"""

from src.gpu_parallel_processing.parameter_combinations import (
    generate_bias_threshold_combinations,
    generate_strategy_threshold_combinations,
    validate_bias_thresholds,
    validate_strategy_thresholds,
    get_combination_counts
)

def demonstrate_bias_combinations():
    """Show bias threshold combinations and their trading interpretation."""
    print("=" * 60)
    print("BIAS THRESHOLD COMBINATIONS")
    print("=" * 60)
    
    bias_combos = generate_bias_threshold_combinations()
    
    print(f"Total bias combinations generated: {len(bias_combos)}")
    print("\nFirst 5 bias combinations:")
    print("-" * 40)
    
    for i, combo in enumerate(bias_combos[:5]):
        print(f"\nCombination {i+1}:")
        print(f"  MACD Line: {combo['macd_line_lower']} to {combo['macd_line_upper']}")
        print(f"  MACD Hist: {combo['macd_histogram_lower']} to {combo['macd_histogram_upper']}")
        
        # Trading interpretation
        if abs(combo['macd_line_lower']) >= 2.0:
            sensitivity = "Conservative (wide range)"
        elif abs(combo['macd_line_lower']) >= 1.0:
            sensitivity = "Moderate"
        else:
            sensitivity = "Aggressive (narrow range)"
            
        print(f"  → Trading Style: {sensitivity}")
        print(f"  → Valid: {validate_bias_thresholds(combo)}")


def demonstrate_strategy_combinations():
    """Show strategy threshold combinations and their trading logic."""
    print("\n" + "=" * 60)
    print("STRATEGY THRESHOLD COMBINATIONS")
    print("=" * 60)
    
    strategy_combos = generate_strategy_threshold_combinations()
    
    print(f"Total strategy combinations generated: {len(strategy_combos)}")
    print("\nFirst 3 strategy combinations:")
    print("-" * 40)
    
    for i, combo in enumerate(strategy_combos[:3]):
        print(f"\nCombination {i+1}:")
        print(f"  Neutral Buy:  {combo['neutral_buy']}")
        print(f"  Neutral Sell: {combo['neutral_sell']}")
        print(f"  Bullish Buy Adjust: {combo['bullish_buy_adjust']:+.2f}")
        print(f"  Strong Bullish Buy: {combo['strong_bullish_buy_adjust']:+.2f}")
        print(f"  Bearish Buy Adjust: {combo['bearish_buy_adjust']:+.2f}")
        print(f"  Bullish Sell Adjust: {combo['bullish_sell_adjust']:+.2f}")
        
        # Calculate effective thresholds
        effective_bullish_buy = combo['neutral_buy'] + combo['bullish_buy_adjust']
        effective_strong_bullish_buy = combo['neutral_buy'] + combo['strong_bullish_buy_adjust']
        effective_bearish_buy = combo['neutral_buy'] + combo['bearish_buy_adjust']
        
        print(f"  → Effective Buy Thresholds:")
        print(f"    Strong Bullish: {effective_strong_bullish_buy:.2f}")
        print(f"    Bullish: {effective_bullish_buy:.2f}")
        print(f"    Neutral: {combo['neutral_buy']:.2f}")
        print(f"    Bearish: {effective_bearish_buy:.2f}")
        print(f"  → Valid: {validate_strategy_thresholds(combo)}")


def demonstrate_practical_trading_scenario():
    """Show how these combinations would work in practice."""
    print("\n" + "=" * 60)
    print("PRACTICAL TRADING SCENARIO")
    print("=" * 60)
    
    # Pick specific combinations for demonstration
    bias_combos = generate_bias_threshold_combinations()
    strategy_combos = generate_strategy_threshold_combinations()
    
    # Conservative bias thresholds (wide ranges)
    conservative_bias = bias_combos[0]  # Should be the widest ranges
    
    # Moderate strategy thresholds
    moderate_strategy = strategy_combos[len(strategy_combos)//2]  # Middle combination
    
    print("Selected Parameter Combination:")
    print("-" * 30)
    print(f"Bias Configuration:")
    print(f"  MACD Line range: {conservative_bias['macd_line_lower']} to {conservative_bias['macd_line_upper']}")
    print(f"  MACD Histogram: {conservative_bias['macd_histogram_lower']} to {conservative_bias['macd_histogram_upper']}")
    
    print(f"\nStrategy Configuration:")
    print(f"  Base Buy Threshold: {moderate_strategy['neutral_buy']}")
    print(f"  Base Sell Threshold: {moderate_strategy['neutral_sell']}")
    
    print("\nTrading Logic Simulation:")
    print("-" * 30)
    
    # Simulate different market conditions
    scenarios = [
        {"macd_line": -0.8, "macd_hist": -0.3, "price_position": 0.25, "condition": "Bearish"},
        {"macd_line": 0.1, "macd_hist": 0.05, "price_position": 0.22, "condition": "Neutral"},
        {"macd_line": 1.2, "macd_hist": 0.4, "price_position": 0.28, "condition": "Bullish"},
        {"macd_line": 2.1, "macd_hist": 0.8, "price_position": 0.25, "condition": "Strong Bullish"}
    ]
    
    for scenario in scenarios:
        print(f"\nScenario: {scenario['condition']} Market")
        print(f"  MACD Line: {scenario['macd_line']}")
        print(f"  MACD Histogram: {scenario['macd_hist']}")
        print(f"  Price Position: {scenario['price_position']}")
        
        # Determine bias classification
        macd_line_val = scenario['macd_line']
        macd_hist_val = scenario['macd_hist']
        
        if (macd_line_val <= conservative_bias['macd_line_lower'] and 
            macd_hist_val <= conservative_bias['macd_histogram_lower']):
            bias = "Strong Bearish"
            buy_threshold = moderate_strategy['neutral_buy'] + moderate_strategy['bearish_buy_adjust']
        elif macd_line_val <= conservative_bias['macd_line_lower']:
            bias = "Bearish"
            buy_threshold = moderate_strategy['neutral_buy'] + moderate_strategy['bearish_buy_adjust']
        elif (macd_line_val >= conservative_bias['macd_line_upper'] and 
              macd_hist_val >= conservative_bias['macd_histogram_upper']):
            bias = "Strong Bullish"
            buy_threshold = moderate_strategy['neutral_buy'] + moderate_strategy['strong_bullish_buy_adjust']
        elif macd_line_val >= conservative_bias['macd_line_upper']:
            bias = "Bullish"
            buy_threshold = moderate_strategy['neutral_buy'] + moderate_strategy['bullish_buy_adjust']
        else:
            bias = "Neutral"
            buy_threshold = moderate_strategy['neutral_buy']
        
        # Determine signal
        price_pos = scenario['price_position']
        if price_pos <= buy_threshold:
            signal = "BUY"
        elif price_pos >= moderate_strategy['neutral_sell']:
            signal = "SELL"
        else:
            signal = "HOLD"
        
        print(f"  → Detected Bias: {bias}")
        print(f"  → Effective Buy Threshold: {buy_threshold:.3f}")
        print(f"  → Trading Signal: {signal}")


def show_combination_statistics():
    """Display statistics about the parameter space."""
    print("\n" + "=" * 60)
    print("PARAMETER SPACE STATISTICS")
    print("=" * 60)
    
    counts = get_combination_counts()
    
    print("Individual Component Counts:")
    print("-" * 30)
    for key, value in counts.items():
        if 'combinations' not in key:
            print(f"  {key.replace('_', ' ').title()}: {value:,}")
    
    print("\nCombination Totals:")
    print("-" * 30)
    print(f"  Bias Combinations: {counts['bias_combinations']:,}")
    print(f"  Strategy Combinations: {counts['strategy_combinations']:,}")
    print(f"  Base Parameter Combinations: {counts['base_parameter_combinations']:,}")
    print(f"  TOTAL ESTIMATED COMBINATIONS: {counts['total_combinations_estimate']:,}")
    
    # Calculate memory/processing implications
    avg_backtest_time_seconds = 30  # Assume 30 seconds per combination
    total_hours = (counts['total_combinations_estimate'] * avg_backtest_time_seconds) / 3600
    total_days = total_hours / 24
    
    print(f"\nProcessing Implications (assuming 30s per backtest):")
    print("-" * 30)
    print(f"  Total Processing Time: {total_hours:,.0f} hours ({total_days:,.1f} days)")
    print(f"  With 100 parallel workers: {total_hours/100:,.1f} hours ({total_days/100:.1f} days)")
    print(f"  With 1000 parallel workers: {total_hours/1000:,.1f} hours ({total_days/1000:.2f} days)")


if __name__ == "__main__":
    print("Phase 1.1.2 Parameter Combination Logic - Practical Example")
    print("=" * 60)
    
    demonstrate_bias_combinations()
    demonstrate_strategy_combinations()
    demonstrate_practical_trading_scenario()
    show_combination_statistics()
    
    print("\n" + "=" * 60)
    print("Example complete! This demonstrates how the 691,200+ parameter")
    print("combinations will be systematically tested to find optimal")
    print("trading strategies across different market conditions.")
    print("=" * 60)