"""
Test suite for DataFetcher implementation

Tests all core functionality including date calculations, contract validation,
and data fetching workflows.
"""

import sys
import os
import pytest
from datetime import datetime, time
import pandas as pd

# Add project root to path
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3')

from src.core.data_fetcher import (
    DeliveryDateCalculator, DateRangeResolver, ContractValidator, 
    DataFetcher, test_tpdata_connectivity
)


class TestDeliveryDateCalculator:
    """Test delivery date calculation functionality"""
    
    def test_monthly_contracts(self):
        """Test monthly contract date calculation"""
        calc = DeliveryDateCalculator()
        
        # July 2025
        result = calc.calc_delivery_date('m', '07_25')
        expected = datetime(2025, 7, 1)
        assert result == expected
        
        # December 2024
        result = calc.calc_delivery_date('m', '12_24')
        expected = datetime(2024, 12, 1)
        assert result == expected
    
    def test_quarterly_contracts(self):
        """Test quarterly contract date calculation"""
        calc = DeliveryDateCalculator()
        
        # Q2 2025 (April-June)
        result = calc.calc_delivery_date('q', '2_25')
        expected = datetime(2025, 4, 1)
        assert result == expected
        
        # Q4 2024 (October-December)
        result = calc.calc_delivery_date('q', '4_24')
        expected = datetime(2024, 10, 1)
        assert result == expected
    
    def test_yearly_contracts(self):
        """Test yearly contract date calculation"""
        calc = DeliveryDateCalculator()
        
        # Year 2025
        result = calc.calc_delivery_date('y', '25')
        expected = datetime(2025, 1, 1)
        assert result == expected
        
        # Year 2030
        result = calc.calc_delivery_date('y', '30')
        expected = datetime(2030, 1, 1)
        assert result == expected
    
    def test_invalid_tenor(self):
        """Test invalid tenor raises ValueError"""
        calc = DeliveryDateCalculator()
        
        with pytest.raises(ValueError, match="Unknown tenor"):
            calc.calc_delivery_date('invalid', '07_25')


class TestDateRangeResolver:
    """Test date range resolution functionality"""
    
    def test_lookback_calculation(self):
        """Test business day lookback calculation"""
        resolver = DateRangeResolver()
        
        # 90 business days before July 1, 2025
        delivery_date = datetime(2025, 7, 1)
        start_date, end_date = resolver.resolve_date_range(delivery_date, 90)
        
        # End date should be June 30, 2025
        assert end_date == datetime(2025, 6, 30)
        
        # Start date should be approximately 90 business days before
        # (allowing for weekends, roughly 4.5 months back)
        assert start_date < datetime(2025, 3, 1)
        assert start_date > datetime(2025, 1, 1)
    
    def test_short_lookback(self):
        """Test short lookback period"""
        resolver = DateRangeResolver()
        
        # 5 business days
        delivery_date = datetime(2025, 7, 1)
        start_date, end_date = resolver.resolve_date_range(delivery_date, 5)
        
        assert end_date == datetime(2025, 6, 30)
        # 5 business days is about 1 week
        assert (end_date - start_date).days >= 5
        assert (end_date - start_date).days <= 10


class TestContractValidator:
    """Test contract configuration validation"""
    
    def test_valid_explicit_dates_contract(self):
        """Test valid contract with explicit dates"""
        validator = ContractValidator()
        
        contract = {
            'market': 'de',
            'tenor': 'm',
            'contract': '07_25',
            'start_date': '2025-04-01',
            'end_date': '2025-06-30'
        }
        
        assert validator.validate_contract(contract) == True
    
    def test_valid_lookback_contract(self):
        """Test valid contract with lookback configuration"""
        validator = ContractValidator()
        
        contract = {
            'market': 'fr',
            'tenor': 'q',
            'contract': '2_25',
            'lookback_days': 120
        }
        
        assert validator.validate_contract(contract) == True
    
    def test_missing_required_fields(self):
        """Test validation fails for missing required fields"""
        validator = ContractValidator()
        
        contract = {
            'market': 'de',
            'tenor': 'm'
            # Missing 'contract' field
        }
        
        with pytest.raises(ValueError, match="Missing required field: contract"):
            validator.validate_contract(contract)
    
    def test_invalid_market(self):
        """Test validation fails for invalid market"""
        validator = ContractValidator()
        
        contract = {
            'market': 'invalid_market',
            'tenor': 'm',
            'contract': '07_25',
            'lookback_days': 90
        }
        
        with pytest.raises(ValueError, match="Invalid market"):
            validator.validate_contract(contract)
    
    def test_invalid_tenor(self):
        """Test validation fails for invalid tenor"""
        validator = ContractValidator()
        
        contract = {
            'market': 'de',
            'tenor': 'invalid_tenor',
            'contract': '07_25',
            'lookback_days': 90
        }
        
        with pytest.raises(ValueError, match="Invalid tenor"):
            validator.validate_contract(contract)
    
    def test_no_date_configuration(self):
        """Test validation fails when no date configuration provided"""
        validator = ContractValidator()
        
        contract = {
            'market': 'de',
            'tenor': 'm',
            'contract': '07_25'
            # No date configuration
        }
        
        with pytest.raises(ValueError, match="must specify either explicit dates"):
            validator.validate_contract(contract)
    
    def test_both_date_configurations(self):
        """Test validation fails when both date configurations provided"""
        validator = ContractValidator()
        
        contract = {
            'market': 'de',
            'tenor': 'm',
            'contract': '07_25',
            'start_date': '2025-04-01',
            'end_date': '2025-06-30',
            'lookback_days': 90  # Both configurations
        }
        
        with pytest.raises(ValueError, match="cannot specify both"):
            validator.validate_contract(contract)


