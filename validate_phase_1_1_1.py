"""
Validation script for Phase 1.1.1 completion.

Run this script to verify that Phase 1.1.1 is properly implemented.
"""

import sys
from pathlib import Path


def validate_phase_1_1_1():
    """Validate Phase 1.1.1 implementation."""
    print("🔍 Validating Phase 1.1.1: Basic Parameter Infrastructure...")
    
    success = True
    
    # Check directory structure
    required_dirs = [
        Path("src/gpu_parallel_processing"),
        Path("tests")
    ]
    
    for dir_path in required_dirs:
        if not dir_path.exists():
            print(f"❌ Missing directory: {dir_path}")
            success = False
        else:
            print(f"✅ Directory exists: {dir_path}")
    
    # Check required files
    required_files = [
        Path("src/gpu_parallel_processing/__init__.py"),
        Path("src/gpu_parallel_processing/parameter_combinations.py"),
        Path("tests/test_parameter_combinations_basic.py")
    ]
    
    for file_path in required_files:
        if not file_path.exists():
            print(f"❌ Missing file: {file_path}")
            success = False
        else:
            print(f"✅ File exists: {file_path}")
    
    # Test imports
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_symmetric_pairs,
            frange,
            get_basic_parameter_info,
            BIAS_THRESHOLD_RANGES,
            NEUTRAL_STRATEGY_RANGES,
            BIAS_ADJUSTMENT_RANGES
        )
        print("✅ All imports successful")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        success = False
    
    # Test helper functions
    try:
        pairs = generate_symmetric_pairs(2.0, 0.5)
        assert len(pairs) == 4
        
        values = frange(0.1, 0.4, 0.1)
        assert len(values) == 3
        
        info = get_basic_parameter_info()
        assert isinstance(info, dict)
        
        # Test new parameter ranges
        assert len(BIAS_THRESHOLD_RANGES['macd_line_pairs']) == 5
        assert len(NEUTRAL_STRATEGY_RANGES['buy_values']) == 2
        assert len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_strong_bullish']) == 2
        
        print("✅ Helper functions and parameter ranges working correctly")
    except Exception as e:
        print(f"❌ Helper function error: {e}")
        success = False
    
    # Run tests
    try:
        import subprocess
        result = subprocess.run([
            sys.executable, "-c", 
            "import subprocess; subprocess.run(['pwsh', '-Command', 'pytest tests/test_parameter_combinations_basic.py -v'], check=True)"
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
        print("\n🎉 Phase 1.1.1 validation PASSED!")
        print("Ready to proceed to Phase 1.1.2: Parameter Combination Logic")
        return True
    else:
        print("\n❌ Phase 1.1.1 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False


if __name__ == "__main__":
    validate_phase_1_1_1()