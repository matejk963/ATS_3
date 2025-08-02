"""
Test your exact original code that was failing
"""

print("🚀 TESTING YOUR ORIGINAL CODE...")

try:
    import refinitiv.data as rd
    print("✅ Import successful")
    
    print("Opening session...")
    rd.open_session()
    print("✅ Session opened")
    
    print("Calling get_history...")
    df = rd.get_history(
        universe="LCOc1",
        fields=["CLOSE", "VOLUME", "BID", "ASK"],
        start="2025-07-17",
        end="2025-07-17",
        interval="1s"
    )
    
    print("✅ get_history call successful!")
    print(f"Result shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    
    if not df.empty:
        print("Sample data:")
        print(df.head())
    else:
        print("No data returned (likely session/authentication issue)")
        
except ValueError as e:
    if "numpy.dtype size changed" in str(e):
        print(f"❌ STILL HAVE NUMPY ISSUE: {e}")
    else:
        print(f"❌ Different ValueError: {e}")
        
except Exception as e:
    print(f"❌ Other error: {type(e).__name__}: {e}")
    
print("🎯 Test completed!")
