#!/usr/bin/env python3
"""
Legacy Function Verification Test
Ensures we're testing against the exact legacy functions referenced in fix handoffs
"""

import sys
from pathlib import Path
import inspect

# Add source paths
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))

def verify_legacy_functions():
    """Verify the legacy functions exist and match fix handoff references"""
    print("🔍 LEGACY FUNCTION VERIFICATION")
    print("=" * 50)
    
    try:
        import predictors_tools
        print("✅ predictors_tools module loaded successfully")
        
        # Check ATR function (should be compute_realtime_atr per ATR fix handoff)
        if hasattr(predictors_tools, 'compute_realtime_atr'):
            print("✅ compute_realtime_atr found - matches ATR fix handoff")
            atr_func = getattr(predictors_tools, 'compute_realtime_atr')
            print(f"   Function signature: {inspect.signature(atr_func)}")
        else:
            print("❌ compute_realtime_atr NOT FOUND - ATR fix handoff references this")
            
        # Check MACD function (should be compute_realtime_macd per MACD fix handoff)
        if hasattr(predictors_tools, 'compute_realtime_macd'):
            print("✅ compute_realtime_macd found - matches MACD fix handoff")
            macd_func = getattr(predictors_tools, 'compute_realtime_macd')
            print(f"   Function signature: {inspect.signature(macd_func)}")
        else:
            print("❌ compute_realtime_macd NOT FOUND - MACD fix handoff references this")
            
        # Check Swing Points function (should be detect_swing_points per Swing fix handoff)
        if hasattr(predictors_tools, 'detect_swing_points'):
            print("✅ detect_swing_points found - matches Swing Points fix handoff")
            swing_func = getattr(predictors_tools, 'detect_swing_points')
            print(f"   Function signature: {inspect.signature(swing_func)}")
        else:
            print("❌ detect_swing_points NOT FOUND - Swing Points fix handoff references this")
            
        # Also check for the wrong functions that previous tests might have used
        print("\n🔍 Checking for commonly confused functions:")
        
        if hasattr(predictors_tools, 'compute_atr'):
            print("⚠️  compute_atr found - this is NOT the function ATR fix uses (wrong one)")
        else:
            print("✅ compute_atr not found - good, ATR fix uses compute_realtime_atr instead")
            
        # List all available functions for reference
        print(f"\n📋 All available functions in predictors_tools:")
        functions = [name for name in dir(predictors_tools) if callable(getattr(predictors_tools, name)) and not name.startswith('_')]
        for func_name in sorted(functions)[:10]:  # Show first 10
            print(f"   - {func_name}")
        if len(functions) > 10:
            print(f"   ... and {len(functions) - 10} more functions")
            
    except ImportError as e:
        print(f"❌ Could not import predictors_tools: {e}")
        print("   This means legacy comparison testing is not possible")
        
    print("\n✅ Legacy function verification complete")

if __name__ == "__main__":
    verify_legacy_functions()