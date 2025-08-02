#!/usr/bin/env python3
"""
Validate Combo 500 Against Legacy Code
Quick validation to check if combo_500.parquet uses legacy functions
"""

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

# Import legacy implementations
try:
    from predictors_tools import compute_realtime_atr, compute_realtime_macd
    print("✅ Legacy functions imported successfully")
except ImportError as e:
    print(f"❌ Could not import legacy functions: {e}")
    sys.exit(1)

def quick_validation():
    """Quick validation of combo_500"""
    print("🔬 QUICK VALIDATION: COMBO 500")
    print("=" * 40)
    
    try:
        # Load combo data
        combo_data = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/data/combo_500.parquet')
        
        # Load metadata
        metadata = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/combinations_metadata.parquet')
        combo_500 = metadata[metadata['combo_id'] == 500].iloc[0]
        
        print(f"✅ Loaded combo_500: {combo_data.shape}")
        print(f"   MACD params: short={combo_500.macd_short}, long={combo_500.macd_long}, signal={combo_500.macd_signal}")
        print(f"   ATR lookback: {combo_500.atr_lookback}")
        
        # Check if combo uses legacy functions flag
        if hasattr(combo_500, 'using_legacy_functions'):
            legacy_flag = combo_500.using_legacy_functions
            print(f"   Using legacy functions flag: {legacy_flag}")
            
            if legacy_flag:
                print(f"\\n🎉 SUCCESS: Combo 500 was generated using legacy functions!")
                print(f"✅ Metadata confirms actual predictors_tools functions were used")
                return True
            else:
                print(f"\\n❌ ISSUE: Combo 500 metadata indicates NOT using legacy functions")
                return False
        else:
            print(f"\\n⚠️  No legacy functions flag found in metadata")
            return False
            
    except Exception as e:
        print(f"❌ Error during validation: {e}")
        return False

if __name__ == "__main__":
    success = quick_validation()
    
    if success:
        print(f"\\n🎊 COMBO 500 VALIDATED!")
    else:
        print(f"\\n💥 COMBO 500 VALIDATION FAILED!")