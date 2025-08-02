"""
Validation script for Phase 1.1.2 completion.

Run this script to verify that Phase 1.1.2 is properly implemented.
"""

import sys
from pathlib import Path

def validate_phase_1_1_2():
    """Validate Phase 1.1.2 implementation."""
    print("🔍 Validating Phase 1.1.2: Parameter Combination Logic...")
    
    success = True
    
    # Check dependencies (Phase 1.1.1)
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_symmetric_pairs, frange, get_basic_parameter_info
        )
        print("✅ Phase 1.1.1 dependencies available")
    except ImportError as e:
        print(f"❌ Phase 1.1.1 dependency missing: {e}")
        success = False
    
    # Check new imports
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_bias_threshold_combinations,
            generate_strategy_threshold_combinations,
            validate_bias_thresholds,
            validate_strategy_thresholds,
            get_combination_counts
        )
        print("✅ Phase 1.1.2 functions available")
    except ImportError as e:
        print(f"❌ Phase 1.1.2 import error: {e}")
        success = False
    
    # Test combination generation
    try:
        bias_combos = generate_bias_threshold_combinations()
        strategy_combos = generate_strategy_threshold_combinations()
        counts = get_combination_counts()
        
        print(f"✅ Generated {len(bias_combos)} bias combinations")
        print(f"✅ Generated {len(strategy_combos)} strategy combinations") 
        print(f"✅ Estimated {counts['total_combinations_estimate']:,} total combinations")
        
        # Check combination counts match expectations
        if len(bias_combos) != counts['bias_combinations']:
            print(f"❌ Bias combination count mismatch: {len(bias_combos)} vs {counts['bias_combinations']}")
            success = False
        
        if len(strategy_combos) != counts['strategy_combinations']:
            print(f"❌ Strategy combination count mismatch: {len(strategy_combos)} vs {counts['strategy_combinations']}")
            success = False
            
    except Exception as e:
        print(f"❌ Combination generation error: {e}")
        success = False
    
    # Test validation functions
    try:
        # Test with valid combinations
        valid_bias = {
            'macd_line_lower': -2.0,
            'macd_line_upper': 2.0,
            'macd_histogram_lower': -1.0,
            'macd_histogram_upper': 1.0
        }
        
        valid_strategy = {
            'neutral_buy': 0.3,
            'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0,
            'strong_bullish_buy_adjust': 0.1,
            'bearish_buy_adjust': -0.05,
            'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1,
            'bullish_sell_adjust': 0.15
        }
        
        if not validate_bias_thresholds(valid_bias):
            print("❌ Valid bias threshold rejected")
            success = False
        
        if not validate_strategy_thresholds(valid_strategy):
            print("❌ Valid strategy threshold rejected")
            success = False
            
        print("✅ Validation functions working correctly")
        
    except Exception as e:
        print(f"❌ Validation function error: {e}")
        success = False
    
    # Check file exists
    test_file = Path("tests/test_parameter_combination_logic.py")
    if not test_file.exists():
        print(f"❌ Missing test file: {test_file}")
        success = False
    else:
        print(f"✅ Test file exists: {test_file}")
    
    # Run tests
    try:
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_parameter_combination_logic.py", 
            "-v"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All tests passed")
        else:
            print(f"❌ Tests failed:\n{result.stdout}\n{result.stderr}")
            success = False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        success = False
    
    if success:
        print("\n🎉 Phase 1.1.2 validation PASSED!")
        print("Ready to proceed to Phase 1.1.3: Complete Parameter Generation")
        return True
    else:
        print("\n❌ Phase 1.1.2 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    validate_phase_1_1_2()