class TestDataFetcher:
    """Test main DataFetcher functionality"""
    
    def test_initialization(self):
        """Test DataFetcher initialization"""
        try:
            fetcher = DataFetcher(
                trading_hours=(9, 17),
                allowed_broker_ids=[1441]
            )
            assert fetcher.trading_hours == (9, 17)
            assert fetcher.allowed_broker_ids == [1441]
        except RuntimeError as e:
            # Expected if TPData not available in test environment
            assert "TPData not available" in str(e)
    
    def test_resolve_explicit_dates(self):
        """Test contract date resolution with explicit dates"""
        try:
            fetcher = DataFetcher()
        except RuntimeError:
            pytest.skip("TPData not available")
        
        contract_config = {
            'market': 'de',
            'tenor': 'm',
            'contract': '07_25',
            'start_date': '2025-04-01',
            'end_date': '2025-06-30'
        }
        
        start_date, end_date = fetcher._resolve_contract_dates(contract_config)
        
        assert start_date == datetime(2025, 4, 1)
        assert end_date == datetime(2025, 6, 30)
    
    def test_resolve_lookback_dates(self):
        """Test contract date resolution with lookback"""
        try:
            fetcher = DataFetcher()
        except RuntimeError:
            pytest.skip("TPData not available")
        
        contract_config = {
            'market': 'de',
            'tenor': 'm',
            'contract': '07_25',
            'lookback_days': 90
        }
        
        start_date, end_date = fetcher._resolve_contract_dates(contract_config)
        
        # Should resolve to dates around 90 business days before July 1, 2025
        assert end_date == datetime(2025, 6, 30)
        assert start_date < datetime(2025, 4, 1)


def test_connectivity():
    """Test TPData connectivity"""
    result = test_tpdata_connectivity()
    # Should return True if TPData is available, False otherwise
    assert isinstance(result, bool)


class TestIntegration:
    """Integration tests for complete workflow"""
    
    def test_example_usage_explicit_dates(self):
        """Test example usage with explicit dates"""
        # This is the usage pattern from the plan
        contracts = [
            {
                'market': 'de', 'tenor': 'm', 'contract': '07_25',
                'start_date': '2025-04-01', 'end_date': '2025-06-30'
            },
            {
                'market': 'fr', 'tenor': 'q', 'contract': '2_25', 
                'start_date': '2024-10-01', 'end_date': '2024-12-31'
            }
        ]
        
        # Validate contracts
        for contract in contracts:
            assert ContractValidator.validate_contract(contract) == True
    
    def test_example_usage_lookback(self):
        """Test example usage with lookback configuration"""
        # This is the usage pattern from the plan
        contracts = [
            {
                'market': 'de', 'tenor': 'm', 'contract': '07_25',
                'lookback_days': 90  # 90 days before July 1, 2025
            },
            {
                'market': 'fr', 'tenor': 'q', 'contract': '2_25',
                'lookback_days': 120  # 120 days before Q2 2025 start
            }
        ]
        
        # Validate contracts  
        for contract in contracts:
            assert ContractValidator.validate_contract(contract) == True
        
        # Test date resolution
        calc = DeliveryDateCalculator()
        resolver = DateRangeResolver()
        
        for contract in contracts:
            delivery_date = calc.calc_delivery_date(contract['tenor'], contract['contract'])
            start_date, end_date = resolver.resolve_date_range(delivery_date, contract['lookback_days'])
            
            # Verify dates make sense
            assert start_date < end_date
            assert end_date < delivery_date


if __name__ == "__main__":
    # Run basic connectivity test
    print("Running TPData connectivity test...")
    test_connectivity()
    
    print("\nRunning delivery date calculation tests...")
    calc = DeliveryDateCalculator()
    
    test_cases = [
        ('m', '07_25', datetime(2025, 7, 1)),
        ('q', '2_25', datetime(2025, 4, 1)),
        ('y', '25', datetime(2025, 1, 1)),
    ]
    
    for tenor, contract, expected in test_cases:
        result = calc.calc_delivery_date(tenor, contract)
        assert result == expected
        print(f"✅ {tenor}:{contract} -> {result}")
    
    print("\nAll tests passed!")