"""
Final validation script for Phase 1.1.6 and complete Phase 1.1 system.

Run this script to verify that the entire Phase 1.1 system is ready.
"""

import sys
import tempfile
import pandas as pd
from pathlib import Path

def validate_phase_1_1_6_and_complete_system():
    """Validate Phase 1.1.6 and the complete Phase 1.1 system."""
    print("🔍 Validating Phase 1.1.6: Integration and Polish...")
    print("🎯 Final validation of complete Phase 1.1 system...")
    
    success = True
    
    # Check all dependencies (Phases 1.1.1 through 1.1.5)
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_all_parameter_combinations,
            generate_combination_batch,
            get_combination_sample,
            validate_complete_combination,
            get_combination_counts
        )
        from src.gpu_parallel_processing.contract_data_manager import (
            ContractDataManager,
            ValidationResult
        )
        from src.gpu_parallel_processing.integration import (
            Phase1Integration,
            IntegrationValidator
        )
        print("✅ All Phase 1.1 components available")
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        success = False
        return False
    
    # Test integration initialization
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            integration = Phase1Integration(temp_dir)
            print("✅ Integration system initialization successful")
    except Exception as e:
        print(f"❌ Integration initialization failed: {e}")
        success = False
    
    # Test system overview
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            integration = Phase1Integration(temp_dir)
            overview = integration.get_system_overview()
            
            required_keys = ['system_version', 'components', 'parameter_capabilities', 
                           'data_capabilities', 'processing_stats']
            for key in required_keys:
                if key not in overview:
                    print(f"❌ Missing overview key: {key}")
                    success = False
            
            if success:
                print("✅ System overview generation working")
                print(f"   📊 System version: {overview['system_version']}")
                print(f"   🔢 Total combinations: {overview['parameter_capabilities']['total_combinations_estimate']:,}")
        
    except Exception as e:
        print(f"❌ System overview failed: {e}")
        success = False
    
    # Test system validation
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            integration = Phase1Integration(temp_dir)
            validation = integration.validate_system_readiness()
            
            if hasattr(validation, 'is_valid') and hasattr(validation, 'validation_details'):
                print("✅ System validation working")
                print(f"   🔍 Validation status: {'READY' if validation.is_valid else 'NOT READY'}")
                if validation.warnings:
                    print(f"   ⚠️  Warnings: {len(validation.warnings)}")
            else:
                print("❌ Invalid validation result structure")
                success = False
        
    except Exception as e:
        print(f"❌ System validation failed: {e}")
        success = False
    
    # Test integration validator
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            test_results = IntegrationValidator.run_integration_tests(temp_dir)
            
            required_test_keys = ['tests_run', 'tests_passed', 'tests_failed', 'test_details']
            for key in required_test_keys:
                if key not in test_results:
                    print(f"❌ Missing test result key: {key}")
                    success = False
            
            if success and test_results['tests_run'] > 0:
                print("✅ Integration validator working")
                print(f"   🧪 Tests: {test_results['tests_passed']}/{test_results['tests_run']} passed")
                
                # Check specific tests
                test_names = [test['test'] for test in test_results['test_details']]
                expected_tests = ['System Initialization', 'System Readiness', 'Parameter Generation']
                
                for expected_test in expected_tests:
                    if expected_test not in test_names:
                        print(f"❌ Missing expected test: {expected_test}")
                        success = False
            else:
                print("❌ No integration tests run")
                success = False
        
    except Exception as e:
        print(f"❌ Integration validator failed: {e}")
        success = False
    
    # Test system report generation
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = IntegrationValidator.generate_system_report(temp_dir)
            
            if isinstance(report, str) and len(report) > 0:
                print("✅ System report generation working")
                print(f"   📄 Report length: {len(report)} characters")
                
                # Check for key sections
                required_sections = ["System Overview", "Parameter Generation Capabilities", 
                                   "Data Management Capabilities", "Integration Tests"]
                for section in required_sections:
                    if section not in report:
                        print(f"❌ Missing report section: {section}")
                        success = False
            else:
                print("❌ Invalid report generated")
                success = False
        
    except Exception as e:
        print(f"❌ System report generation failed: {e}")
        success = False
    
    # Test with actual contract data (if available)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test contract data
            test_data = pd.DataFrame({
                'open': [100.0 + i * 0.01 for i in range(100)],
                'high': [105.0 + i * 0.01 for i in range(100)],
                'low': [95.0 + i * 0.01 for i in range(100)],
                'close': [103.0 + i * 0.01 for i in range(100)],
                'volume': [1000 + i for i in range(100)]
            })
            
            contract_file = Path(temp_dir) / "validation_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Test full workflow
            integration = Phase1Integration(temp_dir)
            workflow_result = integration.process_sample_workflow(
                sample_size=3,
                target_contracts=["validation_test"]
            )
            
            if workflow_result['success']:
                print("✅ Full workflow with real data working")
                print(f"   📊 Processed: {workflow_result['combinations_processed']} combinations")
                print(f"   ⏱️  Time: {workflow_result['workflow_time']:.2f}s")
            else:
                print(f"❌ Workflow failed: {workflow_result.get('error', 'Unknown error')}")
                success = False
        
    except Exception as e:
        print(f"❌ Full workflow test failed: {e}")
        success = False
    
    # Test component integration
    try:
        # Test that parameter generation works with data management
        combinations = get_combination_sample(3)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Both components should work together
            if len(combinations) == 3 and manager.max_cached_contracts >= 0:
                print("✅ Component integration working")
            else:
                print("❌ Component integration failed")
                success = False
        
    except Exception as e:
        print(f"❌ Component integration test failed: {e}")
        success = False
    
    # Check all test files exist
    test_files = [
        Path("tests/test_parameter_combinations_basic.py"),
        Path("tests/test_parameter_combination_logic.py"), 
        Path("tests/test_complete_parameter_generation.py"),
        Path("tests/test_contract_data_manager_foundation.py"),
        Path("tests/test_contract_data_manager_cache.py"),
        Path("tests/test_phase1_integration.py")
    ]
    
    missing_tests = []
    for test_file in test_files:
        if test_file.exists():
            print(f"✅ Test file exists: {test_file.name}")
        else:
            print(f"❌ Missing test file: {test_file}")
            missing_tests.append(test_file)
            success = False
    
    # Run final integration tests
    try:
        print("\n🧪 Running final integration tests...")
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_phase1_integration.py", 
            "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All final integration tests passed")
        else:
            print(f"❌ Final integration tests failed:\n{result.stdout}\n{result.stderr}")
            success = False
    except Exception as e:
        print(f"❌ Error running final tests: {e}")
        success = False
    
    # Generate final system report
    try:
        print("\n📄 Generating final system report...")
        with tempfile.TemporaryDirectory() as temp_dir:
            report = IntegrationValidator.generate_system_report(temp_dir)
            
            # Save report to file
            report_file = Path("PHASE_1_1_SYSTEM_REPORT.md")
            report_file.write_text(report)
            print(f"✅ System report saved to: {report_file}")
        
    except Exception as e:
        print(f"❌ Error generating final report: {e}")
        success = False
    
    # Final summary
    if success:
        print("\n" + "="*60)
        print("🎉 PHASE 1.1 COMPLETE SYSTEM VALIDATION PASSED!")
        print("="*60)
        print("✅ Phase 1.1.1: Basic Parameter Infrastructure - READY")
        print("✅ Phase 1.1.2: Parameter Combination Logic - READY") 
        print("✅ Phase 1.1.3: Complete Parameter Generation - READY")
        print("✅ Phase 1.1.4: Contract Data Manager Foundation - READY")
        print("✅ Phase 1.1.5: Cache Implementation - READY")
        print("✅ Phase 1.1.6: Integration and Polish - READY")
        print("\n🚀 System Capabilities:")
        print("   📊 ~115,200 parameter combinations")
        print("   💾 LRU-cached contract data management")
        print("   🔍 Comprehensive validation and testing")
        print("   📈 Performance monitoring and optimization")
        print("   🧪 Full integration testing suite")
        print("\n🎯 Ready to proceed to Phase 1.2: GPU Processing Core")
        return True
    else:
        print("\n" + "="*60)
        print("❌ PHASE 1.1 SYSTEM VALIDATION FAILED!")
        print("="*60)
        print("Please fix the issues above before proceeding.")
        if missing_tests:
            print(f"\n📝 Missing test files: {len(missing_tests)}")
            for test_file in missing_tests:
                print(f"   - {test_file}")
        print("\n🔧 Use the individual phase validation scripts to debug specific issues:")
        print("   - validate_phase_1_1_1.py")
        print("   - validate_phase_1_1_2.py") 
        print("   - validate_phase_1_1_3.py")
        print("   - validate_phase_1_1_4.py")
        print("   - validate_phase_1_1_5.py")
        return False

if __name__ == "__main__":
    validate_phase_1_1_6_and_complete_system()