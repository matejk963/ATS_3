"""
Metrics validator for exact comparison with data_factory_reg.py output.
TDD implementation - following sklearn precision matching pattern.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Union


class MetricsValidator:
    """
    Validate that calculated metrics match data_factory_reg.py exactly.
    
    Following CLAUDE.md TDD principles - exact floating point precision like sklearn tests.
    """
    
    def __init__(self, precision_tolerance: float = 1e-10):
        """
        Initialize validator with precision tolerance.
        
        Args:
            precision_tolerance: Maximum allowed difference (default: 1e-10 like sklearn tests)
        """
        self.precision_tolerance = precision_tolerance
    
    def compare_metrics(self, calculated_metrics: Dict[str, Any], 
                       expected_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare calculated metrics with expected metrics from data_factory_reg.py.
        
        Args:
            calculated_metrics: Metrics calculated from ObserverStrategy
            expected_metrics: Expected metrics from data_factory_reg.py
            
        Returns:
            Dict with comparison results including exact_match, differences, max_difference
        """
        # Validate metric keys match
        keys_match = self._validate_metric_keys(calculated_metrics, expected_metrics)
        if not keys_match:
            return {
                'exact_match': False,
                'differences': 'Metric keys do not match',
                'max_difference': float('inf')
            }
        
        # Compare each metric with precision tolerance
        differences = {}
        all_differences = []
        
        for key in expected_metrics.keys():
            if key in calculated_metrics:
                result = self._compare_single_metric(
                    calculated_metrics[key], 
                    expected_metrics[key], 
                    key
                )
                differences[key] = result
                all_differences.append(result['abs_difference'])
            else:
                differences[key] = {
                    'exact_match': False,
                    'abs_difference': float('inf'),
                    'error': 'Key missing in calculated metrics'
                }
                all_differences.append(float('inf'))
        
        # Calculate overall results
        max_difference = max(all_differences) if all_differences else 0.0
        exact_match = all(
            diff_result.get('exact_match', False) 
            for diff_result in differences.values()
        )
        
        return {
            'exact_match': exact_match,
            'differences': differences,
            'max_difference': max_difference
        }
    
    def _compare_single_metric(self, calculated: Union[float, np.ndarray], 
                              expected: Union[float, np.ndarray],
                              metric_name: str) -> Dict[str, Any]:
        """Compare single metric with floating point precision"""
        try:
            # Convert to numpy for consistent comparison
            calc_val = np.array(calculated)
            exp_val = np.array(expected)
            
            # Calculate absolute difference
            abs_diff = np.abs(calc_val - exp_val)
            
            # For arrays, use max difference
            if abs_diff.ndim > 0:
                max_abs_diff = np.max(abs_diff)
            else:
                max_abs_diff = float(abs_diff)
            
            # Check if within tolerance
            exact_match = max_abs_diff < self.precision_tolerance
            
            return {
                'exact_match': exact_match,
                'abs_difference': max_abs_diff,
                'calculated_value': calculated,
                'expected_value': expected,
                'metric_name': metric_name
            }
            
        except Exception as e:
            return {
                'exact_match': False,
                'abs_difference': float('inf'),
                'error': f"Comparison failed: {str(e)}",
                'metric_name': metric_name
            }
    
    def _validate_metric_keys(self, calculated_metrics: Dict[str, Any],
                             expected_metrics: Dict[str, Any]) -> bool:
        """Validate that all expected metric keys are present"""
        expected_keys = set(expected_metrics.keys())
        calculated_keys = set(calculated_metrics.keys())
        
        # All expected keys must be present in calculated
        return expected_keys.issubset(calculated_keys)
    
    def _calculate_max_difference(self, calculated_metrics: Dict[str, Any],
                                 expected_metrics: Dict[str, Any]) -> float:
        """Calculate maximum absolute difference across all metrics"""
        max_diff = 0.0
        
        for key in expected_metrics.keys():
            if key in calculated_metrics:
                try:
                    calc_val = np.array(calculated_metrics[key])
                    exp_val = np.array(expected_metrics[key])
                    abs_diff = np.abs(calc_val - exp_val)
                    
                    if abs_diff.ndim > 0:
                        current_max = np.max(abs_diff)
                    else:
                        current_max = float(abs_diff)
                    
                    max_diff = max(max_diff, current_max)
                except:
                    return float('inf')  # Error in comparison
        
        return max_diff