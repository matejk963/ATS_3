# Scripts Directory

This directory contains utility scripts for project setup, benchmarking, and maintenance.

## 📁 Contents

### **GPU Setup Scripts** (`gpu_setup/`)
- `check_gpu_status.py` - Check current GPU status and availability
- `validate_gpu_setup.py` - Validate GPU environment setup
- `install_cuda_wsl2.sh` - Install CUDA drivers for WSL2

### **Benchmarking Scripts**
- `run_phase3_benchmarks.py` - Run Phase 3 GPU performance benchmarks

## 🚀 Usage

### GPU Setup Validation
```bash
# Check GPU status
python scripts/gpu_setup/check_gpu_status.py

# Validate complete GPU setup
python scripts/gpu_setup/validate_gpu_setup.py

# Install CUDA for WSL2 (if needed)
bash scripts/gpu_setup/install_cuda_wsl2.sh
```

### Performance Benchmarking
```bash
# Run comprehensive benchmarks
python scripts/run_phase3_benchmarks.py
```

## 🔧 Requirements

- Python 3.8+
- CuPy (for GPU functionality)
- NumPy
- Pandas

For GPU setup, NVIDIA drivers and CUDA toolkit are required.