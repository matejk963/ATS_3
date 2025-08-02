"""
Test Legacy Candle Generation Method
Uses the exact same candle generation logic for both legacy and GPU pipelines
"""

import pandas as pd
import numpy as np
import sys
import time
import gc
from pathlib import Path

# Add paths for imports
sys.path.append(str(Path(__file__).parent.parent / 'src'))
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/source_repos/ATS_2/combinations_generation_legacy')
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/source_repos/ATS_2/combinations_generation')
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/source_repos/ATS_2/core')

# Legacy imports
from local_technical_indicators import compute_macd_from_period_data, compute_atr_from_period_data, compute_swing_points_from_period_data

# GPU imports
from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline

class LegacyCandleGenerationTest:
    """
    Test using identical legacy candle generation for both pipelines
    """
    
    def __init__(self):
        self.legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
        self.metadata_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/combinations_metadata.parquet"
        
    def load_tick_data(self):
        """Load raw tick data"""
        print("📂 Loading tick data...")
        tick_data = pd.read_parquet(self.legacy_data_path)
        print(f"✅ Loaded {len(tick_data):,} tick records")
        return tick_data
        
    def load_combo_params(self, combo_id=0):
        """Load combination parameters"""
        metadata = pd.read_parquet(self.metadata_path)
        combo_params = metadata[metadata['combo_id'] == combo_id].iloc[0]
        return combo_params
    
    def generate_legacy_candles(self, tick_data, granularity='15min'):
        """
        Generate candles using EXACT legacy method from local_technical_indicators.py
        """
        print(f"🕯️ Generating {granularity} candles using legacy method...")
        
        # Convert to legacy period format
        period_data = tick_data.reset_index()
        period_data.rename(columns={period_data.columns[0]: 'datetime'}, inplace=True)
        
        # Add required columns for legacy functions
        if 'tradeid' not in period_data.columns:
            period_data['tradeid'] = 'T' + period_data.index.astype(str)
        if 'nanotime' not in period_data.columns:
            period_data['nanotime'] = period_data.index
            
        # Set datetime as index (legacy method)
        if 'datetime' in period_data.columns:
            period_data['datetime'] = pd.to_datetime(period_data['datetime'])
            period_data = period_data.set_index('datetime')
        
        # Convert granularity to pandas frequency (legacy mapping)
        freq_map = {
            '15min': '15T',
            '30min': '30T', 
            '1h': '1H',
            '4h': '4H'
        }
        freq = freq_map.get(granularity, '15T')
        
        # EXACT legacy candle aggregation
        candles = period_data.groupby(pd.Grouper(freq=freq)).agg({
            'price': ['first', 'max', 'min', 'last', 'count'],
            'tradeid': 'first',
            'nanotime': 'first'
        }).dropna()
        
        # Flatten column names (legacy method)
        candles.columns = ['open', 'high', 'low', 'close', 'volume', 'tradeid', 'nanotime']
        
        print(f"✅ Legacy candles generated: {candles.shape}")
        print(f"   Sample candle: {candles.iloc[0].to_dict()}")
        
        return candles
    
    def compute_legacy_indicators(self, candles, params):
        """
        Compute indicators using legacy functions but with pre-generated candles
        """
        print("🔧 Computing Legacy Indicators...")
        
        # Extract parameters
        macd_params = {
            'short': int(params['macd_short']),
            'long': int(params['macd_long']),
            'signal': int(params['macd_signal'])
        }
        atr_lookback = int(params['atr_lookback'])
        
        print(f"📈 MACD params: {macd_params}")
        print(f"📊 ATR lookback: {atr_lookback}")
        
        # Use candles directly for calculations (bypass legacy candle generation)
        close_prices = candles['close']
        
        # MACD calculation (extracted from legacy function)
        print("🔢 Computing MACD...")
        ema_short = close_prices.ewm(span=macd_params['short']).mean()
        ema_long = close_prices.ewm(span=macd_params['long']).mean()
        macd_line = ema_short - ema_long
        signal_line = macd_line.ewm(span=macd_params['signal']).mean()
        histogram = macd_line - signal_line
        
        # ATR calculation (extracted from legacy function)
        print("📊 Computing ATR...")
        high = candles['high']
        low = candles['low']
        close = candles['close']
        prev_close = close.shift(1)
        
        # True Range calculation
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR as SMA of True Range
        atr = true_range.rolling(window=atr_lookback).mean()
        
        # Swing Points calculation (extracted from legacy function) 
        print("📈 Computing Swing Points...")
        lookback = 20  # Default swing lookback
        swing_highs = high.rolling(window=lookback, center=True).max()
        swing_lows = low.rolling(window=lookback, center=True).min()
        
        # Create result DataFrame
        result = candles[['tradeid', 'nanotime']].copy()
        result['macd_line'] = macd_line
        result['macd_signal'] = signal_line
        result['macd_histogram'] = histogram
        result['atr'] = atr
        result['swing_high'] = swing_highs
        result['swing_low'] = swing_lows
        
        # Reset index to include datetime
        result = result.reset_index()
        
        print(f"✅ Legacy indicators computed: {result.shape}")
        return result
    
    def compute_gpu_indicators(self, candles, params):
        """
        Compute indicators using GPU pipeline with identical candle data
        """
        print("🚀 Computing GPU Indicators...")
        
        # Set up GPU pipeline
        pipeline = UnifiedTechnicalIndicatorsPipeline(dtype='float32')
        
        # Extract parameters (GPU uses fast/slow, not short/long)
        macd_params = {
            'fast': int(params['macd_short']),
            'slow': int(params['macd_long']),
            'signal': int(params['macd_signal'])
        }
        atr_lookback = int(params['atr_lookback'])
        
        print(f"📈 GPU MACD params: {macd_params}")
        print(f"📊 GPU ATR lookback: {atr_lookback}")
        
        # Prepare candle data for GPU (must have required columns)
        gpu_candles = candles[['open', 'high', 'low', 'close', 'volume']].copy()
        
        # Process with GPU pipeline
        print("🚀 Computing features with GPU...")
        gpu_result = pipeline.compute_all_indicators(
            data=gpu_candles,
            macd_params=macd_params,
            atr_period=atr_lookback
        )
        
        print(f"✅ GPU processing complete: {gpu_result.shape}")
        return gpu_result
    
    def compare_indicators(self, legacy_data, gpu_data, tolerance=1e-4):
        """
        Compare legacy and GPU indicator results
        """
        print("🔍 Comparing Legacy vs GPU Results...")
        print("=" * 60)
        
        # Align data lengths
        min_len = min(len(legacy_data), len(gpu_data))
        legacy_subset = legacy_data.iloc[:min_len].reset_index(drop=True)
        gpu_subset = gpu_data.iloc[:min_len].reset_index(drop=True)
        
        print(f"📊 Comparing {min_len} records")
        print(f"   Legacy columns: {list(legacy_subset.columns)}")
        print(f"   GPU columns: {list(gpu_subset.columns)}")
        
        # Compare indicators
        comparison_mapping = {
            'macd_line': 'macd_line',
            'macd_signal': 'macd_signal', 
            'macd_histogram': 'macd_histogram',
            'atr': 'atr',
            'swing_high': 'swing_highs',  # Note: GPU uses plural
            'swing_low': 'swing_lows'     # Note: GPU uses plural
        }
        
        results = {}
        
        for legacy_col, gpu_col in comparison_mapping.items():
            if legacy_col not in legacy_subset.columns:
                print(f"⚠️  Column {legacy_col} not found in legacy data")
                continue
            if gpu_col not in gpu_subset.columns:
                print(f"⚠️  Column {gpu_col} not found in GPU data")
                continue
            
            # Get non-null values
            legacy_values = legacy_subset[legacy_col].dropna()
            gpu_values = gpu_subset[gpu_col].dropna()
            
            # Align by taking minimum length
            compare_len = min(len(legacy_values), len(gpu_values))
            if compare_len == 0:
                print(f"⚠️  No valid values for comparison in {legacy_col}")
                continue
            
            legacy_compare = legacy_values.iloc[:compare_len]
            gpu_compare = gpu_values.iloc[:compare_len]
            
            # Calculate differences
            abs_diff = np.abs(legacy_compare - gpu_compare)
            max_diff = abs_diff.max()
            mean_diff = abs_diff.mean()
            
            # Check if values match within tolerance
            matches = abs_diff <= tolerance
            match_rate = matches.sum() / len(matches) * 100
            
            results[legacy_col] = {
                'gpu_col': gpu_col,
                'max_diff': max_diff,
                'mean_diff': mean_diff,
                'match_rate': match_rate,
                'compared_values': compare_len,
                'matches_tolerance': match_rate >= 95.0
            }
            
            status = "✅ MATCH" if match_rate >= 95.0 else "❌ MISMATCH"
            print(f"   {status} {legacy_col} vs {gpu_col}:")
            print(f"     Values compared: {compare_len}")
            print(f"     Max difference: {max_diff:.2e}")
            print(f"     Mean difference: {mean_diff:.2e}")
            print(f"     Match rate: {match_rate:.1f}%")
            
            # Show sample values for debugging if mismatch
            if match_rate < 95.0:
                print(f"     Sample legacy values: {legacy_compare.head(3).values}")
                print(f"     Sample GPU values: {gpu_compare.head(3).values}")
                print(f"     Sample differences: {abs_diff.head(3).values}")
        
        return results
    
    def run_test(self, combo_id=0):
        """
        Run the complete test using identical legacy candle generation
        """
        print("🔬 LEGACY CANDLE GENERATION TEST")
        print("=" * 80)
        print("Testing indicators using IDENTICAL candle generation for both pipelines")
        print(f"Combo ID: {combo_id}")
        print()
        
        # Load data
        tick_data = self.load_tick_data()
        combo_params = self.load_combo_params(combo_id)
        
        # Generate candles using legacy method
        print("\n" + "="*60)
        candles = self.generate_legacy_candles(tick_data, granularity='15min')
        
        # Compute indicators using legacy approach
        print("\n" + "="*60)
        legacy_result = self.compute_legacy_indicators(candles, combo_params)
        
        # Compute indicators using GPU approach (same candles)
        print("\n" + "="*60)
        gpu_result = self.compute_gpu_indicators(candles, combo_params)
        
        # Compare results
        print("\n" + "="*60)
        comparison_results = self.compare_indicators(legacy_result, gpu_result)
        
        # Summary
        print(f"\n📈 TEST SUMMARY:")
        print("=" * 40)
        
        total_comparisons = len(comparison_results)
        successful_matches = sum(1 for r in comparison_results.values() if r['matches_tolerance'])
        
        print(f"   Total indicators compared: {total_comparisons}")
        print(f"   Successful matches: {successful_matches}")
        print(f"   Overall success rate: {successful_matches/total_comparisons*100:.1f}%") if total_comparisons > 0 else print("   No comparisons made")
        
        if successful_matches == total_comparisons and total_comparisons > 0:
            print(f"\n🎉 SUCCESS! Indicators match when using identical candle generation")
            print(f"✅ All {total_comparisons} indicators computed identically")
        else:
            print(f"\n⚠️  PARTIAL MATCH: {successful_matches}/{total_comparisons} indicators match")
            print("🔧 Some differences remain - investigating indicator algorithms")
        
        return comparison_results

def main():
    """Main test function"""
    print("🚀 Starting Legacy Candle Generation Test")
    print("=" * 80)
    
    test = LegacyCandleGenerationTest()
    
    # Run test using identical candle generation
    results = test.run_test(combo_id=0)
    
    if results:
        print(f"\n🎊 TEST COMPLETE!")
        
        # Print detailed results
        print("\n📋 DETAILED RESULTS:")
        for indicator, result in results.items():
            status = "✅" if result['matches_tolerance'] else "❌"
            print(f"   {status} {indicator}: {result['match_rate']:.1f}% match rate")
    else:
        print(f"\n🔍 TEST INCOMPLETE: No results to compare")

if __name__ == "__main__":
    main()