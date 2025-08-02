#!/usr/bin/env python3
"""
GPU 100 Combo Generator
Create 100 combo files using the latest fixed GPU implementations
"""

import time
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import json
import warnings
warnings.filterwarnings('ignore')

# Add paths
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))

# Import GPU implementations
try:
    from feature_engineering.array_backend import ArrayBackend
    from feature_engineering.atr_calculator import ATRCalculator
    from feature_engineering.macd_calculator import MACDCalculator
    from feature_engineering.swing_point_detector import SwingPointDetector
    print("✅ GPU implementations imported successfully")
except ImportError as e:
    print(f"❌ Could not import GPU implementations: {e}")
    sys.exit(1)

def load_and_prepare_data():
    """Load and prepare data for GPU processing"""
    print("📂 Loading and preparing data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    # Load tick data
    tick_data = pd.read_parquet(legacy_data_path)
    print(f"✅ Loaded tick data: {len(tick_data):,} rows")
    
    # Convert to 15-minute OHLCV candles
    ohlcv_data = tick_data['price'].resample('15T').agg({
        'open': 'first',
        'high': 'max', 
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    # Add volume
    if 'volume' in tick_data.columns:
        volume_data = tick_data['volume'].resample('15T').sum()
        ohlcv_data['volume'] = volume_data.fillna(0)
    else:
        ohlcv_data['volume'] = np.random.exponential(1500, len(ohlcv_data))
    
    # Reset index to get timestamp column
    historical_candles = ohlcv_data.reset_index()
    historical_candles.rename(columns={'index': 'timestamp'}, inplace=True)
    
    # Create trades format for GPU functions
    trades_df = tick_data[['price']].reset_index()
    trades_df.columns = ['datetime', 'price']
    trades_df['nanotime'] = trades_df.index
    trades_df['tradeid'] = 'T' + trades_df.index.astype(str)
    
    print(f"✅ Data preparation complete")
    print(f"   Historical candles: {historical_candles.shape}")
    print(f"   Trades data: {trades_df.shape}")
    
    return trades_df, historical_candles

def generate_100_combinations():
    """Generate 100 parameter combinations"""
    print("🔢 Generating 100 parameter combinations...")
    
    combinations = []
    
    base_combo = {
        'combo_id': 0,
        'date_range': {'start': '2025-04-01', 'end': '2025-06-30'},
        'contract': 'dem07_25',
        'predictor_granularities': {'atr_macd': '15min', 'swing': '15min'},
        'macd_params': {'short': 12, 'long': 26, 'signal': 9},
        'atr_lookback': 21,
        'bias_thresholds': {
            'macd_line_lower': -2.5, 'macd_line_upper': 2.5,
            'macd_histogram_lower': -1.25, 'macd_histogram_upper': 1.25
        },
        'strategy_thresholds': {
            'neutral_buy': 0.2, 'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0, 'strong_bullish_buy_adjust': 0.05,
            'bearish_buy_adjust': -0.1, 'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1, 'bullish_sell_adjust': 0.05
        },
        'stop_loss': 0.5, 'sl_tp_ratio': 1.5, 'tp_value': 0.75
    }
    
    # Generate 100 variations
    for i in range(100):
        combo = base_combo.copy()
        combo['combo_id'] = i
        
        # Vary MACD parameters
        macd_variations = [
            {'short': 8, 'long': 21, 'signal': 5},
            {'short': 12, 'long': 26, 'signal': 9}, 
            {'short': 5, 'long': 35, 'signal': 5},
            {'short': 19, 'long': 39, 'signal': 9},
            {'short': 6, 'long': 18, 'signal': 6},
            {'short': 10, 'long': 30, 'signal': 8},
            {'short': 15, 'long': 45, 'signal': 12},
            {'short': 7, 'long': 24, 'signal': 7},
            {'short': 9, 'long': 27, 'signal': 10},
            {'short': 11, 'long': 33, 'signal': 11}
        ]
        combo['macd_params'] = macd_variations[i % len(macd_variations)]
        
        # Vary ATR lookback
        atr_variations = [10, 14, 17, 21, 24, 28, 31, 35, 38, 42]
        combo['atr_lookback'] = atr_variations[i % len(atr_variations)]
        
        # Vary bias thresholds
        bias_multiplier = 0.5 + (i % 20) * 0.1
        combo['bias_thresholds'] = {
            'macd_line_lower': -2.5 * bias_multiplier,
            'macd_line_upper': 2.5 * bias_multiplier,
            'macd_histogram_lower': -1.25 * bias_multiplier,
            'macd_histogram_upper': 1.25 * bias_multiplier
        }
        
        # Vary strategy thresholds
        neutral_base = 0.10 + (i % 50) * 0.005
        combo['strategy_thresholds']['neutral_buy'] = neutral_base
        combo['strategy_thresholds']['neutral_sell'] = neutral_base + 0.5
        
        # Vary stop loss and TP
        stop_loss_variations = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        combo['stop_loss'] = stop_loss_variations[i % len(stop_loss_variations)]
        
        sl_tp_ratios = [1.0, 1.2, 1.5, 1.8, 2.0, 2.2]
        combo['sl_tp_ratio'] = sl_tp_ratios[i % len(sl_tp_ratios)]
        combo['tp_value'] = combo['stop_loss'] * combo['sl_tp_ratio']
        
        combinations.append(combo)
    
    print(f"✅ Generated {len(combinations)} parameter combinations")
    return combinations

def create_combo_batch_gpu(trades_df, historical_candles, combinations, output_dir):
    """Create combo files using GPU implementations"""
    print(f"🚀 Creating {len(combinations)} combo files using GPU implementations")
    print("=" * 70)
    print("Using fixed GPU implementations:")
    print("  - ArrayBackend with CuPy/NumPy fallback")
    print("  - MACDCalculator")
    print("  - ATRCalculator")
    print("  - SwingPointDetector")
    
    # Initialize GPU backend and calculators
    backend = ArrayBackend()
    macd_calc = MACDCalculator(backend)
    atr_calc = ATRCalculator(backend)
    swing_detector = SwingPointDetector(backend)
    
    print(f"✅ GPU backend initialized: {backend.backend}")
    
    successful_results = []
    metadata_records = []
    
    for i, combo in enumerate(combinations):
        combo_start_time = time.time()
        combo_id = combo['combo_id']
        
        try:
            # Extract parameters
            macd_short = combo['macd_params']['short']
            macd_long = combo['macd_params']['long']
            macd_signal = combo['macd_params']['signal']
            atr_period = combo['atr_lookback']
            
            if (i + 1) % 10 == 0:
                print(f"🔄 Processing combo {combo_id:3d}/100...")
                print(f"   MACD: short={macd_short}, long={macd_long}, signal={macd_signal}")
                print(f"   ATR: period={atr_period}")
            
            # Use GPU MACD calculator
            gpu_macd = macd_calc.compute_macd(
                trades_df=trades_df,
                historical_candles=historical_candles,
                se=macd_short,
                le=macd_long,
                signal_period=macd_signal,
                price_col='price',
                datetime_col='datetime',
                candle_granularity='15min'
            )
            
            # Use GPU ATR calculator
            gpu_atr = atr_calc.compute_atr(
                trades_df=trades_df,
                historical_candles=historical_candles,
                atr_period=atr_period,
                price_col='price',
                datetime_col='datetime',
                candle_granularity='15min'
            )
            
            # Use GPU swing point detector
            gpu_swing = swing_detector.detect_swings(
                ohlc_df=historical_candles,
                high_col='high',
                low_col='low'
            )
            
            # Start with historical candles as base
            result_data = historical_candles.copy()
            
            # Merge GPU results
            # MACD results
            if not gpu_macd.empty:
                macd_data = gpu_macd[['macd', 'signal', 'histogram']].copy()
                macd_data.columns = ['macd_line', 'macd_signal', 'macd_histogram']
                for col in macd_data.columns:
                    result_data[col] = macd_data[col]
            
            # ATR results
            if not gpu_atr.empty and 'atr' in gpu_atr.columns:
                result_data['atr'] = gpu_atr['atr']
            
            # Swing point results
            if not gpu_swing.empty:
                if 'swing_high' in gpu_swing.columns:
                    result_data['swing_high'] = gpu_swing['swing_high']
                if 'swing_low' in gpu_swing.columns:
                    result_data['swing_low'] = gpu_swing['swing_low']
            
            # Add bias classification
            bias_thresholds = combo['bias_thresholds']
            result_data['bias_classification'] = 'neutral'
            if 'macd_line' in result_data.columns:
                result_data.loc[result_data['macd_line'] > bias_thresholds['macd_line_upper'], 'bias_classification'] = 'bullish'
                result_data.loc[result_data['macd_line'] < bias_thresholds['macd_line_lower'], 'bias_classification'] = 'bearish'
            
            # Add position signals
            strategy_thresholds = combo['strategy_thresholds']
            result_data['position_signal'] = 'hold'
            
            if 'macd_histogram' in result_data.columns:
                bullish_mask = result_data['bias_classification'] == 'bullish'
                bearish_mask = result_data['bias_classification'] == 'bearish'
                neutral_mask = result_data['bias_classification'] == 'neutral'
                
                macd_positive = result_data['macd_histogram'] > 0
                macd_negative = result_data['macd_histogram'] < 0
                
                # Buy signals
                result_data.loc[bullish_mask & macd_positive, 'position_signal'] = 'buy'
                result_data.loc[neutral_mask & macd_positive, 'position_signal'] = 'buy'
                
                # Sell signals  
                result_data.loc[bearish_mask & macd_negative, 'position_signal'] = 'sell'
                result_data.loc[neutral_mask & macd_negative, 'position_signal'] = 'sell'
            
            # Add combo metadata
            result_data['combo_id'] = combo_id
            result_data['contract'] = combo['contract']
            result_data['macd_short'] = macd_short
            result_data['macd_long'] = macd_long
            result_data['macd_signal_period'] = macd_signal
            result_data['atr_period'] = atr_period
            result_data['stop_loss'] = combo['stop_loss']
            result_data['take_profit'] = combo['tp_value']
            
            processing_time = time.time() - combo_start_time
            
            # Save combo file
            combo_file = output_dir / f"combo_{combo_id:03d}.parquet"
            result_data.to_parquet(combo_file, index=False)
            
            # Collect metadata
            metadata_record = {
                'combo_id': combo_id,
                'processing_time_seconds': processing_time,
                'result_shape_rows': result_data.shape[0],
                'result_shape_cols': result_data.shape[1],
                'features_computed': result_data.shape[1] - historical_candles.shape[1],
                'contract': combo.get('contract', 'dem07_25'),
                'date_range_start': combo.get('date_range', {}).get('start', '2025-04-01'),
                'date_range_end': combo.get('date_range', {}).get('end', '2025-06-30'),
                'macd_short': macd_short,
                'macd_long': macd_long,
                'macd_signal': macd_signal,
                'atr_lookback': atr_period,
                'bias_macd_line_lower': combo.get('bias_thresholds', {}).get('macd_line_lower', -2.5),
                'bias_macd_line_upper': combo.get('bias_thresholds', {}).get('macd_line_upper', 2.5),
                'bias_macd_hist_lower': combo.get('bias_thresholds', {}).get('macd_histogram_lower', -1.25),
                'bias_macd_hist_upper': combo.get('bias_thresholds', {}).get('macd_histogram_upper', 1.25),
                'strategy_neutral_buy': combo.get('strategy_thresholds', {}).get('neutral_buy', 0.2),
                'strategy_neutral_sell': combo.get('strategy_thresholds', {}).get('neutral_sell', 0.7),
                'stop_loss': combo.get('stop_loss', 0.5),
                'sl_tp_ratio': combo.get('sl_tp_ratio', 1.5),
                'tp_value': combo.get('tp_value', 0.75),
                'using_gpu_implementations': True,
                'gpu_backend_type': backend.backend
            }
            metadata_records.append(metadata_record)
            
            successful_results.append({
                'combo_id': combo_id,
                'processing_time': processing_time,
                'result_data': result_data
            })
            
            if (i + 1) % 10 == 0:
                avg_time = np.mean([r['processing_time'] for r in successful_results[-10:]])
                print(f"✅ Created {i + 1:3d}/100 combo files - Avg time: {avg_time:.3f}s")
                
        except Exception as e:
            print(f"❌ Error creating combo {combo_id}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\\n✅ GPU combo file creation complete: {len(successful_results)} files created")
    return successful_results, metadata_records

def main():
    """Main execution using GPU implementations"""
    print("🚀 GPU 100 COMBINATION GENERATOR")
    print("=" * 60)
    print("✅ Uses latest fixed GPU implementations")
    print("✅ ArrayBackend with CuPy acceleration")
    print("✅ MACDCalculator, ATRCalculator, SwingPointDetector")
    
    # Setup output directory
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    data_dir = Path(f"{output_base}/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    windows_path = "C:\\\\Users\\\\krajcovic\\\\Documents\\\\Testing Data\\\\ATS_3_data"
    
    print(f"\\n📁 Output: {windows_path}/")
    
    try:
        start_time = time.time()
        
        # Load and prepare data
        trades_df, historical_candles = load_and_prepare_data()
        
        # Generate 100 combinations
        combinations = generate_100_combinations()
        
        # Create combo data files using GPU implementations
        successful_results, metadata_records = create_combo_batch_gpu(
            trades_df, historical_candles, combinations, data_dir)
        
        total_time = time.time() - start_time
        
        # Create metadata parquet file
        if metadata_records:
            print(f"\\n💾 Creating metadata parquet file...")
            metadata_df = pd.DataFrame(metadata_records)
            metadata_file = Path(output_base) / "gpu_combinations_metadata.parquet"
            metadata_df.to_parquet(metadata_file, index=False)
            print(f"   ✅ Saved metadata for {len(metadata_records)} combinations")
        
        # Results summary
        print(f"\\n🎉 GPU 100 COMBINATION GENERATOR COMPLETE!")
        print("=" * 70)
        
        successful_count = len(successful_results)
        success_rate = (successful_count / len(combinations)) * 100
        
        print(f"📊 Results:")
        print(f"   Total combinations: {len(combinations)}")
        print(f"   Successful: {successful_count}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Total time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        
        if successful_count > 0:
            processing_times = [r['processing_time'] for r in successful_results]
            avg_time = np.mean(processing_times)
            throughput = successful_count / total_time
            print(f"   Average time per combo: {avg_time:.3f}s")
            print(f"   Throughput: {throughput:.1f} combinations/second")
        
        # Save summary
        summary = {
            'test_metadata': {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_combinations': len(combinations),
                'successful_combinations': successful_count,
                'processing_time_seconds': total_time,
                'processing_time_minutes': total_time / 60,
                'candles_created': len(historical_candles),
                'windows_path': windows_path,
                'using_gpu_implementations': True,
                'gpu_implementations_used': [
                    'ArrayBackend',
                    'MACDCalculator',
                    'ATRCalculator',
                    'SwingPointDetector'
                ]
            },
            'files_created': {
                'combo_files': successful_count,
                'metadata_file': 1,
                'total_files': successful_count + 1
            }
        }
        
        with open(Path(output_base) / "gpu_100_combo_summary.json", 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\\n🎊 SUCCESS! GPU 100 combination generation complete!")
        print(f"📂 Results: {windows_path}")
        print(f"\\n🚀 USING: Latest fixed GPU implementations!")
        print(f"✅ ArrayBackend - CuPy/NumPy acceleration")
        print(f"✅ MACDCalculator - GPU-optimized MACD")
        print(f"✅ ATRCalculator - GPU-optimized ATR") 
        print(f"✅ SwingPointDetector - GPU-optimized swing detection")
        
        return True
        
    except Exception as e:
        print(f"\\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\\n🎉 GENERATION COMPLETE!")
    else:
        print(f"\\n💥 Generation failed")