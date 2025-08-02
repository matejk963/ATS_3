#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for beta injection scripts

This script tests the import and basic functionality of the beta injection scripts
to ensure they work correctly before running the full injection process.
"""

import sys
import traceback

def test_import(module_name, file_path):
    """Test if a module can be imported successfully."""
    try:
        print(f"Testing import of {module_name}...")
        
        # Add the directory to sys.path if needed
        import os
        script_dir = os.path.dirname(file_path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        
        # Try to import the module
        spec = None
        if module_name == "swing_points_inject_beta":
            import prefect_data_orchestrator.datamart_inject.swing_points_inject as module
        elif module_name == "macd_inject_beta":
            import prefect_data_orchestrator.datamart_inject.macd_inject as module
        elif module_name == "atr_inject_beta":
            import prefect_data_orchestrator.datamart_inject.atr_inject as module
        else:
            raise ValueError(f"Unknown module: {module_name}")
        
        # Test if required functions exist
        if hasattr(module, 'check_existing_predictors_and_entries'):
            print(f"  ✅ check_existing_predictors_and_entries function found")
        else:
            print(f"  ❌ check_existing_predictors_and_entries function missing")
            
        if hasattr(module, 'generate_all_predictor_names'):
            print(f"  ✅ generate_all_predictor_names function found")
        else:
            print(f"  ❌ generate_all_predictor_names function missing")
            
        if hasattr(module, 'main'):
            print(f"  ✅ main function found")
        else:
            print(f"  ❌ main function missing")
        
        print(f"  ✅ {module_name} imported successfully\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Failed to import {module_name}: {e}")
        print(f"  Traceback: {traceback.format_exc()}\n")
        return False

def test_predictor_name_generation():
    """Test the predictor name generation functions."""
    print("Testing predictor name generation...")
    
    try:
        # Test data
        contract_periods_map = {
            'M': ['dem1', 'dem2'],
            'Q': ['deq1', 'deq2']
        }
        candle_granularities = ['5min', '1h']
        
        # Test swing points
        import prefect_data_orchestrator.datamart_inject.swing_points_inject as swing_points_inject
        swing_names = swing_points_inject.generate_all_predictor_names(
            contract_periods_map, candle_granularities
        )
        print(f"  ✅ Swing points generated {len(swing_names)} predictor names")
        print(f"    Examples: {list(swing_names)[:3]}...")
        
        # Test MACD
        import prefect_data_orchestrator.datamart_inject.macd_inject as macd_inject
        macd_params = [(12, 26, 9)]
        macd_names = macd_inject.generate_all_predictor_names(
            contract_periods_map, candle_granularities, macd_params
        )
        print(f"  ✅ MACD generated {len(macd_names)} predictor names")
        print(f"    Examples: {list(macd_names)[:3]}...")
        
        # Test ATR
        import prefect_data_orchestrator.datamart_inject.atr_inject as atr_inject
        atr_lookbacks = [21]
        atr_names = atr_inject.generate_all_predictor_names(
            contract_periods_map, candle_granularities, atr_lookbacks
        )
        print(f"  ✅ ATR generated {len(atr_names)} predictor names")
        print(f"    Examples: {list(atr_names)[:3]}...")
        
        print("  ✅ All predictor name generation tests passed\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Predictor name generation test failed: {e}")
        print(f"  Traceback: {traceback.format_exc()}\n")
        return False

def main():
    """Main test function."""
    print("🧪 Testing beta injection scripts...\n")
    
    # Test imports
    results = []
    
    scripts = [
        ("swing_points_inject_beta", "swing_points_inject_beta.py"),
        ("macd_inject_beta", "macd_inject_beta.py"),
        ("atr_inject_beta", "atr_inject_beta.py")
    ]
    
    for module_name, file_name in scripts:
        file_path = f"c:\\Users\\krajcovic\\Documents\\GitHub\\EnergyTrading\\Python\\prefect_data_orchestrator\\datamart_inject\\{file_name}"
        results.append(test_import(module_name, file_path))
    
    # Test predictor name generation if imports successful
    if all(results):
        results.append(test_predictor_name_generation())
    
    # Summary
    print("🏁 Test Summary:")
    print(f"  Scripts tested: {len(scripts)}")
    print(f"  Tests passed: {sum(results)}")
    print(f"  Tests failed: {len(results) - sum(results)}")
    
    if all(results):
        print("  🎉 All tests passed! Beta scripts are ready to use.")
    else:
        print("  ⚠️ Some tests failed. Please check the errors above.")

if __name__ == "__main__":
    main()
