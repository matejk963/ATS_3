"""
Validation script for Phase 1.1.3 completion.

Run this script to verify that Phase 1.1.3 is properly implemented.
"""

import sys
import time
from pathlib import Path

def validate_phase_1_1_3():
    """Validate Phase 1.1.3 implementation."""
    print("🔍 Validating Phase 1.1.3: Complete Parameter Generation...")
    
    success = True
    
    # Check dependencies (Phases 1.1.1 and 1.1.2)
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_symmetric_pairs, frange, 
            generate_bias_threshold_combinations,
            generate_strategy_threshold_combinations
        )
        print("✅ Phase 1.1.1 and 1.1.2 dependencies available")
    except ImportError as e:
        print(f"❌ Dependency missing: {e}")
        success = False
    
    # Check new Phase 1.1.3 imports
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_all_parameter_combinations,
            generate_combination_batch,
            get_combination_sample,
            validate_complete_combination,
            export_combinations_to_file
        )
        print("✅ Phase 1.1.3 functions available")
    except ImportError as e:
        print(f"❌ Phase 1.1.3 import error: {e}")
        success = False
    
    # Test sample generation
    try:
        print("\n🧪 Testing sample generation...")
        samples = get_combination_sample(5)
        
        if len(samples) != 5:
            print(f"❌ Expected 5 samples, got {len(samples)}")
            success = False
        else:
            print(f"✅ Generated {len(samples)} sample combinations")
        
        # Validate sample structure
        for i, combo in enumerate(samples):
            if not validate_complete_combination(combo):
                print(f"❌ Sample {i} failed validation")
                success = False
            else:
                print(f"✅ Sample {i} validation passed")
                
    except Exception as e:
        print(f"❌ Sample generation error: {e}")
        success = False
    
    # Test batch generation
    try:
        print("\n📦 Testing batch generation...")
        batch = generate_combination_batch(0, 20)
        
        if len(batch) == 0:
            print("❌ Batch generation returned empty result")
            success = False
        else:
            print(f"✅ Generated batch with {len(batch)} combinations")
        
        # Check combo_id sequence
        for i, combo in enumerate(batch):
            if combo['combo_id'] != i:
                print(f"❌ Combo ID mismatch: expected {i}, got {combo['combo_id']}")
                success = False
                break
        else:
            print("✅ Combo ID sequence correct")
            
    except Exception as e:
        print(f"❌ Batch generation error: {e}")
        success = False
    
    # Test combination validation
    try:
        print("\n🔍 Testing combination validation...")
        
        test_combo = samples[0] if samples else {}
        
        if validate_complete_combination(test_combo):
            print("✅ Valid combination passed validation")
        else:
            print("❌ Valid combination failed validation")
            success = False
        
        # Test invalid combination
        invalid_combo = test_combo.copy() if test_combo else {}
        if invalid_combo:
            invalid_combo['combo_id'] = "invalid_type"
            
            if not validate_complete_combination(invalid_combo):
                print("✅ Invalid combination correctly rejected")
            else:
                print("❌ Invalid combination incorrectly accepted")
                success = False
                
    except Exception as e:
        print(f"❌ Validation testing error: {e}")
        success = False
    
    # Test export functionality
    try:
        print("\n💾 Testing export functionality...")
        
        if samples:
            test_file = "test_combinations_validation.json"
            export_success = export_combinations_to_file(samples, test_file)
            
            if export_success:
                print("✅ Export successful")
                
                # Verify file exists and has content
                export_path = Path(test_file)
                if export_path.exists():
                    file_size = export_path.stat().st_size
                    print(f"✅ Export file created: {file_size} bytes")
                    
                    # Clean up
                    export_path.unlink()
                else:
                    print("❌ Export file not created")
                    success = False
            else:
                print("❌ Export failed")
                success = False
                
    except Exception as e:
        print(f"❌ Export testing error: {e}")
        success = False
    
    # Performance test
    try:
        print("\n⚡ Performance testing...")
        
        start_time = time.time()
        perf_batch = generate_combination_batch(0, 50)
        generation_time = time.time() - start_time
        
        if generation_time > 0:
            rate = len(perf_batch) / generation_time
            print(f"✅ Generated {len(perf_batch)} combinations in {generation_time:.2f}s")
            print(f"📈 Rate: {rate:.1f} combinations/second")
            
            if rate < 10:  # Should be able to generate at least 10 combinations/second
                print("⚠️  Performance warning: generation rate is low")
            else:
                print("✅ Performance acceptable")
        else:
            print("⚠️  Performance test too fast to measure")
            
    except Exception as e:
        print(f"❌ Performance testing error: {e}")
        success = False
    
    # Check test files exist
    test_files = [
        Path("tests/test_complete_parameter_generation.py"),
        Path("tests/test_parameter_generation_performance.py")
    ]
    
    for test_file in test_files:
        if test_file.exists():
            print(f"✅ Test file exists: {test_file}")
        else:
            print(f"❌ Missing test file: {test_file}")
            success = False
    
    # Run tests
    try:
        print("\n🧪 Running integration tests...")
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_complete_parameter_generation.py", 
            "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All integration tests passed")
        else:
            print(f"❌ Integration tests failed:\n{result.stdout}\n{result.stderr}")
            success = False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        success = False
    
    if success:
        print("\n🎉 Phase 1.1.3 validation PASSED!")
        print("✅ Complete parameter generation system is ready")
        print("🚀 Ready to proceed to Phase 1.1.4: Contract Data Manager Foundation")
        return True
    else:
        print("\n❌ Phase 1.1.3 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    validate_phase_1_1_3()