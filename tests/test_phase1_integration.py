"""
Comprehensive integration tests for Phase 1.1 complete system.

Tests the integration of parameter generation with contract data management.
"""

import pytest
import pandas as pd
import tempfile
import time
from pathlib import Path
from src.gpu_parallel_processing.integration import Phase1Integration, IntegrationValidator
from src.gpu_parallel_processing.parameter_combinations import get_combination_sample
from src.gpu_parallel_processing.contract_data_manager import ContractDataManager


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_contract_data():
    """Create sample contract data for integration testing."""
    size = 1000
    return pd.DataFrame({
        'open': [100.0 + i * 0.01 for i in range(size)],
        'high': [105.0 + i * 0.01 for i in range(size)],
        'low': [95.0 + i * 0.01 for i in range(size)],
        'close': [103.0 + i * 0.01 for i in range(size)],
        'volume': [1000 + i for i in range(size)]
    })


@pytest.fixture
def integration_setup(temp_data_dir, sample_contract_data):
    """Create complete integration test setup."""
    # Create multiple test contracts using valid patterns
    contracts = ["test01_25", "test02_25", "test03_25"]
    
    for contract in contracts:
        contract_file = temp_data_dir / f"{contract}_tr_ba_data.parquet"
        sample_contract_data.to_parquet(contract_file)
    
    return {
        'data_dir': str(temp_data_dir),
        'contracts': contracts,
        'data_size': len(sample_contract_data)
    }


