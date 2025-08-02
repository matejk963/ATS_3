#!/usr/bin/env python
"""
Runner script for executing all closing logic tests with detailed reporting.
This script runs both the original test_closing_logics.py and our new extended test suite.
"""

import unittest
import sys
import time
from datetime import datetime
import os

# Import test modules
from Strategies.Modular_strategy.tests.test_closing_logics import TestClosingLogics
from Strategies.Modular_strategy.tests.test_closing_logics_extended import TestExtendedClosingLogics
from Strategies.Modular_strategy.tests.test_expanded_closing_logics import TestExpandedClosingLogics

def run_tests():
    """Run all tests with detailed reporting."""
    test_start_time = time.time()
    print(f"\n{'=' * 80}")
    print(f"EXECUTING CLOSING LOGIC TEST SUITE")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}\n")
    
    # Create test suite with all tests
    test_suite = unittest.TestSuite()
    
    # Add original test cases
    print("Loading original test cases...")
    test_suite.addTest(unittest.makeSuite(TestClosingLogics))
    
    # Add extended test cases
    print("Loading extended test cases...")
    test_suite.addTest(unittest.makeSuite(TestExtendedClosingLogics))
    
    # Add expanded comprehensive test cases
    print("Loading expanded comprehensive test cases...")
    test_suite.addTest(unittest.makeSuite(TestExpandedClosingLogics))
    
    # Configure the test runner
    runner = unittest.TextTestRunner(verbosity=2)
    
    # Run the tests
    print(f"\n{'-' * 80}")
    print("RUNNING TESTS:")
    print(f"{'-' * 80}\n")
    results = runner.run(test_suite)
    
    # Calculate timing
    test_end_time = time.time()
    test_duration = test_end_time - test_start_time
    
    # Print test summary
    print(f"\n{'-' * 80}")
    print("TEST SUMMARY:")
    print(f"{'-' * 80}")
    print(f"Total tests run: {results.testsRun}")
    print(f"Tests passed: {results.testsRun - len(results.failures) - len(results.errors)}")
    print(f"Tests failed: {len(results.failures)}")
    print(f"Tests with errors: {len(results.errors)}")
    print(f"Total execution time: {test_duration:.2f} seconds")
    
    # Print failures in detail
    if results.failures:
        print(f"\n{'-' * 80}")
        print("FAILING TESTS:")
        print(f"{'-' * 80}")
        for i, (test, traceback) in enumerate(results.failures, 1):
            print(f"\nFAILURE {i}: {test}")
            print(f"{'-' * 40}")
            print(traceback)
    
    # Print errors in detail
    if results.errors:
        print(f"\n{'-' * 80}")
        print("TEST ERRORS:")
        print(f"{'-' * 80}")
        for i, (test, traceback) in enumerate(results.errors, 1):
            print(f"\nERROR {i}: {test}")
            print(f"{'-' * 40}")
            print(traceback)
    
    print(f"\n{'=' * 80}")
    print(f"TEST SUITE EXECUTION COMPLETED")
    print(f"{'=' * 80}\n")
    
    return len(results.failures) + len(results.errors)

if __name__ == '__main__':
    # Set the working directory to the project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    os.chdir(project_root)
    
    # Run the tests and get the number of failures
    num_failures = run_tests()
    
    # Exit with non-zero status if there were failures
    sys.exit(num_failures)
