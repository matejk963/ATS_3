"""
Example usage of DataFetcher implementation

Demonstrates both explicit date and lookback-based contract configurations
following the patterns outlined in the implementation plan.
"""

import sys
import os
from datetime import datetime
import pandas as pd

# Add project root to path - cross-platform compatible
if os.name == 'nt':  # Windows
    # Running in Windows PowerShell
    project_root = r'C:\Users\krajcovic\Documents\GitHub\ATS_3'
else:
    # Running in WSL/Linux
    project_root = '/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3'

sys.path.append(project_root)

from src.core.data_fetcher import DataFetcher, TPDATA_AVAILABLE


def main():
    """Demonstrate DataFetcher usage with example configurations"""
    
    print("🔋 ATS_3 DataFetcher Example")
    print("=" * 50)
    
    # Check TPData availability
    if not TPDATA_AVAILABLE:
        print("⚠️ TPData not available - running in demo mode")
        demo_mode = True
    else:
        print("✅ TPData available")
        demo_mode = False
    
    print("\n📋 Example 1: Explicit Date Ranges")
    print("-" * 30)
    
    # Example from the plan: Explicit date ranges per contract
    contracts_explicit = [
        {
            'market': 'de', 'tenor': 'm', 'contract': '07_25',
            'start_date': '2025-04-01', 'end_date': '2025-06-30'
        },
        {
            'market': 'fr', 'tenor': 'q', 'contract': '2_25', 
            'start_date': '2024-10-01', 'end_date': '2024-12-31'
        }
    ]
    
    for contract in contracts_explicit:
        print(f"📄 Contract: {contract['market']}{contract['tenor']}{contract['contract']}")
        print(f"   Market: {contract['market']}")
        print(f"   Tenor: {contract['tenor']}")
        print(f"   Period: {contract['start_date']} to {contract['end_date']}")
    
    print("\n📋 Example 2: Lookback from Delivery Date")
    print("-" * 30)
    
    # Example from the plan: Lookback from delivery date
    contracts_lookback = [
        {
            'market': 'de', 'tenor': 'm', 'contract': '07_25',
            'lookback_days': 90  # 90 days before July 1, 2025
        },
        {
            'market': 'fr', 'tenor': 'q', 'contract': '2_25',
            'lookback_days': 120  # 120 days before Q2 2025 start
        }
    ]
    
    # Show how lookback resolves to actual dates
    from src.core.data_fetcher import DeliveryDateCalculator, DateRangeResolver
    
    calc = DeliveryDateCalculator()
    resolver = DateRangeResolver()
    
    for contract in contracts_lookback:
        delivery_date = calc.calc_delivery_date(contract['tenor'], contract['contract'])
        start_date, end_date = resolver.resolve_date_range(delivery_date, contract['lookback_days'])
        
        print(f"📄 Contract: {contract['market']}{contract['tenor']}{contract['contract']}")
        print(f"   Market: {contract['market']}")
        print(f"   Tenor: {contract['tenor']}")
        print(f"   Delivery Date: {delivery_date.strftime('%Y-%m-%d')}")
        print(f"   Lookback: {contract['lookback_days']} days")
        print(f"   Resolved Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    if not demo_mode:
        print("\n🔄 Running Data Fetching Example")
        print("-" * 30)
        
        try:
            # Initialize DataFetcher
            fetcher = DataFetcher(
                trading_hours=(9, 17),
                allowed_broker_ids=[1441]  # EEX broker ID
            )
            
            print("✅ DataFetcher initialized successfully")
            
            # Example: Fetch a single contract (small example to avoid long execution)
            small_contract = {
                'market': 'de', 'tenor': 'm', 'contract': '07_25',
                'start_date': '2025-06-25', 'end_date': '2025-06-27'  # 3 days only
            }
            
            print(f"📊 Fetching sample data for {small_contract['market']}{small_contract['tenor']}{small_contract['contract']}...")
            print(f"   Period: {small_contract['start_date']} to {small_contract['end_date']}")
            
            # This would actually fetch data in a real environment
            result = fetcher.fetch_contract_data(
                small_contract,
                include_trades=True,
                include_orders=True
            )
            
            print("✅ Data fetch completed successfully")
            
            # Show result structure
            print("\n📈 Result Structure:")
            for key, value in result.items():
                if isinstance(value, pd.DataFrame):
                    print(f"   {key}: DataFrame with {len(value)} rows, {len(value.columns)} columns")
                else:
                    print(f"   {key}: {type(value).__name__}")
            
            # Example: Fetch multiple contracts
            print(f"\n📊 Fetching multiple contracts...")
            
            multi_results = fetcher.fetch_multiple_contracts(
                contracts_lookback[:1],  # Just first contract to keep it manageable
                include_trades=True,
                include_orders=True
            )
            
            print("✅ Multiple contract fetch completed")
            
            # Example: Export to parquet
            output_dir = "/tmp/ats3_data_output"
            print(f"\n💾 Exporting to parquet files in {output_dir}...")
            
            fetcher.export_to_parquet(multi_results, output_dir)
            
            print("✅ Export completed successfully")
            
        except Exception as e:
            print(f"⚠️ Data fetching example failed (expected in test environment): {e}")
    
    else:
        print("\n🎯 Demo Mode: Configuration Validation")
        print("-" * 30)
        
        from src.core.data_fetcher import ContractValidator
        validator = ContractValidator()
        
        all_contracts = contracts_explicit + contracts_lookback
        
        for contract in all_contracts:
            try:
                validator.validate_contract(contract)
                contract_key = f"{contract['market']}{contract['tenor']}{contract['contract']}"
                print(f"✅ {contract_key}: Configuration is valid")
            except ValueError as e:
                print(f"❌ {contract_key}: {e}")
    
    print("\n🎉 Example completed successfully!")
    print("\n📝 Key Features Demonstrated:")
    print("   • TPData connectivity and availability checking")
    print("   • Flexible contract configuration (explicit dates vs lookback)")
    print("   • Automatic delivery date calculation")
    print("   • Business day lookback calculation")
    print("   • Contract validation")
    print("   • Unified data fetching interface")
    print("   • Parquet export functionality")


if __name__ == "__main__":
    main()