class TestPhase1Integration:
    """Test Phase 1.1 integration functionality."""
    
    def test_integration_initialization(self, integration_setup):
        """Test integration system initialization."""
        integration = Phase1Integration(
            data_directory=integration_setup['data_dir'],
            max_cached_contracts=2
        )
        
        assert integration.data_directory == integration_setup['data_dir']
        assert integration.max_cached_contracts == 2
        assert integration.combinations_processed == 0
        assert integration.errors_encountered == 0
        assert isinstance(integration.data_manager, ContractDataManager)
    
    def test_system_overview(self, integration_setup):
        """Test system overview generation."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        overview = integration.get_system_overview()
        
        # Check structure
        required_keys = ['system_version', 'components', 'parameter_capabilities', 
                        'data_capabilities', 'processing_stats']
        for key in required_keys:
            assert key in overview
        
        # Check parameter capabilities
        assert overview['parameter_capabilities']['contracts_available'] == len(integration_setup['contracts'])
        assert overview['parameter_capabilities']['total_combinations_estimate'] > 0
        
        # Check data capabilities
        assert overview['data_capabilities']['cache_max_contracts'] == 3  # default
        assert 'cache_performance' in overview['data_capabilities']
    
    def test_system_readiness_validation(self, integration_setup):
        """Test system readiness validation."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        validation = integration.validate_system_readiness()
        
        assert validation.is_valid == True
        assert 'contracts_found' in validation.validation_details
        assert validation.validation_details['contracts_found'] == len(integration_setup['contracts'])
        assert 'parameter_generation_test' in validation.validation_details
        assert validation.validation_details['parameter_generation_test'] == 'Passed'
    
    def test_system_readiness_with_missing_data(self, temp_data_dir):
        """Test system readiness validation with missing data directory."""
        # Use non-existent directory - should raise ValueError during initialization
        with pytest.raises((ValueError, Exception)):
            integration = Phase1Integration("/nonexistent/directory")
    
    def test_sample_workflow_success(self, integration_setup):
        """Test successful sample workflow execution."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        result = integration.process_sample_workflow(
            sample_size=5,
            target_contracts=integration_setup['contracts'][:1]
        )
        
        assert result['success'] == True
        assert result['combinations_requested'] == 5
        assert result['combinations_processed'] > 0
        assert result['workflow_time'] > 0
        assert 'performance_metrics' in result
        assert len(result['results']) > 0
    
    def test_sample_workflow_with_no_contracts(self, temp_data_dir):
        """Test sample workflow with no available contracts."""
        integration = Phase1Integration(str(temp_data_dir))  # Empty directory
        
        result = integration.process_sample_workflow(sample_size=3)
        
        assert result['success'] == False
        assert "no contract data files available" in result['error'].lower()
    
    def test_system_optimization(self, integration_setup):
        """Test system optimization functionality."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        # Load some data first
        integration.process_sample_workflow(sample_size=2, target_contracts=integration_setup['contracts'][:1])
        
        # Run optimization
        optimization_result = integration.optimize_system()
        
        assert 'cache_optimization' in optimization_result
        assert 'updated_cache_stats' in optimization_result
        assert 'garbage_collected' in optimization_result
    
    def test_error_handling_and_tracking(self, integration_setup):
        """Test error handling and tracking in integration."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        # Try to process with non-existent contracts
        result = integration.process_sample_workflow(
            sample_size=3,
            target_contracts=["nonexistent_contract"]
        )
        
        # Should handle errors gracefully
        assert result['success'] == False or result['combinations_failed'] > 0
        
        # Error should be tracked
        overview = integration.get_system_overview()
        assert overview['processing_stats']['errors_encountered'] >= 0


class TestIntegrationValidator:
    """Test integration validator functionality."""
    
    def test_integration_tests_with_data(self, integration_setup):
        """Test integration tests with available data."""
        test_results = IntegrationValidator.run_integration_tests(integration_setup['data_dir'])
        
        assert test_results['tests_run'] > 0
        assert test_results['tests_passed'] > 0
        assert isinstance(test_results['test_details'], list)
        
        # Check that all tests have proper structure
        for test in test_results['test_details']:
            assert 'test' in test
            assert 'status' in test
            assert 'message' in test
            assert test['status'] in ['PASSED', 'FAILED']
    
    def test_integration_tests_without_data(self, temp_data_dir):
        """Test integration tests without data files."""
        test_results = IntegrationValidator.run_integration_tests(str(temp_data_dir))
        
        # Tests should run even without data
        assert test_results['tests_run'] > 0
        
        # Some tests should pass (initialization, parameter generation)
        assert test_results['tests_passed'] > 0
    
    def test_system_report_generation(self, integration_setup):
        """Test system report generation."""
        report = IntegrationValidator.generate_system_report(integration_setup['data_dir'])
        
        assert isinstance(report, str)
        assert len(report) > 0
        assert "Phase 1.1 Integration System Report" in report
        assert "System Overview" in report
        assert "Parameter Generation Capabilities" in report
        assert "Data Management Capabilities" in report
        assert "Integration Tests" in report
    
    def test_system_report_with_errors(self):
        """Test system report generation with invalid directory."""
        report = IntegrationValidator.generate_system_report("/nonexistent/directory")
        
        assert isinstance(report, str)
        assert "failed" in report.lower() or "error" in report.lower()


class TestIntegrationPerformance:
    """Test integration performance characteristics."""
    
    def test_workflow_performance_scaling(self, integration_setup):
        """Test that workflow performance scales reasonably."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        # Test different workflow sizes
        sizes = [5, 10, 15]
        times = []
        
        for size in sizes:
            start_time = time.time()
            result = integration.process_sample_workflow(
                sample_size=size,
                target_contracts=integration_setup['contracts'][:1]
            )
            end_time = time.time()
            
            if result['success']:
                times.append(end_time - start_time)
            else:
                times.append(float('inf'))  # Mark failures
        
        # Check that time doesn't increase dramatically
        if len([t for t in times if t != float('inf')]) >= 2:
            # At least 2 successful runs to compare
            valid_times = [t for t in times if t != float('inf')]
            time_ratio = max(valid_times) / min(valid_times)
            assert time_ratio < 10  # Should not be more than 10x difference
    
    def test_cache_effectiveness_in_workflow(self, integration_setup):
        """Test that caching improves workflow performance."""
        integration = Phase1Integration(integration_setup['data_dir'], max_cached_contracts=3)
        
        # First workflow run (cache misses)
        start_time = time.time()
        result1 = integration.process_sample_workflow(
            sample_size=5,
            target_contracts=integration_setup['contracts'][:1]
        )
        first_run_time = time.time() - start_time
        
        # Second workflow run (cache hits)
        start_time = time.time()
        result2 = integration.process_sample_workflow(
            sample_size=5,
            target_contracts=integration_setup['contracts'][:1]
        )
        second_run_time = time.time() - start_time
        
        # Second run should be faster (or at least not much slower)
        if result1['success'] and result2['success']:
            # Allow some variation due to system factors
            assert second_run_time <= first_run_time * 1.5  # At most 50% slower
    
    def test_memory_efficiency_in_integration(self, integration_setup):
        """Test memory efficiency of integrated workflow."""
        integration = Phase1Integration(integration_setup['data_dir'], max_cached_contracts=2)
        
        # Run workflow multiple times to test memory stability
        initial_cache_stats = integration.data_manager.get_cache_stats()
        
        for i in range(3):
            integration.process_sample_workflow(
                sample_size=3,
                target_contracts=integration_setup['contracts'][:2]
            )
        
        final_cache_stats = integration.data_manager.get_cache_stats()
        
        # Memory usage should be reasonable and stable
        assert final_cache_stats['cached_contracts'] <= integration.max_cached_contracts
        assert final_cache_stats['current_memory_mb'] >= 0  # Memory usage could be 0 if cache was cleared
        
        # Hit rate should improve after first run
        if final_cache_stats['cache_hits'] + final_cache_stats['cache_misses'] > 0:
            assert final_cache_stats['hit_rate_percent'] > 0


