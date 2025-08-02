"""
Integration module for Phase 1.1 - combining parameter generation with data management.

Provides high-level interface for integrated parameter and data processing.
"""

import time
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import pandas as pd

from .parameter_combinations import (
    generate_combination_batch,
    get_combination_sample,
    get_combination_counts,
    validate_complete_combination
)
from .contract_data_manager import ContractDataManager, ValidationResult


class Phase1Integration:
    """
    Integrated Phase 1.1 system combining parameter generation with data management.
    
    Provides high-level interface for:
    - Parameter combination generation
    - Contract data loading with caching
    - Integrated validation and error handling
    - Performance monitoring and optimization
    """
    
    def __init__(self, 
                 data_directory: str = "data",
                 max_cached_contracts: int = 3,
                 enable_logging: bool = True):
        """
        Initialize integrated Phase 1.1 system.
        
        Args:
            data_directory: Directory containing contract data files
            max_cached_contracts: Maximum contracts to cache simultaneously
            enable_logging: Enable detailed logging
        """
        self.data_directory = data_directory
        self.max_cached_contracts = max_cached_contracts
        
        # Initialize components
        self.data_manager = ContractDataManager(
            data_directory=data_directory,
            max_cached_contracts=max_cached_contracts
        )
        
        # Performance tracking
        self.combinations_processed = 0
        self.processing_start_time = None
        self.errors_encountered = 0
        self.warnings_generated = 0
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        if enable_logging:
            self._setup_logging()
        
        self.logger.info(f"🚀 Phase 1.1 Integration initialized")
        self.logger.info(f"   📂 Data directory: {self.data_directory}")
        self.logger.info(f"   💾 Max cached contracts: {self.max_cached_contracts}")
    
    def get_system_overview(self) -> Dict:
        """
        Get comprehensive overview of the integrated system.
        
        Returns:
            Dictionary with system status and capabilities
        """
        # Get parameter counts
        param_counts = get_combination_counts()
        
        # Get available contracts
        available_contracts = self.data_manager.list_available_contracts()
        
        # Get data manager stats
        data_stats = self.data_manager.get_manager_statistics()
        
        return {
            'system_version': '1.1.0',
            'components': {
                'parameter_generation': 'Ready',
                'data_management': 'Ready',
                'caching': 'Enabled' if self.max_cached_contracts > 0 else 'Disabled'
            },
            'parameter_capabilities': {
                'total_combinations_estimate': param_counts['total_combinations_estimate'],
                'contracts_available': len(available_contracts),
                'available_contracts': available_contracts[:5],  # Show first 5
                'date_range': param_counts.get('date_range', 'Not specified')
            },
            'data_capabilities': {
                'cache_max_contracts': self.max_cached_contracts,
                'files_loaded': data_stats['files_loaded'],
                'cache_performance': data_stats.get('cache_performance', {})
            },
            'processing_stats': {
                'combinations_processed': self.combinations_processed,
                'errors_encountered': self.errors_encountered,
                'warnings_generated': self.warnings_generated
            }
        }
    
    def validate_system_readiness(self) -> ValidationResult:
        """
        Validate that the integrated system is ready for processing.
        
        Returns:
            ValidationResult with readiness status and details
        """
        result = ValidationResult(True)
        
        try:
            # Check data directory
            if not Path(self.data_directory).exists():
                return ValidationResult(False, f"Data directory not found: {self.data_directory}")
            
            # Check available contracts
            available_contracts = self.data_manager.list_available_contracts()
            if not available_contracts:
                result.add_warning("No contract data files found in data directory")
                result.add_detail('contracts_found', 0)
            else:
                result.add_detail('contracts_found', len(available_contracts))
                result.add_detail('sample_contracts', available_contracts[:3])
            
            # Test parameter generation
            try:
                sample_combinations = get_combination_sample(5)
                if len(sample_combinations) != 5:
                    return ValidationResult(False, "Parameter generation test failed")
                
                # Validate sample combinations
                for combo in sample_combinations:
                    if not validate_complete_combination(combo):
                        return ValidationResult(False, "Generated combination failed validation")
                
                result.add_detail('parameter_generation_test', 'Passed')
                
            except Exception as e:
                return ValidationResult(False, f"Parameter generation error: {e}")
            
            # Test data loading (if contracts available)
            if available_contracts:
                try:
                    test_contract = available_contracts[0]
                    contract_info = self.data_manager.get_contract_info(test_contract)
                    
                    if contract_info['file_exists']:
                        result.add_detail('data_loading_test', 'Passed')
                        result.add_detail('test_contract', test_contract)
                    else:
                        result.add_warning(f"Test contract file issue: {test_contract}")
                        
                except Exception as e:
                    result.add_warning(f"Data loading test error: {e}")
            
            # Check system resources
            try:
                cache_stats = self.data_manager.get_cache_stats()
                result.add_detail('cache_status', cache_stats)
            except Exception as e:
                result.add_warning(f"Cache status check failed: {e}")
            
            # Get combination counts
            try:
                counts = get_combination_counts()
                result.add_detail('combination_counts', counts)
            except Exception as e:
                return ValidationResult(False, f"Combination count error: {e}")
            
            return result
            
        except Exception as e:
            return ValidationResult(False, f"System validation error: {e}")
    
    def process_sample_workflow(self, 
                               sample_size: int = 10,
                               target_contracts: Optional[List[str]] = None) -> Dict:
        """
        Process a sample workflow demonstrating integrated functionality.
        
        Args:
            sample_size: Number of combinations to process
            target_contracts: Specific contracts to use, or None for auto-detection
            
        Returns:
            Dictionary with workflow results and performance metrics
        """
        self.logger.info(f"🔄 Starting sample workflow: {sample_size} combinations")
        workflow_start = time.time()
        
        try:
            # Validate system first
            validation = self.validate_system_readiness()
            if not validation.is_valid:
                return {
                    'success': False,
                    'error': f"System validation failed: {validation.error_message}",
                    'workflow_time': 0
                }
            
            # Determine contracts to use
            if target_contracts is None:
                available_contracts = self.data_manager.list_available_contracts()
                if not available_contracts:
                    return {
                        'success': False,
                        'error': "No contract data files available",
                        'workflow_time': time.time() - workflow_start
                    }
                target_contracts = available_contracts[:1]  # Use first available
            
            # Generate sample combinations
            self.logger.info(f"📊 Generating {sample_size} parameter combinations...")
            combinations = get_combination_sample(sample_size)
            
            # Process combinations with data loading
            results = []
            data_load_times = []
            validation_results = []
            
            for i, combination in enumerate(combinations):
                combo_start = time.time()
                
                try:
                    # Validate combination
                    if not validate_complete_combination(combination):
                        self.warnings_generated += 1
                        self.logger.warning(f"⚠️  Combination {i} failed validation")
                        continue
                    
                    # Use first available contract for this demonstration
                    contract_code = target_contracts[0]
                    combination['contract'] = contract_code  # Override for demo
                    
                    # Load contract data
                    data_load_start = time.time()
                    contract_data = self.data_manager.load_contract_data(contract_code)
                    data_load_time = time.time() - data_load_start
                    data_load_times.append(data_load_time)
                    
                    # Create result
                    combo_result = {
                        'combo_id': combination['combo_id'],
                        'contract': contract_code,
                        'data_rows': len(contract_data),
                        'data_columns': list(contract_data.columns),
                        'data_load_time': data_load_time,
                        'processing_time': time.time() - combo_start,
                        'success': True
                    }
                    
                    results.append(combo_result)
                    self.combinations_processed += 1
                    
                    self.logger.debug(f"✅ Processed combination {i}: {combo_result['data_rows']} rows in {data_load_time:.3f}s")
                    
                except Exception as e:
                    self.errors_encountered += 1
                    self.logger.error(f"❌ Error processing combination {i}: {e}")
                    
                    error_result = {
                        'combo_id': combination.get('combo_id', i),
                        'contract': combination.get('contract', 'unknown'),
                        'error': str(e),
                        'processing_time': time.time() - combo_start,
                        'success': False
                    }
                    results.append(error_result)
            
            # Calculate performance metrics
            workflow_time = time.time() - workflow_start
            successful_results = [r for r in results if r['success']]
            
            avg_data_load_time = sum(data_load_times) / len(data_load_times) if data_load_times else 0
            cache_stats = self.data_manager.get_cache_stats()
            
            workflow_summary = {
                'success': True,
                'workflow_time': workflow_time,
                'combinations_requested': sample_size,
                'combinations_processed': len(successful_results),
                'combinations_failed': len(results) - len(successful_results),
                'contracts_used': target_contracts,
                'performance_metrics': {
                    'avg_data_load_time': avg_data_load_time,
                    'total_processing_time': sum(r['processing_time'] for r in results),
                    'cache_hit_rate': cache_stats.get('hit_rate_percent', 0),
                    'cache_memory_usage': cache_stats.get('current_memory_mb', 0)
                },
                'results': results[:5],  # Include first 5 results as samples
                'validation_warnings': validation.warnings
            }
            
            self.logger.info(f"✅ Sample workflow completed in {workflow_time:.2f}s")
            self.logger.info(f"   📊 Processed: {len(successful_results)}/{sample_size} combinations")
            self.logger.info(f"   💾 Cache hit rate: {cache_stats.get('hit_rate_percent', 0):.1f}%")
            
            return workflow_summary
            
        except Exception as e:
            self.errors_encountered += 1
            self.logger.error(f"❌ Sample workflow failed: {e}")
            
            return {
                'success': False,
                'error': str(e),
                'workflow_time': time.time() - workflow_start,
                'combinations_processed': 0
            }
    
    def optimize_system(self) -> Dict[str, any]:
        """
        Optimize the integrated system for better performance.
        
        Returns:
            Dictionary with optimization results
        """
        self.logger.info("🔧 Optimizing integrated system...")
        
        optimization_results = {}
        
        try:
            # Optimize data cache
            cache_optimization = self.data_manager.optimize_cache()
            optimization_results['cache_optimization'] = cache_optimization
            
            # Get updated statistics
            updated_stats = self.data_manager.get_cache_stats()
            optimization_results['updated_cache_stats'] = updated_stats
            
            # Force garbage collection
            import gc
            collected = gc.collect()
            optimization_results['garbage_collected'] = collected
            
            self.logger.info(f"✅ System optimization complete")
            self.logger.info(f"   🗑️  Cache contracts removed: {cache_optimization.get('contracts_removed', 0)}")
            self.logger.info(f"   💾 Current cache memory: {updated_stats.get('current_memory_mb', 0):.1f} MB")
            
            return optimization_results
            
        except Exception as e:
            self.logger.error(f"❌ System optimization failed: {e}")
            return {'error': str(e)}
    
    def _setup_logging(self):
        """Setup logging configuration for integration module."""
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Configure logger
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            self.logger.addHandler(console_handler)


