"""
Cleanup and Create Single Metadata
- Remove all JSON metadata files from data/ folder
- Create single metadata parquet file at root level
"""

import pandas as pd
import json
from pathlib import Path
import glob

def cleanup_and_create_metadata():
    """Clean up JSON files and create single metadata parquet"""
    print("🧹 CLEANING UP METADATA STRUCTURE")
    print("=" * 50)
    
    # Paths
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    data_dir = Path(f"{output_base}/data")
    
    print(f"📁 Working with:")
    print(f"   Data folder: {data_dir}")
    print(f"   Root folder: {output_base}")
    
    try:
        # Find all JSON metadata files in data/ folder
        json_files = list(data_dir.glob("*_metadata.json"))
        print(f"\n🔍 Found {len(json_files)} JSON metadata files to process")
        
        if not json_files:
            print("❌ No JSON metadata files found")
            return False
        
        # Read all JSON metadata into a list
        metadata_records = []
        
        for json_file in sorted(json_files):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    
                # Extract relevant metadata into flat structure
                metadata_record = {
                    'combo_id': data.get('combo_id', 0),
                    'processing_time_seconds': data.get('processing_time_seconds', 0),
                    'worker_id': data.get('worker_id', ''),
                    'result_shape_rows': data.get('result_shape', [0, 0])[0] if data.get('result_shape') else 0,
                    'result_shape_cols': data.get('result_shape', [0, 0])[1] if data.get('result_shape') else 0,
                    'features_computed': data.get('result_shape', [0, 6])[1] - 6 if data.get('result_shape') else 0,  # Subtract original 6 columns
                    'memory_peak_gb': data.get('combination_parameters', {}).get('memory_stats', {}).get('peak_memory_gb', 0),
                    'contract': data.get('combination_parameters', {}).get('contract', 'dem07_25'),
                    'date_range_start': data.get('combination_parameters', {}).get('date_range', {}).get('start', '2025-04-01'),
                    'date_range_end': data.get('combination_parameters', {}).get('date_range', {}).get('end', '2025-06-30'),
                    'macd_short': data.get('combination_parameters', {}).get('macd_params', {}).get('short', 12),
                    'macd_long': data.get('combination_parameters', {}).get('macd_params', {}).get('long', 26),
                    'macd_signal': data.get('combination_parameters', {}).get('macd_params', {}).get('signal', 9),
                    'atr_lookback': data.get('combination_parameters', {}).get('atr_lookback', 21),
                    'bias_macd_line_lower': data.get('combination_parameters', {}).get('bias_thresholds', {}).get('macd_line_lower', -2.5),
                    'bias_macd_line_upper': data.get('combination_parameters', {}).get('bias_thresholds', {}).get('macd_line_upper', 2.5),
                    'bias_macd_hist_lower': data.get('combination_parameters', {}).get('bias_thresholds', {}).get('macd_histogram_lower', -1.25),
                    'bias_macd_hist_upper': data.get('combination_parameters', {}).get('bias_thresholds', {}).get('macd_histogram_upper', 1.25),
                    'strategy_neutral_buy': data.get('combination_parameters', {}).get('strategy_thresholds', {}).get('neutral_buy', 0.2),
                    'strategy_neutral_sell': data.get('combination_parameters', {}).get('strategy_thresholds', {}).get('neutral_sell', 0.7),
                    'stop_loss': data.get('combination_parameters', {}).get('stop_loss', 0.5),
                    'sl_tp_ratio': data.get('combination_parameters', {}).get('sl_tp_ratio', 1.5),
                    'tp_value': data.get('combination_parameters', {}).get('tp_value', 0.75),
                    'legacy_data_source': data.get('legacy_data_source', 'dem07_25_tr_ba_data.parquet')
                }
                
                metadata_records.append(metadata_record)
                
            except Exception as e:
                print(f"⚠️  Error reading {json_file.name}: {e}")
                continue
        
        print(f"✅ Successfully read {len(metadata_records)} metadata records")
        
        # Create DataFrame and save as parquet
        if metadata_records:
            metadata_df = pd.DataFrame(metadata_records)
            metadata_df = metadata_df.sort_values('combo_id').reset_index(drop=True)
            
            # Save single metadata parquet at root level
            metadata_file = Path(output_base) / "combinations_metadata.parquet"
            metadata_df.to_parquet(metadata_file, index=False)
            
            print(f"\n💾 Created single metadata parquet:")
            print(f"   File: {metadata_file}")
            print(f"   Records: {len(metadata_df)}")
            print(f"   Columns: {len(metadata_df.columns)}")
            
            # Show sample of metadata
            print(f"\n📋 Sample Metadata:")
            sample_cols = ['combo_id', 'processing_time_seconds', 'features_computed', 'macd_short', 'macd_long', 'atr_lookback']
            print(metadata_df[sample_cols].head(3).to_string(index=False))
        
        # Remove all JSON metadata files from data/ folder
        print(f"\n🗑️  Removing {len(json_files)} JSON files from data/ folder...")
        
        removed_count = 0
        for json_file in json_files:
            try:
                json_file.unlink()
                removed_count += 1
            except Exception as e:
                print(f"⚠️  Error removing {json_file.name}: {e}")
        
        print(f"✅ Removed {removed_count} JSON metadata files")
        
        # Also remove any leftover combo_XXXXXX.parquet files (from old async system)
        old_combo_files = list(data_dir.glob("combo_[0-9][0-9][0-9][0-9][0-9][0-9].parquet"))
        if old_combo_files:
            print(f"\n🗑️  Removing {len(old_combo_files)} old format combo files...")
            for old_file in old_combo_files:
                try:
                    old_file.unlink()
                    removed_count += 1
                except Exception as e:
                    print(f"⚠️  Error removing {old_file.name}: {e}")
        
        # Verify final structure
        print(f"\n🔍 FINAL STRUCTURE VERIFICATION:")
        
        # Count combo files
        combo_files = list(data_dir.glob("combo_[0-9][0-9][0-9].parquet"))
        json_files_remaining = list(data_dir.glob("*.json"))
        
        print(f"   📊 data/ folder:")
        print(f"     - Combo files (combo_XXX.parquet): {len(combo_files)}")
        print(f"     - JSON files remaining: {len(json_files_remaining)}")
        
        print(f"   📊 Root level:")
        metadata_exists = (Path(output_base) / "combinations_metadata.parquet").exists()
        print(f"     - combinations_metadata.parquet: {'✅ EXISTS' if metadata_exists else '❌ MISSING'}")
        
        if len(json_files_remaining) == 0 and metadata_exists:
            print(f"\n🎉 SUCCESS! Clean structure achieved:")
            print(f"   📁 {output_base}/")
            print(f"   ├── data/")
            print(f"   │   ├── combo_000.parquet")
            print(f"   │   ├── combo_001.parquet") 
            print(f"   │   └── ... ({len(combo_files)} combo files)")
            print(f"   └── combinations_metadata.parquet")
            return True
        else:
            print(f"\n⚠️  Structure not fully clean:")
            if json_files_remaining:
                print(f"     - {len(json_files_remaining)} JSON files still in data/")
            if not metadata_exists:
                print(f"     - combinations_metadata.parquet missing")
            return False
        
    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = cleanup_and_create_metadata()
    
    if success:
        print(f"\n🎊 CLEANUP COMPLETE! Proper metadata structure created.")
    else:
        print(f"\n💥 Cleanup failed or incomplete")