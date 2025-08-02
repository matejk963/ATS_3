"""
Test script to verify the NumPy/SciPy fix for Refinitiv Data Library
"""

print("🔧 TESTING NUMPY/SCIPY FIX...")

try:
    print("1. Testing NumPy import...")
    import numpy as np
    print(f"   ✅ NumPy {np.__version__} imported successfully")
    
    print("2. Testing SciPy import...")
    import scipy
    print(f"   ✅ SciPy {scipy.__version__} imported successfully")
    
    print("3. Testing scipy.interpolate (the problematic module)...")
    from scipy import interpolate
    print("   ✅ scipy.interpolate imported successfully")
    
    print("4. Testing scipy.special (another problematic module)...")
    from scipy import special
    print("   ✅ scipy.special imported successfully")
    
    print("5. Testing refinitiv.data import...")
    import refinitiv.data as rd
    print("   ✅ refinitiv.data imported successfully")
    
    print("6. Testing get_history method availability...")
    has_get_history = hasattr(rd, 'get_history')
    print(f"   ✅ get_history available: {has_get_history}")
    
    if has_get_history:
        print("\n🎉 SUCCESS! The NumPy/SciPy compatibility issue is FIXED!")
        print("Your original rd.get_history() code should now work.")
    else:
        print("\n⚠️  get_history not available - different issue")
        
except ValueError as e:
    if "numpy.dtype size changed" in str(e):
        print(f"\n❌ STILL HAVE NUMPY COMPATIBILITY ISSUE:")
        print(f"   Error: {e}")
        print("\n🔧 ADDITIONAL FIX NEEDED:")
        print("   Try: conda install scipy numpy -c conda-forge --force-reinstall")
    else:
        print(f"\n❌ Different ValueError: {e}")
        
except Exception as e:
    print(f"\n❌ Other error: {type(e).__name__}: {e}")

print("\n" + "="*60)
