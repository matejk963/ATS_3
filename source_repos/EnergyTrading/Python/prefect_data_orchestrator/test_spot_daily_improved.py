#!/usr/bin/env python3
"""
Test script for the improved spot daily flow
Runs with test=True for yesterday's data
"""

import sys
import os
from datetime import datetime, timedelta

# Add the current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import the improved flow
from flow_spot_daily_improved import spot_daily_improved

def test_improved_flow():
    """Test the improved spot daily flow with all countries in production mode"""
    
    print("🧪 Testing improved spot daily flow...")
    print(f"📅 Testing for yesterday: {(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')}")
    print("🌍 Using all countries: ['at', 'be', 'cz', 'de', 'dkw', 'dke', 'fr', 'hu', 'nl', 'sk', 'si', 'ro', 'bg', 'hr', 'gr', 'es', 'it_nord']")
    print("🔬 Running with test=False (production mode)")
    print("-" * 60)
    
    # Use all countries from the production deployment
    all_countries = ['at', 'be', 'cz', 'de', 'dkw', 'dke',
                     'fr', 'hu', 'nl', 'sk', 'si', 'ro',
                     'bg', 'hr', 'gr', 'es', 'it_nord']
    
    try:
        # Run the improved flow with test=False (production mode)
        result = spot_daily_improved(countries=all_countries, test=False)
        
        print("\n✅ Test Results:")
        print("=" * 40)
        for country, status in result.items():
            emoji = "✅" if "Success" in str(status) else "⚠️" if "Error" in str(status) else "ℹ️"
            print(f"{emoji} {country.upper()}: {status}")
        
        print("\n🎉 Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_improved_flow()
