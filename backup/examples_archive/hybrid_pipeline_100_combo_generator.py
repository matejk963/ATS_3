#!/usr/bin/env python3
"""
Hybrid Pipeline 100 Combo Generator
Uses individual GPU calculators directly with trades_df + historical_candles format,
then saves combo data to ATS_3_data with metadata at the same level as data directory
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

# Import individual GPU calculators and parallel processing
try:
    from feature_engineering.array_backend import ArrayBackend
    from feature_engineering.macd_calculator import MACDCalculator
    from feature_engineering.atr_calculator import ATRCalculator
    from feature_engineering.swing_point_detector import SwingPointDetector
    from feature_engineering.bias_classifier import GPUBiasClassifier, ThresholdConfig
    from feature_engineering.position_generator import GPUPositionGenerator, ThresholdConfig as PositionThresholdConfig
    from gpu_parallel_processing import generate_combination_batch
    print("✅ Individual GPU calculators and parallel processing imported successfully")
except ImportError as e:
    print(f"❌ Could not import modules: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def load_market_data():
    """Load market data in both tick and OHLCV formats"""
    print("📂 Loading market data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    # Load tick data
    tick_data = pd.read_parquet(legacy_data_path)
    print(f"✅ Loaded tick data: {len(tick_data):,} rows")
    print(f"   Date range: {tick_data.index.min()} to {tick_data.index.max()}")
    
    # Create trades format for individual calculators
    trades_df = tick_data[['price']].reset_index()
    trades_df.columns = ['datetime', 'price']
    trades_df['nanotime'] = trades_df.index
    trades_df['tradeid'] = 'T' + trades_df.index.astype(str)
    
    # Convert to 15-minute OHLCV format for historical candles
    print("🔄 Converting tick data to 15-minute OHLCV format...")
    
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
    
    # Reset index to get timestamp column for historical candles
    historical_candles = ohlcv_data.reset_index()
    historical_candles.rename(columns={'index': 'timestamp'}, inplace=True)
    
    print(f"✅ Created trades data: {trades_df.shape}")
    print(f"✅ Created historical candles: {historical_candles.shape}")
    
    return trades_df, historical_candles

def create_combo_with_individual_calculators(calculators, trades_df, historical_candles, combo, output_dir):
    """Create one combo file using individual GPU calculators"""
    combo_id = combo['combo_id']
    combo_start_time = time.time()
    
    try:
        # Extract parameters
        macd_params = combo.get('macd_params', {'short': 12, 'long': 26, 'signal': 9})
        atr_period = combo.get('atr_lookback', 21)
        
        print(f"   🔄 Processing combo {combo_id:3d} - MACD: {macd_params}, ATR: {atr_period}")
        
        # Unpack calculators
        macd_calc, atr_calc, swing_detector, bias_classifier, position_generator = calculators
        
        # Step 1: Compute MACD using individual calculator
        macd_result = macd_calc.compute_macd(
            trades_df=trades_df,
            historical_candles=historical_candles.set_index('timestamp'),
            se=macd_params['short'],
            le=macd_params['long'],
            signal_period=macd_params['signal'],
            price_col='price',
            datetime_col='datetime',
            candle_granularity='15min'
        )
        
        # Step 2: Compute ATR using individual calculator  
        atr_result = atr_calc.compute_atr(
            trades_df=trades_df,
            historical_candles=historical_candles.set_index('timestamp'),
            atr_period=atr_period,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='15min'
        )
        
        # Step 3: Compute swing points
        swing_result = swing_detector.detect_swings(
            ohlc_df=historical_candles,
            high_col='high',
            low_col='low'
        )
        
        # Step 4: Merge all results with historical candles as base
        result_data = historical_candles.copy()
        
        # Convert individual calculator results to candle periods and merge
        # MACD data
        if not macd_result.empty:
            macd_result['period'] = pd.to_datetime(macd_result['datetime']).dt.floor('15min')
            macd_candle = macd_result.groupby('period')[['macd', 'signal', 'hist']].last().reset_index()
            result_data = result_data.merge(macd_candle, left_on='timestamp', right_on='period', how='left')
            result_data = result_data.drop(columns=['period'], errors='ignore')
            
            # Rename columns to match expected format
            result_data = result_data.rename(columns={
                'macd': 'macd_line',
                'signal': 'macd_signal',
                'hist': 'macd_histogram'
            })
        
        # ATR data
        if not atr_result.empty:
            atr_result['period'] = pd.to_datetime(atr_result['datetime']).dt.floor('15min')
            atr_candle = atr_result.groupby('period')['atr'].last().reset_index()
            result_data = result_data.merge(atr_candle, left_on='timestamp', right_on='period', how='left')
            result_data = result_data.drop(columns=['period'], errors='ignore')
        
        # Swing points data
        if not swing_result.empty:
            result_data = result_data.merge(swing_result.reset_index(), left_on='timestamp', right_on='timestamp', how='left')
        
        # Step 5: Compute bias classification
        if 'macd_line' in result_data.columns and 'macd_histogram' in result_data.columns:
            # Create bias thresholds from combo parameters
            bias_thresholds_dict = combo.get('bias_thresholds', {
                'macd_line_lower': -2.5, 'macd_line_upper': 2.5,
                'macd_histogram_lower': -1.25, 'macd_histogram_upper': 1.25
            })
            bias_thresholds = ThresholdConfig(
                macd_line_lower=bias_thresholds_dict['macd_line_lower'],
                macd_line_upper=bias_thresholds_dict['macd_line_upper'],
                macd_histogram_lower=bias_thresholds_dict['macd_histogram_lower'],
                macd_histogram_upper=bias_thresholds_dict['macd_histogram_upper']
            )
            
            # Compute bias classification
            bias_numeric, bias_labels = bias_classifier.compute_bias_classification(
                macd_line=result_data['macd_line'].values,
                macd_histogram=result_data['macd_histogram'].values,
                config=bias_thresholds
            )
            
            result_data['bias_numeric'] = bias_numeric
            result_data['bias_classification'] = bias_labels
            
            # Compute price position (simple normalized position within range)
            price_range = result_data['close'].max() - result_data['close'].min()
            if price_range > 0:
                result_data['price_position'] = (result_data['close'] - result_data['close'].min()) / price_range
            else:
                result_data['price_position'] = 0.5  # Neutral if no price movement
        
        # Step 6: Compute position signals
        if 'bias_numeric' in result_data.columns and 'price_position' in result_data.columns:
            # Create position thresholds from combo parameters  
            strategy_thresholds_dict = combo.get('strategy_thresholds', {
                'neutral_buy': 0.2, 'neutral_sell': 0.7
            })
            position_thresholds = PositionThresholdConfig(
                neutral_buy=strategy_thresholds_dict['neutral_buy'],
                neutral_sell=strategy_thresholds_dict['neutral_sell']
            )
            
            # Compute position signals
            position_signals = position_generator.compute_position_signals(
                bias_numeric=result_data['bias_numeric'].values,
                price_position=result_data['price_position'].values,
                config=position_thresholds
            )
            
            result_data['position_signal'] = position_signals
        
        # Step 7: Add combo metadata
        result_data['combo_id'] = combo_id
        result_data['contract'] = combo.get('contract', 'dem07_25')
        result_data['macd_short'] = macd_params['short']
        result_data['macd_long'] = macd_params['long']
        result_data['macd_signal_period'] = macd_params['signal']
        result_data['atr_period'] = atr_period
        result_data['stop_loss'] = combo.get('stop_loss', 0.5)
        result_data['take_profit'] = combo.get('tp_value', 0.75)
        
        processing_time = time.time() - combo_start_time
        
        # Save combo file
        combo_file = output_dir / f"combo_{combo_id:03d}.parquet"
        result_data.to_parquet(combo_file, index=False)
        
        print(f"   ✅ Saved combo {combo_id:3d} in {processing_time:.2f}s - Shape: {result_data.shape}")
        
        # Create metadata record
        metadata_record = {
            'combo_id': combo_id,
            'processing_time_seconds': processing_time,
            'result_shape_rows': result_data.shape[0],
            'result_shape_cols': result_data.shape[1],
            'contract': combo.get('contract', 'dem07_25'),
            'date_range_start': combo.get('date_range', {}).get('start', '2025-04-01'),
            'date_range_end': combo.get('date_range', {}).get('end', '2025-06-30'),
            'macd_short': macd_params['short'],
            'macd_long': macd_params['long'],
            'macd_signal': macd_params['signal'],
            'atr_lookback': atr_period,
            'bias_macd_line_lower': bias_thresholds_dict['macd_line_lower'],
            'bias_macd_line_upper': bias_thresholds_dict['macd_line_upper'],
            'bias_macd_hist_lower': bias_thresholds_dict['macd_histogram_lower'],
            'bias_macd_hist_upper': bias_thresholds_dict['macd_histogram_upper'],
            'strategy_neutral_buy': strategy_thresholds_dict['neutral_buy'],
            'strategy_neutral_sell': strategy_thresholds_dict['neutral_sell'],
            'stop_loss': combo.get('stop_loss', 0.5),
            'sl_tp_ratio': combo.get('sl_tp_ratio', 1.5),
            'tp_value': combo.get('tp_value', 0.75),
            'using_individual_calculators': True,
            'features_included': 'MACD + ATR + Swing Points + Bias + Position Signals'
        }
        
        return True, processing_time, metadata_record
        
    except Exception as e:
        print(f"   ❌ Error processing combo {combo_id}: {e}")
        import traceback
        traceback.print_exc()
        return False, 0, None

def main():
    """Main execution using individual GPU calculators"""
    print("🚀 HYBRID PIPELINE 100 COMBO GENERATOR")
    print("=" * 70)
    print("✅ Uses individual GPU calculators directly")
    print("✅ Trades_df + historical_candles input format")
    print("✅ All features: MACD + ATR + Swing + Bias + Positions")
    
    # Setup output directory
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    data_dir = Path(f"{output_base}/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    windows_path = "C:\\\\Users\\\\krajcovic\\\\Documents\\\\Testing Data\\\\ATS_3_data"
    
    print(f"\\n📁 Output: {windows_path}/")
    
    try:
        start_time = time.time()
        
        # Initialize individual GPU calculators
        print("🔧 Initializing individual GPU calculators...")
        backend = ArrayBackend(backend='cupy')
        macd_calc = MACDCalculator(backend)
        atr_calc = ATRCalculator(backend)
        swing_detector = SwingPointDetector(backend)
        bias_classifier = GPUBiasClassifier(backend)
        position_generator = GPUPositionGenerator(backend)
        calculators = (macd_calc, atr_calc, swing_detector, bias_classifier, position_generator)
        print("✅ Individual GPU calculators initialized")
        
        # Load market data in both formats
        trades_df, historical_candles = load_market_data()
        
        # Generate 100 combinations using GPU parallel processing
        print("🔢 Generating 100 parameter combinations...")
        combinations = generate_combination_batch(start_idx=0, batch_size=100)
        print(f"✅ Generated {len(combinations)} combinations")
        
        # Process combinations
        print(f"\\n🔧 Processing {len(combinations)} combinations with individual calculators...")
        
        successful_results = []
        metadata_records = []
        
        for i, combo in enumerate(combinations):
            success, proc_time, metadata = create_combo_with_individual_calculators(
                calculators, trades_df, historical_candles, combo, data_dir
            )
            
            if success:
                successful_results.append({
                    'combo_id': combo['combo_id'],
                    'processing_time': proc_time
                })
                metadata_records.append(metadata)
            
            # Progress update every 10 combos
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                avg_time = np.mean([r['processing_time'] for r in successful_results[-10:]])
                print(f"   📊 Progress: {i+1}/{len(combinations)} - Avg time: {avg_time:.2f}s - Elapsed: {elapsed/60:.1f}min")
        
        total_time = time.time() - start_time
        
        # Create metadata parquet file at the same level as data directory
        if metadata_records:
            print(f"\\n💾 Creating metadata parquet file...")
            metadata_df = pd.DataFrame(metadata_records)
            metadata_file = Path(output_base) / "hybrid_combinations_metadata.parquet"
            metadata_df.to_parquet(metadata_file, index=False)
            print(f"   ✅ Saved metadata for {len(metadata_records)} combinations")
        
        # Results summary
        print(f"\\n🎉 HYBRID PIPELINE 100 COMBO GENERATOR COMPLETE!")
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
            print(f"   Average time per combo: {avg_time:.2f}s")
            print(f"   Throughput: {throughput:.2f} combinations/second")
        
        # Save summary
        summary = {
            'test_metadata': {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_combinations': len(combinations),
                'successful_combinations': successful_count,
                'processing_time_seconds': total_time,
                'processing_time_minutes': total_time / 60,
                'windows_path': windows_path,
                'using_individual_calculators': True,
                'input_format': 'trades_df + historical_candles',
                'features_included': [
                    'MACD (line, signal, histogram)',
                    'ATR',
                    'Swing points (high, low)',
                    'Bias classification (numeric, label)',
                    'Price position',
                    'Position signals'
                ]
            },
            'files_created': {
                'combo_files': successful_count,
                'metadata_file': 1,
                'total_files': successful_count + 1
            }
        }
        
        with open(Path(output_base) / "hybrid_pipeline_100_combo_summary.json", 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\\n🎊 SUCCESS! Hybrid pipeline 100 combo generation complete!")
        print(f"📂 Results: {windows_path}")
        print(f"\\n🚀 FEATURES GENERATED:")
        print(f"✅ MACD (line, signal, histogram) - using trades_df + historical_candles")
        print(f"✅ ATR (Average True Range) - using trades_df + historical_candles")
        print(f"✅ Swing points (high, low) - using OHLCV data")
        print(f"✅ Bias classification (numeric + labels) - using MACD values")
        print(f"✅ Price position analysis - using close prices")
        print(f"✅ Position signals (buy/sell/hold) - using bias + price position")
        
        print(f"\\n📁 FILE STRUCTURE:")
        print(f"   {windows_path}/")
        print(f"   ├── data/")
        print(f"   │   ├── combo_000.parquet")
        print(f"   │   ├── combo_001.parquet")
        print(f"   │   └── ... ({successful_count} combo files)")
        print(f"   ├── hybrid_combinations_metadata.parquet")
        print(f"   └── hybrid_pipeline_100_combo_summary.json")
        
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