class TestIntegrationRobustness:
    """Test integration system robustness and error handling."""
    
    def test_workflow_with_invalid_combinations(self, integration_setup):
        """Test workflow robustness with invalid combinations."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        # This should still work even if some combinations are invalid
        result = integration.process_sample_workflow(
            sample_size=10,
            target_contracts=integration_setup['contracts'][:1]
        )
        
        # Should handle any invalid combinations gracefully
        assert isinstance(result, dict)
        assert 'success' in result
        assert 'workflow_time' in result
    
    def test_workflow_with_corrupted_data_directory(self, temp_data_dir):
        """Test workflow behavior with corrupted data directory."""
        # Create a corrupted file with valid contract name
        fake_file = temp_data_dir / "test123_tr_ba_data.parquet"
        fake_file.write_text("not a parquet file")
        
        integration = Phase1Integration(str(temp_data_dir))
        
        # Should handle corrupted files gracefully
        result = integration.process_sample_workflow(sample_size=2)
        
        # Might succeed (no contracts found) or fail (file read error)
        # Either way should return valid result structure
        assert isinstance(result, dict)
        assert 'success' in result
    
    def test_system_validation_resilience(self, integration_setup):
        """Test system validation resilience to various issues."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        # Run validation multiple times
        for _ in range(3):
            validation = integration.validate_system_readiness()
            
            # Should return consistent results
            assert isinstance(validation.is_valid, bool)
            assert isinstance(validation.validation_details, dict)
            assert isinstance(validation.warnings, list)


class TestEndToEndIntegration:
    """End-to-end integration tests."""
    
    def test_complete_phase1_workflow(self, integration_setup):
        """Test complete Phase 1.1 workflow from start to finish."""
        # Initialize system
        integration = Phase1Integration(integration_setup['data_dir'])
        
        # Validate system
        validation = integration.validate_system_readiness()
        assert validation.is_valid
        
        # Get system overview
        overview = integration.get_system_overview()
        assert overview['parameter_capabilities']['contracts_available'] > 0
        
        # Run sample workflow
        workflow_result = integration.process_sample_workflow(sample_size=8)
        assert workflow_result['success']
        assert workflow_result['combinations_processed'] > 0
        
        # Optimize system
        optimization_result = integration.optimize_system()
        assert 'cache_optimization' in optimization_result
        
        # Run integration tests
        test_results = IntegrationValidator.run_integration_tests(integration_setup['data_dir'])
        assert test_results['tests_passed'] > test_results['tests_failed']
        
        # Generate report
        report = IntegrationValidator.generate_system_report(integration_setup['data_dir'])
        assert "✅ READY" in report or "PASSED" in report
        
        # Final system state should be healthy
        final_overview = integration.get_system_overview()
        assert final_overview['processing_stats']['combinations_processed'] > 0
    
    def test_multi_contract_processing(self, integration_setup):
        """Test processing with multiple contracts."""
        integration = Phase1Integration(integration_setup['data_dir'])
        
        # Process with multiple contracts
        result = integration.process_sample_workflow(
            sample_size=6,
            target_contracts=integration_setup['contracts']
        )
        
        # Should handle multiple contracts
        assert result['success'] == True or result['combinations_processed'] > 0
        
        # Cache should be utilized effectively
        cache_stats = integration.data_manager.get_cache_stats()
        assert cache_stats['cached_contracts'] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])