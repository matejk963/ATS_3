"""
Test package for ObserverStrategy validation.

This package contains categorized tests for validating different aspects
of the ObserverStrategy implementation.
"""

# Test categories
from .test_market_data_collection import *
from .test_predictor_calculation import *
from .test_real_data_validation import *
from .test_trade_processing import *

__all__ = [
    'run_market_data_tests',
    'run_predictor_tests', 
    'run_data_validation_tests',
    'run_trade_processing_tests'
]