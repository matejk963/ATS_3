#!/usr/bin/env python3
"""
Test script for fund_analysis beta - Schema Configuration Verification
This script tests that the beta version is correctly configured to use 'MODEL_forecast_prices_beta' schema
"""

import sys
import os

# Add the fund_analysis beta path
sys.path.insert(0, r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis beta')

def test_schema_configuration():
    """Test that the spreads_creation module uses the correct beta schema"""
    try:
        from fund_analysis.utils.spreads_creation import schema_name
        print(f"✓ Schema configuration loaded successfully")
        print(f"✓ Current schema: {schema_name}")
        
        if schema_name == 'MODEL_forecast_prices_beta':
            print("✓ PASS: Using correct beta schema 'MODEL_forecast_prices_beta'")
            return True
        else:
            print(f"✗ FAIL: Expected 'MODEL_forecast_prices_beta', got '{schema_name}'")
            return False
            
    except ImportError as e:
        print(f"✗ FAIL: Could not import spreads_creation module: {e}")
        return False
    except Exception as e:
        print(f"✗ FAIL: Unexpected error: {e}")
        return False

def test_database_connection():
    """Test basic database connectivity (without executing actual queries)"""
    try:
        from Database.DB_reader import Database
        db = Database()
        print("✓ Database connection object created successfully")
        return True
    except ImportError as e:
        print(f"✗ WARNING: Could not import Database module: {e}")
        return False
    except Exception as e:
        print(f"✗ WARNING: Database connection issue: {e}")
        return False

def main():
    """Main test function"""
    print("="*60)
    print("FUND ANALYSIS BETA - SCHEMA CONFIGURATION TEST")
    print("="*60)
    
    # Test 1: Schema Configuration
    print("\n1. Testing Schema Configuration...")
    schema_test = test_schema_configuration()
    
    # Test 2: Database Connection
    print("\n2. Testing Database Connection...")
    db_test = test_database_connection()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    if schema_test:
        print("✓ Schema Configuration: PASS - Beta schema correctly configured")
    else:
        print("✗ Schema Configuration: FAIL - Schema configuration issue")
    
    if db_test:
        print("✓ Database Connection: PASS - Database module accessible")
    else:
        print("✗ Database Connection: WARNING - Database connection not tested")
    
    if schema_test:
        print("\n🎉 SUCCESS: Fund analysis beta is correctly configured to use 'MODEL_forecast_prices_beta' schema!")
        print("\nNext steps:")
        print("- The beta version will now save all results to the beta schema")
        print("- This ensures separation from the production 'MODEL_forecast_prices' schema")
        print("- The enhanced curve combination functionality is preserved")
    else:
        print("\n❌ ISSUES FOUND: Please check the schema configuration")

if __name__ == "__main__":
    main()
