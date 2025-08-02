"""
Phase 1.1 Complete System Usage Example

Demonstrates how to use the integrated parameter generation and data management system.
"""

import time
from pathlib import Path
from src.gpu_parallel_processing.integration import Phase1Integration, IntegrationValidator
from src.gpu_parallel_processing.parameter_combinations import get_combination_counts
import pandas as pd

def main():
    """Demonstrate Phase 1.1 complete system usage."""
    print("🚀 Phase 1.1 Complete System Usage Example")
    print("=" * 50)
    
    # Initialize the integrated system
    print("\n1️⃣ Initializing integrated system...")
    
    # Use "data" directory by default, or create sample data if it doesn't exist
    data_dir = "data"
    if not Path(data_dir).exists():
        print(f"📂 Creating sample data directory: {data_dir}")
        Path(data_dir).mkdir(exist_ok=True)
        
        # Create sample contract data for demonstration
        create_sample_data(data_dir)
    
    integration = Phase1Integration(
        data_directory=data_dir,
        max_cached_contracts=3,
        enable_logging=True
    )
    
    print("✅ Integration system initialized")
    
    # Get system overview
    print("\n2️⃣ Getting system overview...")
    overview = integration.get_system_overview()
    
    print(f"📊 System Version: {overview['system_version']}")
    print(f"🔢 Total Parameter Combinations: {overview['parameter_capabilities']['total_combinations_estimate']:,}")
    print(f"📋 Available Contracts: {overview['parameter_capabilities']['contracts_available']}")
    print(f"💾 Cache Capacity: {overview['data_capabilities']['cache_max_contracts']} contracts")
    
    # Validate system readiness
    print("\n3️⃣ Validating system readiness...")
    validation = integration.validate_system_readiness()
    
    if validation.is_valid:
        print("✅ System is ready for processing")
        print(f"📂 Contracts found: {validation.validation_details.get('contracts_found', 0)}")
        
        if validation.warnings:
            print(f"⚠️  Warnings: {len(validation.warnings)}")
            for warning in validation.warnings[:3]:  # Show first 3 warnings
                print(f"   - {warning}")
    else:
        print(f"❌ System not ready: {validation.error_message}")
        return
    
    # Demonstrate parameter generation capabilities
    print("\n4️⃣ Demonstrating parameter generation...")
    
    param_counts = get_combination_counts()
    print(f"📈 Parameter breakdown:")
    print(f"   - Bias combinations: {param_counts['bias_combinations']}")
    print(f"   - Strategy combinations: {param_counts['strategy_combinations']}")  
    print(f"   - Base parameters: {param_counts['base_parameter_combinations']}")
    print(f"   - Total estimate: {param_counts['total_combinations_estimate']:,}")
    
    # Run sample workflow
    print("\n5️⃣ Running sample workflow...")
    
    workflow_start = time.time()
    workflow_result = integration.process_sample_workflow(sample_size=10)
    workflow_time = time.time() - workflow_start
    
    if workflow_result['success']:
        print(f"✅ Sample workflow completed in {workflow_time:.2f}s")
        print(f"📊 Results:")
        print(f"   - Combinations processed: {workflow_result['combinations_processed']}")
        print(f"   - Combinations failed: {workflow_result['combinations_failed']}")
        print(f"   - Average data load time: {workflow_result['performance_metrics']['avg_data_load_time']:.4f}s")
        print(f"   - Cache hit rate: {workflow_result['performance_metrics']['cache_hit_rate']:.1f}%")
        
        # Show sample results
        if workflow_result['results']:
            print(f"\n📋 Sample processing result:")
            sample_result = workflow_result['results'][0]
            if sample_result['success']:
                print(f"   - Contract: {sample_result['contract']}")
                print(f"   - Data rows: {sample_result['data_rows']:,}")
                print(f"   - Processing time: {sample_result['processing_time']:.3f}s")
            else:
                print(f"   - Error: {sample_result['error']}")
    else:
        print(f"❌ Sample workflow failed: {workflow_result.get('error', 'Unknown error')}")
    
    # Demonstrate cache performance
    print("\n6️⃣ Demonstrating cache performance...")
    
    cache_stats = integration.data_manager.get_cache_stats()
    print(f"💾 Cache statistics:")
    print(f"   - Cached contracts: {cache_stats['cached_contracts']}")
    print(f"   - Cache hits: {cache_stats['cache_hits']}")
    print(f"   - Cache misses: {cache_stats['cache_misses']}")
    print(f"   - Hit rate: {cache_stats['hit_rate_percent']:.1f}%")
    print(f"   - Memory usage: {cache_stats['current_memory_mb']:.1f} MB")
    
    # Show cache details
    cache_details = integration.data_manager.get_cache_details()
    if cache_details:
        print(f"\n📊 Cached contract details:")
        for contract, details in list(cache_details.items())[:2]:  # Show first 2
            print(f"   - {contract}: {details['memory_mb']:.1f} MB, {details['access_count']} accesses")
    
    # Optimize system
    print("\n7️⃣ Optimizing system...")
    
    optimization_result = integration.optimize_system()
    if 'error' not in optimization_result:
        cache_opt = optimization_result['cache_optimization']
        print(f"🔧 Optimization complete:")
        print(f"   - Contracts analyzed: {cache_opt['contracts_analyzed']}")
        print(f"   - Contracts removed: {cache_opt['contracts_removed']}")
        print(f"   - Memory freed: Available in updated stats")
    else:
        print(f"❌ Optimization failed: {optimization_result['error']}")
    
    # Run integration tests
    print("\n8️⃣ Running integration tests...")
    
    test_results = IntegrationValidator.run_integration_tests(data_dir)
    print(f"🧪 Integration test results:")
    print(f"   - Tests run: {test_results['tests_run']}")
    print(f"   - Tests passed: {test_results['tests_passed']}")
    print(f"   - Tests failed: {test_results['tests_failed']}")
    print(f"   - Success rate: {(test_results['tests_passed']/test_results['tests_run']*100):.1f}%")
    
    # Show test details
    for test in test_results['test_details']:
        status_emoji = "✅" if test['status'] == 'PASSED' else "❌"
        print(f"   {status_emoji} {test['test']}: {test['message']}")
    
    # Generate system report
    print("\n9️⃣ Generating system report...")
    
    report = IntegrationValidator.generate_system_report(data_dir)
    
    # Save report to file
    report_file = Path("phase1_1_system_report.md")
    report_file.write_text(report)
    print(f"📄 System report saved to: {report_file}")
    
    # Display final system state
    print("\n🔟 Final system state...")
    
    final_overview = integration.get_system_overview()
    final_stats = final_overview['processing_stats']
    
    print(f"📈 Processing statistics:")
    print(f"   - Combinations processed: {final_stats['combinations_processed']}")
    print(f"   - Errors encountered: {final_stats['errors_encountered']}")
    print(f"   - Warnings generated: {final_stats['warnings_generated']}")
    
    print("\n" + "=" * 50)
    print("🎉 Phase 1.1 Complete System Demonstration Finished!")
    print("✅ System is ready for production parameter processing")
    print("🚀 Next step: Implement Phase 1.2 GPU Processing Core")


def create_sample_data(data_dir: str):
    """Create sample contract data for demonstration."""
    print("📊 Creating sample contract data...")
    
    # Create sample data with realistic structure
    contracts = ["dem07_25", "fra08_25", "gbr07_25"]
    
    for contract in contracts:
        # Generate sample OHLCV data
        size = 5000  # 5K data points
        
        base_price = 100.0
        data = []
        
        for i in range(size):
            # Simulate realistic price movement
            price_change = (i * 0.01) + (i % 100 - 50) * 0.001  # Trend + noise
            
            open_price = base_price + price_change
            high_price = open_price + abs(i % 10) * 0.1
            low_price = open_price - abs(i % 8) * 0.1
            close_price = open_price + (i % 20 - 10) * 0.05
            volume = 1000 + i * 10 + (i % 50) * 20
            
            data.append({
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': int(volume)
            })
        
        # Create DataFrame and save to parquet
        df = pd.DataFrame(data)
        
        contract_file = Path(data_dir) / f"{contract}_tr_ba_data.parquet"
        df.to_parquet(contract_file, index=False)
        
        print(f"   ✅ Created {contract}: {len(df):,} data points")
    
    print(f"📂 Sample data created in {data_dir}/")


if __name__ == "__main__":
    main()