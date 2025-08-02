#!/usr/bin/env python3
"""
Test Legacy Combo Creation - Small Test
Creates just 5 combo files to test the actual legacy function integration
"""

import time
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import warnings
warnings.filterwarnings('ignore')

# Add legacy functions path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python"))

# Import legacy implementations
try:
    from predictors_tools import (
        compute_realtime_atr,
        compute_realtime_macd,
        detect_swing_points
    )
    print("✅ Legacy functions imported successfully")
except ImportError as e:
    print(f"❌ Could not import legacy functions: {e}")
    sys.exit(1)

def load_legacy_data():
    """Load legacy tick data"""
    print("📂 Loading legacy tick data...")
    
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
    
    # Create trades format for legacy functions
    trades_df = tick_data[['price']].reset_index()
    trades_df.columns = ['datetime', 'price']
    
    # Add required columns for legacy functions
    trades_df['nanotime'] = trades_df.index
    trades_df['tradeid'] = 'T' + trades_df.index.astype(str)
    
    print(f"✅ Created historical candles: {historical_candles.shape}")
    print(f"✅ Created trades data: {trades_df.shape}")
    
    return trades_df, historical_candles

def create_test_combos():
    """Create 5 test combinations"""
    combinations = []
    
    base_combo = {
        'combo_id': 0,
        'macd_params': {'short': 12, 'long': 26, 'signal': 9},
        'atr_lookback': 21,
        'contract': 'dem07_25'
    }
    
    # Create 5 variations
    macd_variations = [
        {'short': 8, 'long': 21, 'signal': 5},
        {'short': 12, 'long': 26, 'signal': 9}, 
        {'short': 5, 'long': 35, 'signal': 5},
        {'short': 19, 'long': 39, 'signal': 9},
        {'short': 6, 'long': 18, 'signal': 6}
    ]
    
    atr_variations = [10, 14, 17, 21, 24]
    
    for i in range(5):
        combo = base_combo.copy()
        combo['combo_id'] = i
        combo['macd_params'] = macd_variations[i]
        combo['atr_lookback'] = atr_variations[i]
        combinations.append(combo)
    
    print(f"✅ Generated {len(combinations)} test combinations")
    return combinations

