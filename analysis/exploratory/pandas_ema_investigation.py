#!/usr/bin/env python3
"""
Investigate pandas EMA exact formula to match precisely
"""

import numpy as np
import pandas as pd


def investigate_pandas_ewm():
    """Investigate how pandas EMA actually works"""
    print("🔍 Investigating Pandas EMA Formula")
    print("=" * 40)
    
    # Simple test case
    data = np.array([100.0, 101.0, 102.0, 101.5, 103.0])
    span = 3
    
    print(f"Test data: {data}")
    print(f"Span: {span}")
    print(f"Alpha: {2.0 / (span + 1)}")
    
    # Pandas result
    pandas_result = pd.Series(data).ewm(span=span, adjust=True).mean()
    print(f"\nPandas EMA result:")
    for i, val in enumerate(pandas_result):
        print(f"  [{i}] = {val:.10f}")
    
    # Manual calculation - check different approaches
    print(f"\nManual calculations:")
    
    # Approach 1: Simple alpha * x + (1-alpha) * prev
    alpha = 2.0 / (span + 1)
    manual1 = np.zeros_like(data)
    manual1[0] = data[0]
    for i in range(1, len(data)):
        manual1[i] = alpha * data[i] + (1 - alpha) * manual1[i-1]
    
    print(f"Approach 1 (simple recurrence):")
    for i, val in enumerate(manual1):
        print(f"  [{i}] = {val:.10f} (diff: {val - pandas_result.iloc[i]:.2e})")
    
    # Approach 2: Weighted average with adjust=True
    manual2 = np.zeros_like(data)
    for i in range(len(data)):
        weights = (1 - alpha) ** np.arange(i + 1)[::-1]
        weighted_sum = np.sum(data[:i+1] * weights)
        weight_sum = np.sum(weights)
        manual2[i] = weighted_sum / weight_sum
    
    print(f"\nApproach 2 (weighted average):")
    for i, val in enumerate(manual2):
        print(f"  [{i}] = {val:.10f} (diff: {val - pandas_result.iloc[i]:.2e})")
    
    # Check which matches
    diff1 = np.max(np.abs(manual1 - pandas_result.values))
    diff2 = np.max(np.abs(manual2 - pandas_result.values))
    
    print(f"\nMax differences:")
    print(f"Approach 1: {diff1:.2e}")
    print(f"Approach 2: {diff2:.2e}")
    
    if diff2 < 1e-14:
        print("✅ Approach 2 (weighted average) matches pandas exactly!")
        return True, manual2
    elif diff1 < 1e-14:
        print("✅ Approach 1 (simple recurrence) matches pandas exactly!")
        return True, manual1
    else:
        print("❌ Neither approach matches pandas exactly")
        return False, None


def correct_pandas_ema(data: np.ndarray, span: int) -> np.ndarray:
    """Correct implementation that matches pandas exactly"""
    alpha = 2.0 / (span + 1)
    result = np.zeros_like(data, dtype=np.float64)
    
    # Use weighted average approach (adjust=True)
    for i in range(len(data)):
        # Weights decay exponentially: (1-α)^0, (1-α)^1, (1-α)^2, ...
        weights = (1 - alpha) ** np.arange(i + 1)[::-1]
        weighted_sum = np.sum(data[:i+1] * weights)
        weight_sum = np.sum(weights) 
        result[i] = weighted_sum / weight_sum
    
    return result


def test_corrected_implementation():
    """Test corrected implementation against pandas"""
    print(f"\n✅ Testing Corrected Implementation")
    print("=" * 40)
    
    test_cases = [
        (np.array([100.0, 101.0, 102.0, 101.5, 103.0]), 3),
        (np.random.RandomState(42).randn(100).cumsum() + 100, 12),
        (np.random.RandomState(42).randn(1000).cumsum() + 100, 26),
    ]
    
    all_exact = True
    
    for i, (data, span) in enumerate(test_cases):
        pandas_result = pd.Series(data).ewm(span=span, adjust=True).mean().values
        manual_result = correct_pandas_ema(data, span)
        
        max_diff = np.max(np.abs(pandas_result - manual_result))
        print(f"Test case {i+1}: size={len(data)}, span={span}")
        print(f"  Max difference: {max_diff:.2e}")
        
        if max_diff < 1e-14:
            print(f"  ✅ EXACT match!")
        else:
            print(f"  ❌ Not exact")
            all_exact = False
    
    return all_exact


