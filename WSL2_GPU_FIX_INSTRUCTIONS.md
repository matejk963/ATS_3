# WSL2 GPU Access Fix Instructions

## 🎯 **Issue Summary**
- ✅ **Windows GPU**: RTX 4080 SUPER with Driver 577.00 working perfectly
- ✅ **CuPy & CUDA Runtime**: 12.9 working in WSL2
- ❌ **Problem**: CUDA Driver shows 0 in WSL2 (should show 577000)
- ❌ **Symptom**: "GPU access blocked by the operating system"

## 🔧 **Quick Test After Any Fix**
```bash
cd /mnt/c/Users/krajcovic/Documents/GitHub/ATS_3
python test_gpu_bypass.py
```
**Success = CUDA Driver Version > 0 (not 0)**

---

## 🚀 **Solution Methods (Try in Order)**

### **Method 1: Full Windows Restart (Most Common Fix)**
```powershell
# Windows PowerShell (as Admin)
shutdown /r /t 0
```
**After restart → Test with `python test_gpu_bypass.py`**

### **Method 2: Enable WSL2 GPU Features**
```powershell
# Windows PowerShell (as Admin)
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -All
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All

# Check Hyper-V
$hyperv = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
if ($hyperv -and $hyperv.State -eq "Disabled") {
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All
}

# Restart WSL
wsl --shutdown
wsl
```

### **Method 3: Install WSL Preview (Better GPU Support)**
```powershell
# Windows PowerShell (as Admin)
winget install Microsoft.WSL.Preview
wsl --shutdown
wsl
```

### **Method 4: Fresh Ubuntu Install**
```powershell
# BACKUP FIRST!
wsl --export Ubuntu ubuntu_backup.tar

# Fresh install
wsl --unregister Ubuntu
wsl --install Ubuntu
```

---

## ✅ **Expected Success Output**
```
🔧 Step 2: Testing CUDA Versions...
✅ CUDA Runtime: 12.9 (raw: 12090)
✅ CUDA Driver Version: 577000  ← Should NOT be 0!
🎉 CUDA Driver detected! GPU should be accessible

🧮 Step 3: Testing Basic GPU Computation...
✅ GPU computation successful: sum([1,2,3,4,5]) = 15

💾 Step 4: Testing GPU Memory Access...
✅ GPU Memory Info:
   Total: 16.4GB
   Free: 14.1GB

🎉 BASIC GPU ACCESS: ✅ SUCCESS
🎉 PIPELINE TEST: ✅ SUCCESS
Your GPU implementation is FULLY FUNCTIONAL!
```

---

## 🏃 **After GPU Working - Run These**
```bash
# Comprehensive tests
python tests/technical_indicators/test_large_dataset_validation.py

# Performance benchmarks  
python scripts/run_phase3_benchmarks.py

# Quick validation
python tests/technical_indicators/test_quick_implementation_check.py
```

---

## 📋 **Status Tracking**
- [ ] Method 1: Windows restart attempted
- [ ] Method 2: WSL features enabled
- [ ] Method 3: WSL Preview installed
- [ ] Method 4: Fresh Ubuntu install
- [ ] GPU working (CUDA Driver > 0)
- [ ] Pipeline tests passing
- [ ] Performance benchmarks completed

**Current Status**: Attempting fixes for WSL2 GPU passthrough issue