def create_one_combo_with_legacy(trades_df, historical_candles, combo, output_dir):
    """Create one combo file using actual legacy functions"""
    combo_id = combo['combo_id']
    print(f"🔄 Creating combo {combo_id} with legacy functions...")
    
    start_time = time.time()
    
    try:
        # Extract parameters
        macd_short = combo['macd_params']['short']
        macd_long = combo['macd_params']['long']
        macd_signal = combo['macd_params']['signal']
        atr_period = combo['atr_lookback']
        
        print(f"   MACD: se={macd_short}, le={macd_long}, signal={macd_signal}")
        print(f"   ATR: period={atr_period}")
        
        # Set up historical candles with proper datetime index for legacy functions
        hist_candles = historical_candles.set_index('timestamp')
        hist_candles.index = pd.to_datetime(hist_candles.index)
        
        # Use ACTUAL legacy function: compute_realtime_macd()
        print("   Computing legacy MACD...")
        legacy_macd = compute_realtime_macd(
            trades_df=trades_df,
            historical_candles=hist_candles,
            se=macd_short,
            le=macd_long,
            signal_period=macd_signal,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='15min'
        )
        print(f"   ✅ Legacy MACD computed: {legacy_macd.shape}")
        
        # Use ACTUAL legacy function: compute_realtime_atr()
        print("   Computing legacy ATR...")
        legacy_atr = compute_realtime_atr(
            trades_df=trades_df,
            historical_candles=hist_candles,
            atr_period=atr_period,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='15min'
        )
        print(f"   ✅ Legacy ATR computed: {legacy_atr.shape}")
        
        # Create swing points
        print("   Computing swing points...")
        swing_points = detect_swing_points(hist_candles)
        print(f"   ✅ Swing points computed: {swing_points.shape}")
        
        # Start with historical candles as base
        result_data = historical_candles.copy()
        
        # Convert legacy results to candle periods
        legacy_macd['period'] = pd.to_datetime(legacy_macd['datetime']).dt.floor('15min')
        legacy_atr['period'] = pd.to_datetime(legacy_atr['datetime']).dt.floor('15min')
        
        # Take last value in each period (most recent for that candle)
        macd_candle = legacy_macd.groupby('period')[['macd', 'signal', 'hist']].last().reset_index()
        atr_candle = legacy_atr.groupby('period')['atr'].last().reset_index()
        
        # Merge with result_data
        result_data = result_data.merge(macd_candle, left_on='timestamp', right_on='period', how='left')
        result_data = result_data.merge(atr_candle, left_on='timestamp', right_on='period', how='left')
        
        # Add swing points data
        result_data = result_data.merge(swing_points.reset_index(), left_on='timestamp', right_on='timestamp', how='left')
        
        # Clean up merge columns
        result_data = result_data.drop(columns=['period_x', 'period_y'], errors='ignore')
        
        # Rename columns to match expected combo format
        column_renames = {
            'macd': 'macd_line',
            'signal': 'macd_signal', 
            'hist': 'macd_histogram'
        }
        result_data = result_data.rename(columns=column_renames)
        
        # Add combo metadata
        result_data['combo_id'] = combo_id
        result_data['contract'] = combo['contract']
        result_data['macd_short'] = macd_short
        result_data['macd_long'] = macd_long
        result_data['macd_signal_period'] = macd_signal
        result_data['atr_period'] = atr_period
        
        processing_time = time.time() - start_time
        
        # Save combo file
        combo_file = output_dir / f"legacy_combo_{combo_id:03d}.parquet"
        result_data.to_parquet(combo_file, index=False)
        
        print(f"   ✅ Saved combo {combo_id} in {processing_time:.2f}s: {combo_file}")
        print(f"   📊 Result shape: {result_data.shape}")
        
        return True, processing_time, result_data.shape
        
    except Exception as e:
        print(f"   ❌ Error creating combo {combo_id}: {e}")
        import traceback
        traceback.print_exc()
        return False, 0, (0, 0)

def main():
    """Test legacy combo creation with 5 combos"""
    print("🧪 TEST LEGACY COMBO CREATION")
    print("=" * 50)
    print("Creating 5 test combo files using ACTUAL legacy functions")
    
    # Setup output directory
    output_dir = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/test_legacy")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    start_time = time.time()
    
    # Load legacy data
    trades_df, historical_candles = load_legacy_data()
    
    # Create test combinations
    combinations = create_test_combos()
    
    # Create combo files
    print(f"\n🔧 Creating {len(combinations)} combo files with legacy functions...")
    
    successful = 0
    total_processing_time = 0
    
    for combo in combinations:
        success, proc_time, shape = create_one_combo_with_legacy(
            trades_df, historical_candles, combo, output_dir)
            
        if success:
            successful += 1
            total_processing_time += proc_time
    
    total_time = time.time() - start_time
    
    print(f"\n📊 TEST RESULTS:")
    print(f"   Total time: {total_time:.2f}s")
    print(f"   Successful combos: {successful}/{len(combinations)}")
    print(f"   Average processing time: {total_processing_time/successful:.2f}s" if successful > 0 else "   No successful combos")
    print(f"   Output directory: {output_dir}")
    
    if successful > 0:
        print(f"\n✅ SUCCESS: Created {successful} test combo files using actual legacy functions!")
        print(f"📂 Files saved to: {output_dir}")
    else:
        print(f"\n❌ FAILED: No combo files created successfully")
    
    return successful > 0

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🎊 Test completed successfully!")
    else:
        print(f"\n💥 Test failed")