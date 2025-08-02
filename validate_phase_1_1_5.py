"""
Validation script for Phase 1.1.5 completion.

Run this script to verify that Phase 1.1.5 is properly implemented.
"""

import sys
import tempfile
import pandas as pd
import time
from pathlib import Path

def validate_phase_1_1_5():
    """Validate Phase 1.1.5 implementation."""
    print("🔍 Validating Phase 1.1.5: Cache Implementation...")
    
    success = True
    
    # Check dependencies (Phase 1.1.4)
    try:
        from src.gpu_parallel_processing.contract_data_manager import ContractDataManager
        print("✅ Phase 1.1.4 dependencies available")
    except ImportError as e:
        print(f"❌ Dependency missing: {e}")
        success = False
        return False
    
    # Test cache initialization
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir, max_cached_contracts=2)
            
            # Check cache attributes
            if not hasattr(manager, 'data_cache'):
                print("❌ Missing data_cache attribute")
                success = False
            
            if not hasattr(manager, 'cache_hits'):
                print("❌ Missing cache_hits attribute")
                success = False
            
            if not hasattr(manager, 'cache_misses'):
                print("❌ Missing cache_misses attribute")
                success = False
            
            if manager.max_cached_contracts != 2:
                print(f"❌ Incorrect max_cached_contracts: expected 2, got {manager.max_cached_contracts}")
                success = False
            
            if success:
                print("✅ Cache initialization successful")
        
    except Exception as e:
        print(f"❌ Cache initialization failed: {e}")
        success = False
    
    # Test basic caching functionality
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir, max_cached_contracts=2)
            
            # Create test contract
            test_data = pd.DataFrame({
                'open': [100.0, 101.0, 102.0],
                'high': [105.0, 106.0, 107.0],
                'low': [95.0, 96.0, 97.0],
                'close': [103.0, 104.0, 105.0],
                'volume': [1000, 1100, 1200]
            })
            
            contract_file = Path(temp_dir) / "cache_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # First load (cache miss)
            data1 = manager.load_contract_data("cache_test")
            
            if manager.cache_misses != 1:
                print(f"❌ Expected 1 cache miss, got {manager.cache_misses}")
                success = False
            
            if manager.cache_hits != 0:
                print(f"❌ Expected 0 cache hits, got {manager.cache_hits}")
                success = False
            
            # Second load (cache hit)
            data2 = manager.load_contract_data("cache_test")
            
            if manager.cache_misses != 1:
                print(f"❌ Cache misses changed unexpectedly: {manager.cache_misses}")
                success = False
            
            if manager.cache_hits != 1:
                print(f"❌ Expected 1 cache hit, got {manager.cache_hits}")
                success = False
            
            # Data should be identical
            if not data1.equals(data2):
                print("❌ Cached data differs from original")
                success = False
            
            if success:
                print("✅ Basic caching functionality working")
        
    except Exception as e:
        print(f"❌ Basic caching test failed: {e}")
        success = False
    
    # Test cache methods
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create test contract
            test_data = pd.DataFrame({
                'open': [100.0, 101.0],
                'high': [105.0, 106.0],
                'low': [95.0, 96.0],
                'close': [103.0, 104.0],
                'volume': [1000, 1100]
            })
            
            contract_file = Path(temp_dir) / "methods_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Test is_cached method
            if manager.is_cached("methods_test"):
                print("❌ is_cached returned True for non-cached contract")
                success = False
            
            # Load contract
            manager.load_contract_data("methods_test")
            
            if not manager.is_cached("methods_test"):
                print("❌ is_cached returned False for cached contract")
                success = False
            
            # Test get_cached_data method
            cached_data = manager.get_cached_data("methods_test")
            if cached_data is None:
                print("❌ get_cached_data returned None for cached contract")
                success = False
            
            # Test cache stats
            stats = manager.get_cache_stats()
            required_stats_keys = ['cache_hits', 'cache_misses', 'hit_rate_percent', 'cached_contracts']
            
            for key in required_stats_keys:
                if key not in stats:
                    print(f"❌ Missing cache stats key: {key}")
                    success = False
            
            # Test cache details
            details = manager.get_cache_details()
            if "methods_test" not in details:
                print("❌ Contract not found in cache details")
                success = False
            
            if success:
                print("✅ Cache methods working")
        
    except Exception as e:
        print(f"❌ Cache methods test failed: {e}")
        success = False
    
    # Test LRU eviction
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir, max_cached_contracts=2)
            
            # Create test contracts
            test_data = pd.DataFrame({
                'open': [100.0, 101.0],
                'high': [105.0, 106.0],
                'low': [95.0, 96.0],
                'close': [103.0, 104.0],
                'volume': [1000, 1100]
            })
            
            contracts = ["lru_a", "lru_b", "lru_c"]
            for contract in contracts:
                contract_file = Path(temp_dir) / f"{contract}_tr_ba_data.parquet"
                test_data.to_parquet(contract_file)
            
            # Load first two contracts
            manager.load_contract_data("lru_a")
            manager.load_contract_data("lru_b")
            
            if len(manager.data_cache) != 2:
                print(f"❌ Expected 2 cached contracts, got {len(manager.data_cache)}")
                success = False
            
            # Load third contract (should trigger eviction)
            manager.load_contract_data("lru_c")
            
            if len(manager.data_cache) != 2:
                print(f"❌ Cache size incorrect after eviction: {len(manager.data_cache)}")
                success = False
            
            if manager.cache_evictions == 0:
                print("❌ No evictions recorded")
                success = False
            
            # First contract should be evicted (LRU)
            if manager.is_cached("lru_a"):
                print("❌ LRU contract was not evicted")
                success = False
            
            if success:
                print("✅ LRU eviction working")
        
    except Exception as e:
        print(f"❌ LRU eviction test failed: {e}")
        success = False
    
    # Test memory tracking
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create larger test contract
            test_data = pd.DataFrame({
                'open': [100.0 + i * 0.1 for i in range(1000)],
                'high': [105.0 + i * 0.1 for i in range(1000)],
                'low': [95.0 + i * 0.1 for i in range(1000)],
                'close': [103.0 + i * 0.1 for i in range(1000)],
                'volume': [1000 + i for i in range(1000)]
            })
            
            contract_file = Path(temp_dir) / "memory_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Check initial memory
            if manager.current_cache_memory_mb != 0.0:
                print(f"❌ Initial cache memory should be 0, got {manager.current_cache_memory_mb}")
                success = False
            
            # Load contract
            data = manager.load_contract_data("memory_test")
            
            # Check memory tracking
            if manager.current_cache_memory_mb <= 0:
                print("❌ Cache memory not tracked after loading")
                success = False
            
            # Memory should be reasonable
            expected_memory = data.memory_usage(deep=True).sum() / (1024 * 1024)
            if abs(manager.current_cache_memory_mb - expected_memory) > 1.0:
                print(f"❌ Memory tracking inaccurate: expected ~{expected_memory:.1f} MB, got {manager.current_cache_memory_mb:.1f} MB")
                success = False
            
            if success:
                print("✅ Memory tracking working")
        
    except Exception as e:
        print(f"❌ Memory tracking test failed: {e}")
        success = False
    
    # Test cache operations
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create test contract
            test_data = pd.DataFrame({
                'open': [100.0], 'high': [105.0], 'low': [95.0], 
                'close': [103.0], 'volume': [1000]
            })
            
            contract_file = Path(temp_dir) / "ops_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Load and cache
            manager.load_contract_data("ops_test")
            
            # Test clear specific contract
            manager.clear_cache("ops_test")
            
            if manager.is_cached("ops_test"):
                print("❌ Contract still cached after clear")
                success = False
            
            if manager.current_cache_memory_mb != 0.0:
                print("❌ Memory not freed after cache clear")
                success = False
            
            # Test preload
            result = manager.preload_contracts(["ops_test"])
            
            if not result.get("ops_test"):
                print("❌ Preload failed")
                success = False
            
            if not manager.is_cached("ops_test"):
                print("❌ Contract not cached after preload")
                success = False
            
            if success:
                print("✅ Cache operations working")
        
    except Exception as e:
        print(f"❌ Cache operations test failed: {e}")
        success = False
    
    # Test performance improvement
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create test contract
            test_data = pd.DataFrame({
                'open': [100.0 + i * 0.01 for i in range(5000)],
                'high': [105.0 + i * 0.01 for i in range(5000)],
                'low': [95.0 + i * 0.01 for i in range(5000)],
                'close': [103.0 + i * 0.01 for i in range(5000)],
                'volume': [1000 + i for i in range(5000)]
            })
            
            contract_file = Path(temp_dir) / "perf_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Time cache miss
            start_time = time.time()
            manager.load_contract_data("perf_test")
            miss_time = time.time() - start_time
            
            # Time cache hit
            start_time = time.time()
            manager.load_contract_data("perf_test")
            hit_time = time.time() - start_time
            
            # Cache hit should be faster
            if hit_time >= miss_time:
                print(f"❌ Cache hit not faster: miss={miss_time:.4f}s, hit={hit_time:.4f}s")
                success = False
            else:
                speedup = miss_time / hit_time
                print(f"✅ Performance improvement: {speedup:.1f}x speedup")
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        success = False
    
    # Check test files exist
    test_files = [
        Path("tests/test_contract_data_manager_cache.py"),
        Path("tests/test_cache_performance_benchmark.py")
    ]
    
    for test_file in test_files:
        if test_file.exists():
            print(f"✅ Test file exists: {test_file}")
        else:
            print(f"❌ Missing test file: {test_file}")
            success = False
    
    # Run cache tests
    try:
        print("\n🧪 Running cache tests...")
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_contract_data_manager_cache.py", 
            "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All cache tests passed")
        else:
            print(f"❌ Cache tests failed:\n{result.stdout}\n{result.stderr}")
            success = False
    except Exception as e:
        print(f"❌ Error running cache tests: {e}")
        success = False
    
    if success:
        print("\n🎉 Phase 1.1.5 validation PASSED!")
        print("✅ Cache implementation is ready")
        print("💾 LRU caching, memory management, and performance optimization complete")
        print("🚀 Ready to proceed to Phase 1.1.6: Integration and Polish")
        return True
    else:
        print("\n❌ Phase 1.1.5 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    validate_phase_1_1_5()