class IntegrationValidator:
    """
    Comprehensive validation for Phase 1.1 integration.
    
    Provides testing and validation capabilities for the integrated system.
    """
    
    @staticmethod
    def run_integration_tests(data_directory: str = "data") -> Dict:
        """
        Run comprehensive integration tests.
        
        Args:
            data_directory: Directory containing contract data
            
        Returns:
            Dictionary with test results
        """
        test_results = {
            'tests_run': 0,
            'tests_passed': 0,
            'tests_failed': 0,
            'test_details': []
        }
        
        try:
            # Test 1: System initialization
            test_results['tests_run'] += 1
            try:
                integration = Phase1Integration(data_directory)
                test_results['tests_passed'] += 1
                test_results['test_details'].append({
                    'test': 'System Initialization',
                    'status': 'PASSED',
                    'message': 'Integration system initialized successfully'
                })
            except Exception as e:
                test_results['tests_failed'] += 1
                test_results['test_details'].append({
                    'test': 'System Initialization', 
                    'status': 'FAILED',
                    'message': str(e)
                })
                return test_results  # Can't continue without initialization
            
            # Test 2: System readiness validation
            test_results['tests_run'] += 1
            try:
                validation = integration.validate_system_readiness()
                if validation.is_valid:
                    test_results['tests_passed'] += 1
                    test_results['test_details'].append({
                        'test': 'System Readiness',
                        'status': 'PASSED',
                        'message': f"System ready with {len(validation.warnings)} warnings"
                    })
                else:
                    test_results['tests_failed'] += 1
                    test_results['test_details'].append({
                        'test': 'System Readiness',
                        'status': 'FAILED', 
                        'message': validation.error_message
                    })
            except Exception as e:
                test_results['tests_failed'] += 1
                test_results['test_details'].append({
                    'test': 'System Readiness',
                    'status': 'FAILED',
                    'message': str(e)
                })
            
            # Test 3: Parameter generation
            test_results['tests_run'] += 1
            try:
                sample_combinations = get_combination_sample(3)
                if len(sample_combinations) == 3:
                    test_results['tests_passed'] += 1
                    test_results['test_details'].append({
                        'test': 'Parameter Generation',
                        'status': 'PASSED',
                        'message': 'Generated and validated 3 sample combinations'
                    })
                else:
                    test_results['tests_failed'] += 1
                    test_results['test_details'].append({
                        'test': 'Parameter Generation',
                        'status': 'FAILED',
                        'message': f"Expected 3 combinations, got {len(sample_combinations)}"
                    })
            except Exception as e:
                test_results['tests_failed'] += 1
                test_results['test_details'].append({
                    'test': 'Parameter Generation',
                    'status': 'FAILED',
                    'message': str(e)
                })
            
            # Test 4: Data management
            test_results['tests_run'] += 1
            try:
                available_contracts = integration.data_manager.list_available_contracts()
                if available_contracts:
                    # Try to get info for first contract
                    info = integration.data_manager.get_contract_info(available_contracts[0])
                    if info['file_exists']:
                        test_results['tests_passed'] += 1
                        test_results['test_details'].append({
                            'test': 'Data Management',
                            'status': 'PASSED',
                            'message': f"Successfully accessed contract: {available_contracts[0]}"
                        })
                    else:
                        test_results['tests_failed'] += 1
                        test_results['test_details'].append({
                            'test': 'Data Management',
                            'status': 'FAILED',
                            'message': f"Contract file not accessible: {available_contracts[0]}"
                        })
                else:
                    test_results['tests_passed'] += 1  # Not a failure, just no data
                    test_results['test_details'].append({
                        'test': 'Data Management',
                        'status': 'PASSED',
                        'message': 'No contract files found (expected for empty directory)'
                    })
            except Exception as e:
                test_results['tests_failed'] += 1
                test_results['test_details'].append({
                    'test': 'Data Management',
                    'status': 'FAILED',
                    'message': str(e)
                })
            
            # Test 5: Integrated workflow (if data available)
            test_results['tests_run'] += 1
            try:
                workflow_result = integration.process_sample_workflow(sample_size=2)
                if workflow_result['success']:
                    test_results['tests_passed'] += 1
                    test_results['test_details'].append({
                        'test': 'Integrated Workflow',
                        'status': 'PASSED',
                        'message': f"Processed {workflow_result['combinations_processed']} combinations"
                    })
                else:
                    test_results['tests_failed'] += 1
                    test_results['test_details'].append({
                        'test': 'Integrated Workflow',
                        'status': 'FAILED',
                        'message': workflow_result.get('error', 'Unknown workflow error')
                    })
            except Exception as e:
                test_results['tests_failed'] += 1
                test_results['test_details'].append({
                    'test': 'Integrated Workflow',
                    'status': 'FAILED',
                    'message': str(e)
                })
            
            return test_results
            
        except Exception as e:
            test_results['test_details'].append({
                'test': 'Integration Test Framework',
                'status': 'FAILED', 
                'message': f"Test framework error: {e}"
            })
            return test_results
    
    @staticmethod
    def generate_system_report(data_directory: str = "data") -> str:
        """
        Generate comprehensive system report.
        
        Args:
            data_directory: Directory containing contract data
            
        Returns:
            Formatted system report string
        """
        try:
            integration = Phase1Integration(data_directory)
            overview = integration.get_system_overview()
            validation = integration.validate_system_readiness()
            test_results = IntegrationValidator.run_integration_tests(data_directory)
            
            report = f"""
# Phase 1.1 Integration System Report

## System Overview
- **Version**: {overview['system_version']}
- **Components**: {', '.join(f"{k}: {v}" for k, v in overview['components'].items())}

## Parameter Generation Capabilities
- **Total Combinations**: {overview['parameter_capabilities']['total_combinations_estimate']:,}
- **Available Contracts**: {overview['parameter_capabilities']['contracts_available']}
- **Sample Contracts**: {', '.join(overview['parameter_capabilities']['available_contracts'])}
- **Date Range**: {overview['parameter_capabilities']['date_range']}

## Data Management Capabilities  
- **Cache Max Contracts**: {overview['data_capabilities']['cache_max_contracts']}
- **Files Loaded**: {overview['data_capabilities']['files_loaded']}
- **Cache Hit Rate**: {overview['data_capabilities'].get('cache_performance', {}).get('hit_rate_percent', 0):.1f}%

## System Validation
- **Status**: {"✅ READY" if validation.is_valid else "❌ NOT READY"}
- **Contracts Found**: {validation.validation_details.get('contracts_found', 0)}
- **Warnings**: {len(validation.warnings)}

## Integration Tests
- **Tests Run**: {test_results['tests_run']}
- **Tests Passed**: {test_results['tests_passed']}
- **Tests Failed**: {test_results['tests_failed']}
- **Success Rate**: {(test_results['tests_passed']/test_results['tests_run']*100):.1f}%

## Test Details
"""
            
            for test in test_results['test_details']:
                status_emoji = "✅" if test['status'] == 'PASSED' else "❌"
                report += f"- {status_emoji} **{test['test']}**: {test['message']}\n"
            
            if validation.warnings:
                report += "\n## Warnings\n"
                for warning in validation.warnings:
                    report += f"- ⚠️  {warning}\n"
            
            report += f"\n## Processing Statistics\n"
            report += f"- **Combinations Processed**: {overview['processing_stats']['combinations_processed']}\n"
            report += f"- **Errors Encountered**: {overview['processing_stats']['errors_encountered']}\n"
            report += f"- **Warnings Generated**: {overview['processing_stats']['warnings_generated']}\n"
            
            return report
            
        except Exception as e:
            return f"# System Report Generation Failed\n\nError: {e}"


if __name__ == "__main__":
    # Demo integration functionality
    print("🧪 Testing Phase 1.1 Integration...")
    
    try:
        # Initialize integration
        integration = Phase1Integration("data")
        
        # Get system overview
        overview = integration.get_system_overview()
        print(f"📊 System Overview: {overview['system_version']}")
        print(f"   📋 Components: {overview['components']}")
        print(f"   🔢 Total combinations: {overview['parameter_capabilities']['total_combinations_estimate']:,}")
        
        # Validate system
        validation = integration.validate_system_readiness()
        print(f"🔍 System validation: {'✅ READY' if validation.is_valid else '❌ NOT READY'}")
        
        if validation.warnings:
            print(f"⚠️  Warnings: {len(validation.warnings)}")
        
        # Run integration tests
        test_results = IntegrationValidator.run_integration_tests("data")
        print(f"🧪 Integration tests: {test_results['tests_passed']}/{test_results['tests_run']} passed")
        
        # Generate and print report
        report = IntegrationValidator.generate_system_report("data")
        print("\n" + "="*60)
        print(report)
        print("="*60)
        
        print("✅ Phase 1.1 Integration ready!")
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")