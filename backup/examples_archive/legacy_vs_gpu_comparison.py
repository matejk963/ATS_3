"""
Legacy vs GPU Processing Comparison
Compares the legacy core processing pipeline with our new GPU processing approach
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
from strategy_parameter_sweep_cpu_parallel_fixed import StrategyParameterSweepCPUParallel
from bias_classifier import BiasClassifier, ThresholdConfig
from local_technical_indicators import compute_macd_from_period_data, compute_atr_from_period_data, compute_swing_points_from_period_data

# GPU imports
from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from feature_engineering.array_backend import ArrayBackend

class LegacyVsGPUComparison:
    """
    Compare legacy CPU processing with new GPU accelerated processing
    """
    
    def __init__(self):
        self.legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
        self.gpu_results_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/data"
        self.metadata_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/combinations_metadata.parquet"
        
    def load_legacy_data(self):
        """Load the legacy tick data and convert to period format"""
        print("📂 Loading legacy tick data...")
        
        tick_data = pd.read_parquet(self.legacy_data_path)
        print(f"✅ Loaded {len(tick_data):,} tick records")
        
        # Convert to legacy period format
        period_data = tick_data.reset_index()
        period_data.rename(columns={period_data.columns[0]: 'datetime'}, inplace=True)
        
        # Add required columns for legacy functions
        if 'tradeid' not in period_data.columns:
            period_data['tradeid'] = 'T' + period_data.index.astype(str)
        if 'nanotime' not in period_data.columns:
            period_data['nanotime'] = period_data.index
            
        # Wrap in dictionary format expected by legacy functions
        period_dict = {'period_1': period_data}
        
        return period_dict
    
    def load_gpu_results(self, combo_id=0):
        """Load GPU processing results for comparison"""
        print(f"📊 Loading GPU results for combo_{combo_id:03d}...")
        
        # Load metadata
        metadata = pd.read_parquet(self.metadata_path)
        combo_params = metadata[metadata['combo_id'] == combo_id].iloc[0]
        
        # Load GPU result data
        gpu_data = pd.read_parquet(f"{self.gpu_results_path}/combo_{combo_id:03d}.parquet")
        
        print(f"✅ Loaded GPU data: {gpu_data.shape}")
        print(f"   Parameters: MACD({combo_params['macd_short']},{combo_params['macd_long']},{combo_params['macd_signal']}), ATR({combo_params['atr_lookback']})")
        
        return gpu_data, combo_params
    
    def run_legacy_processing_pipeline(self, period_data, params):
        """
        Run the legacy core processing pipeline extracted from strategy_parameter_sweep_cpu_parallel_fixed.py
        """
        print("🔧 Running Legacy Core Processing Pipeline...")
        print("=" * 60)
        
        # Extract parameters
        macd_params = {
            'short': int(params['macd_short']),
            'long': int(params['macd_long']),
            'signal': int(params['macd_signal'])
        }
        atr_lookback = int(params['atr_lookback'])
        
        print(f"📈 MACD params: {macd_params}")
        print(f"📊 ATR lookback: {atr_lookback}")
        
        try:
            # Step 1: Compute MACD using legacy function
            print("🔢 Computing MACD...")
            macd_data = compute_macd_from_period_data(
                period_data=period_data,
                granularity='15min',
                se=macd_params['short'],
                le=macd_params['long'],
                cont=macd_params['signal']
            )
            print(f"✅ MACD computed: {len(macd_data['period_1'])} records")
            
            # Step 2: Compute ATR using legacy function
            print("📊 Computing ATR...")
            atr_data = compute_atr_from_period_data(
                period_data=period_data,
                granularity='15min',
                atr_lookback=atr_lookback
            )
            print(f"✅ ATR computed: {len(atr_data['period_1'])} records")
            
            # Step 3: Compute Swing Points using legacy function
            print("📈 Computing Swing Points...")
            swing_data = compute_swing_points_from_period_data(
                period_data=period_data,
                granularity='15min',
                lookback=20  # Default swing lookback
            )
            print(f"✅ Swing Points computed: {len(swing_data['period_1'])} records")
            
            # Step 4: Merge data (simplified version of legacy merge)
            print("🔧 Merging technical indicators...")
            period_key = 'period_1'
            
            # Start with base period data
            base_data = period_data[period_key].reset_index(drop=True)
            
            # Merge MACD data
            merged_data = base_data.merge(
                macd_data[period_key], 
                on=['tradeid', 'datetime', 'nanotime'], 
                how='left'
            )
            
            # Merge ATR data
            merged_data = merged_data.merge(
                atr_data[period_key], 
                on=['tradeid', 'datetime', 'nanotime'], 
                how='left'
            )
            
            # Merge Swing Points data
            merged_data = merged_data.merge(
                swing_data[period_key], 
                on=['tradeid', 'datetime', 'nanotime'], 
                how='left'
            )
            
            print(f"✅ Data merged: {merged_data.shape}")
            print(f"   Columns: {list(merged_data.columns)}")
            
            # Step 5: Extract final features (matching GPU output format)
            final_data = merged_data[['datetime', 'nanotime', 'tradeid', 'macd', 'signal', 'hist', 'atr', 'swing_high', 'swing_low']].copy()
            final_data = final_data.rename(columns={
                'macd': 'macd_line',
                'signal': 'macd_signal',
                'hist': 'macd_histogram'
            })
            
            # Clean up memory
            del macd_data, atr_data, swing_data, merged_data
            gc.collect()
            
            print(f"✅ Legacy processing complete: {final_data.shape}")
            return final_data
            
        except Exception as e:
            print(f"❌ Error in legacy processing: {e}")
            raise
    
    def run_gpu_processing_pipeline(self, tick_data, params):
        """
        Run our GPU processing pipeline for comparison
        """
        print("🚀 Running GPU Processing Pipeline...")
        print("=" * 60)
        
        # Convert tick data to OHLCV format (15-minute candles)
        print("🔄 Converting tick data to OHLCV format...")
        ohlcv_data = tick_data.resample('15min').agg({
            'price': ['first', 'max', 'min', 'last'],
            'volume': 'sum'
        }).dropna()
        
        # Flatten column names
        ohlcv_data.columns = ['open', 'high', 'low', 'close', 'volume']
        
        print(f"✅ OHLCV data created: {ohlcv_data.shape}")
        
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
        
        # Process with GPU pipeline
        print("🚀 Computing features with GPU...")
        gpu_result = pipeline.compute_all_indicators(
            data=ohlcv_data,
            macd_params=macd_params,
            atr_period=atr_lookback
        )
        
        print(f"✅ GPU processing complete: {gpu_result.shape}")
        return gpu_result
    
    def compare_results(self, legacy_data, gpu_data, tolerance=1e-4):
        """
        Compare legacy and GPU processing results
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
        
        # Compare technical indicators including swing points
        comparison_mapping = {
            'macd_line': 'macd_line',
            'macd_signal': 'macd_signal', 
            'macd_histogram': 'macd_histogram',
            'atr': 'atr',
            'swing_high': 'swing_highs',  # Note: GPU uses plural 'swing_highs'
            'swing_low': 'swing_lows'     # Note: GPU uses plural 'swing_lows'
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
    
    def run_comparison(self, combo_id=0):
        """
        Run full comparison between legacy and GPU processing
        """
        print("🔬 LEGACY vs GPU PROCESSING COMPARISON")
        print("=" * 80)
        print(f"Comparing processing pipelines for combo_{combo_id:03d}")
        print()
        
        # Load data
        period_data = self.load_legacy_data()
        gpu_data, combo_params = self.load_gpu_results(combo_id)
        
        # Load raw tick data for GPU processing
        tick_data = pd.read_parquet(self.legacy_data_path)
        
        # Run legacy processing pipeline
        print("\n" + "="*80)
        legacy_result = self.run_legacy_processing_pipeline(period_data, combo_params)
        
        # Run GPU processing pipeline
        print("\n" + "="*80)
        gpu_result = self.run_gpu_processing_pipeline(tick_data, combo_params)
        
        # Compare results
        print("\n" + "="*80)
        comparison_results = self.compare_results(legacy_result, gpu_result)
        
        # Summary
        print(f"\n📈 COMPARISON SUMMARY:")
        print("=" * 40)
        
        total_comparisons = len(comparison_results)
        successful_matches = sum(1 for r in comparison_results.values() if r['matches_tolerance'])
        
        print(f"   Total indicators compared: {total_comparisons}")
        print(f"   Successful matches: {successful_matches}")
        print(f"   Overall success rate: {successful_matches/total_comparisons*100:.1f}%") if total_comparisons > 0 else print("   No comparisons made")
        
        if successful_matches == total_comparisons and total_comparisons > 0:
            print(f"\n🎉 SUCCESS! GPU processing matches legacy pipeline")
            print(f"✅ All {total_comparisons} indicators computed correctly")
        else:
            print(f"\n⚠️  PARTIAL MATCH: {successful_matches}/{total_comparisons} indicators match")
            print("🔧 Differences detected - further investigation needed")
        
        return comparison_results

def main():
    """Main comparison function"""
    print("🚀 Starting Legacy vs GPU Processing Comparison")
    print("=" * 80)
    
    comparison = LegacyVsGPUComparison()
    
    # Run comparison for first combination
    results = comparison.run_comparison(combo_id=0)
    
    if results:
        print(f"\n🎊 COMPARISON COMPLETE!")
        
        # Print detailed results
        print("\n📋 DETAILED RESULTS:")
        for indicator, result in results.items():
            status = "✅" if result['matches_tolerance'] else "❌"
            print(f"   {status} {indicator}: {result['match_rate']:.1f}% match rate")
    else:
        print(f"\n🔍 COMPARISON INCOMPLETE: No results to compare")

if __name__ == "__main__":
    main()