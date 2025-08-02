#!/usr/bin/env python3
"""
Enhanced MCP Server Deployment and Management Script
"""
import os
import sys
import subprocess
import json
import time
import psutil
from pathlib import Path

def check_dependencies():
    """Check if all required dependencies are installed."""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        'fastmcp',
        'psycopg2',
        'pandas',
        'psutil'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package} - MISSING")
    
    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Run: pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies satisfied")
    return True

def check_configuration():
    """Check if configuration files exist and are valid."""
    print("\n🔧 Checking configuration...")
    
    config_files = [
        "mcp.json",
        ".vscode/settings.json"
    ]
    
    all_good = True
    
    for config_file in config_files:
        if Path(config_file).exists():
            try:
                with open(config_file, 'r') as f:
                    json.load(f)
                print(f"✓ {config_file}")
            except json.JSONDecodeError as e:
                print(f"✗ {config_file} - Invalid JSON: {e}")
                all_good = False
        else:
            print(f"✗ {config_file} - Missing")
            all_good = False
    
    if all_good:
        print("✅ Configuration files valid")
    else:
        print("❌ Configuration issues found")
    
    return all_good

def start_server(background=False):
    """Start the MCP server."""
    print(f"\n🚀 Starting MCP server {'in background' if background else ''}...")
    
    server_file = "mcp-server-enhanced.py"
    if not Path(server_file).exists():
        print(f"❌ Server file not found: {server_file}")
        return None
    
    try:
        if background:
            process = subprocess.Popen(
                [sys.executable, server_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Give it a moment to start
            time.sleep(2)
            
            if process.poll() is None:
                print(f"✅ Server started with PID {process.pid}")
                return process
            else:
                stdout, stderr = process.communicate()
                print(f"❌ Server failed to start")
                print(f"STDOUT: {stdout}")
                print(f"STDERR: {stderr}")
                return None
        else:
            # Run in foreground
            result = subprocess.run([sys.executable, server_file])
            return result
            
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return None

def stop_server():
    """Stop any running MCP server processes."""
    print("\n🛑 Stopping MCP server...")
    
    stopped = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                if 'mcp-server-enhanced.py' in cmdline:
                    proc.kill()
                    proc.wait()
                    stopped += 1
                    print(f"✓ Stopped process {proc.info['pid']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if stopped > 0:
        print(f"✅ Stopped {stopped} server process(es)")
    else:
        print("ℹ️ No running server processes found")

def test_server_health():
    """Test if the server is responding."""
    print("\n🏥 Testing server health...")
    
    # For now, just check if the process is running
    # In a full implementation, you could make HTTP requests to test endpoints
    
    running = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                if 'mcp-server-enhanced.py' in cmdline:
                    running = True
                    print(f"✓ Server process running (PID: {proc.info['pid']})")
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if running:
        print("✅ Server appears to be healthy")
    else:
        print("❌ Server not running")
    
    return running

def deploy():
    """Complete deployment process."""
    print("🚀 Enhanced Energy Trading MCP Server Deployment")
    print("=" * 60)
    
    # Check prerequisites
    if not check_dependencies():
        return False
    
    if not check_configuration():
        return False
    
    # Stop any existing server
    stop_server()
    
    # Start new server
    process = start_server(background=True)
    if not process:
        return False
    
    # Test health
    time.sleep(3)
    if test_server_health():
        print("\n🎉 Deployment successful!")
        print(f"Server is running with PID {process.pid}")
        print("\nNext steps:")
        print("1. Configure VS Code to connect to the MCP server")
        print("2. Test the available tools")
        print("3. Monitor logs for any issues")
        return True
    else:
        print("\n❌ Deployment failed - server health check failed")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  {sys.argv[0]} deploy     - Deploy the server")
        print(f"  {sys.argv[0]} start      - Start the server")
        print(f"  {sys.argv[0]} stop       - Stop the server")
        print(f"  {sys.argv[0]} status     - Check server status")
        print(f"  {sys.argv[0]} test       - Run health checks")
        return 1
    
    command = sys.argv[1].lower()
    
    if command == "deploy":
        success = deploy()
        return 0 if success else 1
    elif command == "start":
        process = start_server(background=True)
        return 0 if process else 1
    elif command == "stop":
        stop_server()
        return 0
    elif command == "status":
        health = test_server_health()
        return 0 if health else 1
    elif command == "test":
        deps = check_dependencies()
        config = check_configuration()
        health = test_server_health()
        return 0 if (deps and config and health) else 1
    else:
        print(f"Unknown command: {command}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