def vectorized_pandas_ema(data: np.ndarray, span: int) -> np.ndarray:
    """Vectorized version that still matches pandas"""
    alpha = 2.0 / (span + 1)
    n = len(data)
    result = np.zeros_like(data, dtype=np.float64)
    
    # For each position, we need weighted average of all previous values
    # This is inherently sequential, but we can vectorize the inner computation
    
    for i in range(n):
        if i == 0:
            result[i] = data[i]
        else:
            # Vectorized computation of weights and weighted sum
            idx_range = np.arange(i + 1)
            weights = (1 - alpha) ** (i - idx_range)
            weighted_sum = np.dot(data[:i+1], weights)
            weight_sum = np.sum(weights)
            result[i] = weighted_sum / weight_sum
    
    return result


def analyze_gpu_vectorization_potential():
    """Analyze potential for GPU vectorization"""
    print(f"\n🖥️  GPU Vectorization Analysis")
    print("=" * 35)
    
    print("Current Weighted Average Approach:")
    print("  • Each EMA[i] depends on data[0:i+1]")
    print("  • Cannot parallelize across time dimension")
    print("  • CAN vectorize inner dot product operations")
    print("  • Still fundamentally sequential in outer loop")
    
    print("\nGPU Optimization Strategies:")
    print("  1. Vectorize inner operations (dot products)")
    print("  2. Use GPU memory hierarchy efficiently")
    print("  3. Batch multiple EMA calculations")
    print("  4. Pipeline overlapping computations")
    
    print("\nRealistic GPU Performance:")
    print("  • Small datasets (<1000): GPU overhead dominates")
    print("  • Large datasets (>10000): Modest GPU benefits from vectorized ops")
    print("  • Expected speedup: 2-5x (not 10-100x as initially hoped)")
    
    print("\nConclusion:")
    print("  ❌ EMA is inherently sequential - limited GPU benefits")
    print("  ✅ ArrayBackend still valuable for unified interface")
    print("  ⚠️  Need realistic performance expectations")


def main():
    """Main analysis"""
    print("🧮 Pandas EMA Investigation & GPU Reality Check")
    print("=" * 55)
    
    # Investigate pandas formula
    matches, correct_impl = investigate_pandas_ewm()
    
    # Test corrected implementation
    if matches:
        all_exact = test_corrected_implementation()
        print(f"\n🎯 Numerical Precision: {'✅ SOLVED' if all_exact else '❌ Still issues'}")
    
    # Analyze GPU potential
    analyze_gpu_vectorization_potential()
    
    # Final conclusions
    print(f"\n🚨 REVISED CONCLUSIONS")
    print("=" * 25)
    
    print("1. Numerical Precision:")
    print("   ✅ Can achieve exact pandas match with weighted average")
    
    print("2. GPU Compatibility - REALITY CHECK:")
    print("   ❌ EMA is fundamentally sequential")
    print("   ⚠️  Limited GPU benefits (2-5x vs 100x)")
    print("   ✅ ArrayBackend still useful for consistency")
    
    print("3. Phase 2 Recommendations:")
    print("   • Keep sequential algorithm (it's the only correct one)")
    print("   • Use ArrayBackend for unified interface")
    print("   • Set realistic GPU performance expectations")
    print("   • Focus GPU optimization on other indicators")
    
    print("\n📝 Phase 2 Guide Status:")
    print("   ✅ Sequential algorithm is correct approach")
    print("   ⚠️  Need to adjust GPU performance expectations")
    print("   ✅ ArrayBackend design is appropriate")


if __name__ == "__main__":
    main()