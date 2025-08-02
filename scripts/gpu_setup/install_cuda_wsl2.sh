#!/bin/bash
# CUDA Toolkit Installation for WSL2
# Target: Fix missing libnvrtc.so.12 for CuPy GPU acceleration

echo "🚀 Installing CUDA Toolkit for WSL2..."
echo "Target: CUDA 12.8 runtime libraries"

# Step 1: Add NVIDIA package repository
echo "📦 Adding NVIDIA repository..."
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt-get update

# Step 2: Install CUDA Toolkit
echo "⬇️ Installing CUDA Toolkit 12.8..."
sudo apt-get -y install cuda-toolkit-12-8

# Step 3: Set environment variables
echo "🔧 Setting up environment variables..."
echo 'export PATH=/usr/local/cuda-12.8/bin${PATH:+:${PATH}}' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}' >> ~/.bashrc

# Step 4: Reload environment
echo "🔄 Reloading environment..."
source ~/.bashrc

# Step 5: Verify installation
echo "✅ Verifying CUDA installation..."
nvcc --version
ls -la /usr/local/cuda-12.8/lib64/libnvrtc.so*

echo "🎯 Installation complete! Please restart your terminal and test with:"
echo "python validate_gpu_setup.py"