#!/usr/bin/env python3
"""
Simple runner script for the comprehensive parameter combinations test.

Usage:
    python sandbox/experiments/run_combinations_test.py

This script demonstrates the corrected Phase 2 GPU pipeline processing 
real market data through 1,250 parameter combinations.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def main():
    print("🚀 Starting Comprehensive Parameter Combinations Test")
    print("=" * 60)
    
    try:
        # Import and run the comprehensive test
        from sandbox.experiments.comprehensive_parameter_combinations_test import run_comprehensive_test
        
        print("📋 Test Configuration:")
        print("   • Total parameter combinations: 1,250")
        print("   • Candle granularities: [5, 10, 15, 20, 25] minutes")
        print("   • ATR periods: [14, 21]")
        print("   • MACD se: [8, 9, 10, 11, 12]")
        print("   • MACD le: [16, 20, 26, 32, 38]")
        print("   • MACD signal: [6, 9, 12, 15, 18]")
        print("   • Output: C:\\Users\\krajcovic\\Documents\\Testing Data\\ATS_3_data\\interim_test")
        print()
        print("🔧 Running test with first 50 combinations (demo mode)...")
        print("   (Edit comprehensive_parameter_combinations_test.py to run all 1,250)")
        print()
        
        # Run the test
        results, summary = run_comprehensive_test()
        
        if summary['results_summary']['success_rate_percent'] > 90:
            print("\n🎉 Test completed successfully!")
            return True
        else:
            print("\n⚠️  Test completed with some failures.")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure you're running from the project root directory.")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)