# CUDA Driver Update Guide for WSL2

## 🎯 **Problem Identified**

Your system status:
- **CUDA Runtime Version**: 12.9 (from CuPy 13.5.1)
- **CUDA Driver Version**: 0 (insufficient)
- **Error**: "GPU access blocked by the operating system"
- **Root Cause**: Windows NVIDIA drivers are outdated

## 🔧 **Solution: Update Windows NVIDIA Drivers**

### **Step 1: Check Your Graphics Card**

Open PowerShell **on Windows** (not WSL) and run:
```powershell
# Check GPU model
Get-WmiObject Win32_VideoController | Select Name, VideoProcessor
```

Or check in Device Manager:
1. Windows + X → Device Manager
2. Expand "Display adapters"
3. Note your NVIDIA GPU model

### **Step 2: Download Latest NVIDIA Drivers**

**🔗 Download from NVIDIA:**
1. Go to: https://www.nvidia.com/Download/index.aspx
2. Select your GPU model and Windows version
3. Download the **Game Ready Driver** or **Studio Driver**

**Minimum Required:**
- **CUDA 12.x support**: Driver version **525.60.11** or newer
- **Recommended**: Latest available driver (usually 540.x+)

### **Step 3: Install NVIDIA Drivers on Windows**

**Important**: Install on your **Windows host**, not in WSL2!

1. **Close all GPU applications** (games, AI tools, etc.)
2. **Run the NVIDIA installer as Administrator**
3. Choose **Custom Installation**
4. Select:
   - ✅ Graphics Driver
   - ✅ CUDA Development (if available)
   - ✅ GeForce Experience (optional)
5. **Restart Windows** after installation

### **Step 4: Verify Installation**

**On Windows** (PowerShell):
```powershell
# Check driver version
nvidia-smi
```

**In WSL2**:
```bash
# Should now work
/usr/lib/wsl/lib/nvidia-smi

# Test CUDA driver
python -c "
import cupy as cp
print(f'CUDA Runtime: {cp.cuda.runtime.runtimeGetVersion()}')
print(f'CUDA Driver: {cp.cuda.runtime.driverGetVersion()}')
print('GPU Available:', cp.cuda.is_available())
"
```

## ⚡ **Quick Test After Update**

Run our GPU validation:
```bash
cd /mnt/c/Users/krajcovic/Documents/GitHub/ATS_3
python tests/feature_engineering/test_gpu_quick_validation.py
```

Expected output after fix:
```
🚀 Quick GPU Validation Test
========================================
🔍 GPU Availability Check...
✅ CuPy version: 13.5.1
✅ Basic GPU operation: 15
✅ GPU Memory: X.XGB free / Y.YGB total

📦 Pipeline Import Test...
✅ Pipeline imported successfully
✅ NumPy pipeline initialized
✅ GPU pipeline initialized with memory management
✅ GPU stats: X.XGB free

🧪 Small Dataset Test...
📊 Test data: 1000 rows
✅ CPU MACD: 0.028s, 1000 valid values
✅ GPU MACD: 0.010s, 1000 valid values
🏃 Speedup: 2.8x

📊 VALIDATION SUMMARY
========================================
GPU Available: ✅
Pipeline Import: ✅
Small Dataset Test: ✅

🎉 GPU Implementation: ✅ READY FOR LARGE DATASET TESTING
```

## 🚨 **Troubleshooting**

### **If GPU still not detected:**

1. **Check Windows NVIDIA Control Panel**:
   - Right-click desktop → NVIDIA Control Panel
   - Help → System Information
   - Verify driver version

2. **Restart WSL2**:
   ```powershell
   # In Windows PowerShell
   wsl --shutdown
   wsl
   ```

3. **Check Windows GPU access**:
   ```powershell
   # In Windows PowerShell
   nvidia-smi
   ```

4. **Verify WSL2 NVIDIA support**:
   ```bash
   # In WSL2
   ls -la /usr/lib/wsl/lib/nvidia*
   ```

### **If CUDA version mismatch:**

The driver needs to support CUDA 12.9. Minimum driver versions:
- **CUDA 12.0**: Driver 525.60.11+
- **CUDA 12.1**: Driver 530.30.02+
- **CUDA 12.2**: Driver 535.54.03+
- **CUDA 12.9**: Driver 545.23.06+

## 🎯 **Expected Performance After Fix**

Once drivers are updated, you should see:
- **GPU acceleration**: 2-5x speedup over CPU
- **Large dataset support**: 500K+ data points
- **Memory management**: Automatic chunking working
- **All indicators**: MACD, ATR, Candles, Swing Points on GPU

## 📞 **Next Steps After Driver Update**

1. ✅ Verify GPU detection
2. ✅ Run comprehensive tests
3. ✅ Benchmark performance improvements
4. ✅ Deploy GPU-accelerated pipeline

---

**Remember**: WSL2 uses Windows NVIDIA drivers, so the fix must be applied on your Windows host system, not inside WSL2.