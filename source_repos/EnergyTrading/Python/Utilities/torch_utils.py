import os
import platform
import psutil
import torch
from datetime import datetime
from collections import defaultdict

def print_line(length=60):
    print("\n" + "-" * length)

def print_section(title, length=50):
    print(f"\n== {title} {'=' * ((length-6) - len(title))}")


def format_bytes(size):
    """Convert memory size to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

def device_agnostic(mode='gpu', cpu_threads=4):
    # ASCII Art and Header
    BANNER = f"""
  ____       _____              _     
 |  _ \ _   |_   _|__  _ __ ___| |__  
 | |_) | | | || |/ _ \| '__/ __| '_ \ 
 |  __/| |_| || | (_) | | | (__| | | |
 |_|    \__, ||_|\___/|_|  \___|_| |_|
        |___/                         
    """

    def print_header():
        print(BANNER)



    def human_bytes(size):
        units = ('B', 'KB', 'MB', 'GB', 'TB')
        i = 0
        while size >= 1024 and i < len(units)-1:
            size /= 1024
            i += 1
        return f"{size:.2f} {units[i]}"

    print_header()
    
    if torch.cuda.is_available() and mode == 'gpu':
        # CUDA Device Section
        props = torch.cuda.get_device_properties(0)
        print_section("NVIDIA GPU STATUS")
        device = f"cuda"
        
        # GPU Details
        print(f"  Device Name: {torch.cuda.get_device_name(0)}")
        print(f"  CUDA Version: {torch.version.cuda}")
        print(f"  Stream multiprocessors: {props.multi_processor_count}")  # Approximation: 64 cores per SM
        print(f"  Compute Capability: {props.major}.{props.minor}")
        
        # Memory Stats
        free, total = torch.cuda.mem_get_info(0)
        used = total - free
        print(f"\n  Memory Usage:")
        print(f"    Total: {human_bytes(total)}")
        print(f"    Used:  {human_bytes(used)} ({used/total:.1%})")
        print(f"    Free:  {human_bytes(free)}")

    elif torch.backends.mps.is_available():
        # Apple Silicon Section
        print_section("APPLE SILICON STATUS")
        device = f"mps"
        print(f"  Metal GPU Acceleration Available")

    else:
        # CPU Fallback Section
        print_section("CPU MODE")
        device = f"cpu"
    
        # CPU Details
        total_cores = os.cpu_count()
        reserved_cores = 2
        pytorch_cores = cpu_threads if cpu_threads < total_cores - reserved_cores else total_cores - reserved_cores
        
        print(f"  No GPU acceleration available")
        print(f"\n  CPU Configuration:")
        print(f"    Physical Cores: {psutil.cpu_count(logical=False)}")
        print(f"    Logical Cores:  {total_cores}")
        print(f"    Allocated Cores: {pytorch_cores}")

        # Set thread configuration
        torch.set_num_threads(pytorch_cores)
        os.environ["OMP_NUM_THREADS"] = str(pytorch_cores)
        os.environ["MKL_NUM_THREADS"] = str(pytorch_cores)

        # Final Output
        print("\n" + "─" * 60)
        print(f"Active device: {device}\n")

    return device


class TensorTracker:
    def __init__(self):
        self.tensor_info = defaultdict(dict)
        self._register_hooks()
    
    def _get_tensor_size(self, tensor):
        """Calculate tensor memory footprint"""
        return tensor.element_size() * tensor.nelement()

    def _track_tensor(self, tensor, name=None):
        """Record tensor metadata"""
        if tensor.device.type == 'cuda':
            self.tensor_info[id(tensor)] = {
                'shape': tuple(tensor.shape),
                'dtype': str(tensor.dtype),
                'device': tensor.device,
                'size_mb': self._get_tensor_size(tensor) / 1024**2,
                'name': name or 'anonymous'
            }

    def _register_hooks(self):
        """Hook into tensor creation methods"""
        original_to = torch.Tensor.to
        original_cuda = torch.Tensor.cuda
        
        def new_to(tensor, *args, **kwargs):
            result = original_to(tensor, *args, **kwargs)
            if result.device.type == 'cuda':
                self._track_tensor(result)
            return result
            
        def new_cuda(tensor, *args, **kwargs):
            result = original_cuda(tensor, *args, **kwargs)
            self._track_tensor(result)
            return result
            
        torch.Tensor.to = new_to
        torch.Tensor.cuda = new_cuda

    def get_memory_summary(self):
        """Generate formatted memory report"""
        report = ["\nTensor VRAM Summary:"]
        total = 0
        for tid, info in self.tensor_info.items():
            report.append(
                f"{info['name']} - Shape: {info['shape']} | "
                f"Dtype: {info['dtype']} | "
                f"Size: {info['size_mb']:.2f}MB"
            )
            total += info['size_mb']
        report.append(f"\nTotal VRAM Used: {total:.2f}MB")
        return "\n".join(report)
