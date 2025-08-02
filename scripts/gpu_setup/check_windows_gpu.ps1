# Windows GPU and Driver Check Script
# Run this in Windows PowerShell (not WSL2)

Write-Host "🔍 Windows GPU and NVIDIA Driver Check" -ForegroundColor Cyan
Write-Host "=" * 50

# Check GPU hardware
Write-Host "`n📱 Graphics Hardware:" -ForegroundColor Yellow
try {
    $gpus = Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
    if ($gpus) {
        foreach ($gpu in $gpus) {
            Write-Host "✅ GPU: $($gpu.Name)" -ForegroundColor Green
            Write-Host "   Video Processor: $($gpu.VideoProcessor)" -ForegroundColor White
            Write-Host "   Driver Version: $($gpu.DriverVersion)" -ForegroundColor White
            Write-Host "   Driver Date: $($gpu.DriverDate)" -ForegroundColor White
        }
    } else {
        Write-Host "❌ No NVIDIA GPU detected" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Error checking GPU: $_" -ForegroundColor Red
}

# Check NVIDIA driver via nvidia-smi
Write-Host "`n🔧 NVIDIA Driver Status:" -ForegroundColor Yellow
try {
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($nvidiaSmi) {
        Write-Host "✅ nvidia-smi found at: $($nvidiaSmi.Source)" -ForegroundColor Green
        Write-Host "`nDriver Information:" -ForegroundColor White
        & nvidia-smi --query-gpu=driver_version,cuda_version --format=csv,noheader,nounits 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ NVIDIA driver working" -ForegroundColor Green
        } else {
            Write-Host "❌ NVIDIA driver not responding" -ForegroundColor Red
        }
    } else {
        Write-Host "❌ nvidia-smi not found - drivers may not be installed" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Error checking nvidia-smi: $_" -ForegroundColor Red
}

# Check CUDA compatibility
Write-Host "`n⚡ CUDA Compatibility:" -ForegroundColor Yellow
try {
    if (Test-Path "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA") {
        $cudaVersions = Get-ChildItem "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA" | Where-Object { $_.PSIsContainer }
        if ($cudaVersions) {
            Write-Host "✅ CUDA Toolkits found:" -ForegroundColor Green
            foreach ($version in $cudaVersions) {
                Write-Host "   - $($version.Name)" -ForegroundColor White
            }
        }
    } else {
        Write-Host "⚠️ CUDA Toolkit not found (not required for WSL2)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Error checking CUDA: $_" -ForegroundColor Red
}

# WSL2 specific check
Write-Host "`n🐧 WSL2 GPU Support:" -ForegroundColor Yellow
try {
    $wslVersion = wsl --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ WSL2 available" -ForegroundColor Green
        
        # Check if nvidia libraries exist in WSL
        $nvmlCheck = wsl sh -c "ls /usr/lib/wsl/lib/nvidia* 2>/dev/null | wc -l" 2>$null
        if ($nvmlCheck -and [int]$nvmlCheck -gt 0) {
            Write-Host "✅ NVIDIA libraries found in WSL2" -ForegroundColor Green
        } else {
            Write-Host "❌ NVIDIA libraries not found in WSL2" -ForegroundColor Red
        }
    } else {
        Write-Host "⚠️ WSL2 not available or not responding" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Error checking WSL2: $_" -ForegroundColor Red
}

# Recommendations
Write-Host "`n💡 Recommendations:" -ForegroundColor Cyan
Write-Host "=" * 30

$driverFound = $false
try {
    & nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>$null | ForEach-Object {
        $version = [float]($_ -replace '\..*', '')
        if ($version -ge 525) {
            Write-Host "✅ Driver version $_ supports CUDA 12.x" -ForegroundColor Green
            $driverFound = $true
        } else {
            Write-Host "⚠️ Driver version $_ may not support CUDA 12.x" -ForegroundColor Yellow
            Write-Host "   Recommended: Update to 525.60.11 or newer" -ForegroundColor White
        }
    }
} catch {
    # nvidia-smi failed
}

if (-not $driverFound) {
    Write-Host "🔧 Action Required:" -ForegroundColor Red
    Write-Host "1. Download latest NVIDIA drivers from:" -ForegroundColor White
    Write-Host "   https://www.nvidia.com/Download/index.aspx" -ForegroundColor Blue
    Write-Host "2. Install drivers and restart Windows" -ForegroundColor White
    Write-Host "3. Re-run this script to verify" -ForegroundColor White
}

Write-Host "`n🏁 Check complete!" -ForegroundColor Cyan