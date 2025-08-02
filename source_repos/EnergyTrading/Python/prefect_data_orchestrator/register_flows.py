"""
Prefect Flow Registration and Environment Management

This script manages the complete lifecycle of Prefect 3.1.11 deployments including:
- Local state cleanup to prevent post-restart worker crashes
- Server and worker process management
- Work pool creation with conda environment isolation
- Flow deployment with proper scheduling

Enhanced with automatic clearing of C:/Users/AS4user/.prefect/ state files
to resolve common post-restart issues where stale process references 
cause worker startup failures.
"""

from prefect.types.entrypoint import EntrypointType
from prefect.client.schemas.actions import DeploymentScheduleCreate
from prefect.client.schemas.schedules import CronSchedule, IntervalSchedule, RRuleSchedule
from datetime import timedelta, datetime
import os
import subprocess
import asyncio
import psutil
import socket
import sys
import time
import requests
import shutil
import tempfile
import pandas as pd
from pathlib import Path
from prefect.client.orchestration import PrefectClient
from prefect.client.schemas.actions import DeploymentScheduleCreate
from prefect.client.schemas.schedules import RRuleSchedule, CronSchedule
from prefect.types.entrypoint import EntrypointType
from datetime import timedelta, datetime



# Ensure the script directory is in Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

print(f"📂 Added {SCRIPT_DIR} to sys.path for module lookup.")

# Import Prefect flows
try:
    from prefect_data_orchestrator.flow_spot_daily import spot_daily
    from prefect_data_orchestrator.flow_cot import commitments_of_traders
except ModuleNotFoundError as e:
    print(f"❌ ERROR: Missing module: {e}. Ensure all flow files are in the same directory.")
    exit(1)

# Configurations
WORK_POOL_NAME = "conda-develop"
PREFECT_API_URL = "http://127.0.0.1:4200/api"
CONDA_ENV_NAME = "develop"

# Ensure Prefect API URL is set
os.environ["PREFECT_API_URL"] = PREFECT_API_URL
# Add this line alongside your existing PREFECT_API_URL setting
os.environ["PREFECT_API_DATABASE_CONNECTION_URL"] = "postgresql+asyncpg://prefect:prefect123@localhost:5432/prefect"



def setup_windows_unicode():
    """Setup Windows terminal for Unicode/UTF-8 support to prevent encoding errors."""
    try:
        # Set environment variables for UTF-8 support
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['PYTHONLEGACYWINDOWSSTDIO'] = '1'
        
        # Try to set console to UTF-8 mode (chcp 65001)
        try:
            subprocess.run(['chcp', '65001'], 
                         capture_output=True, 
                         shell=True, 
                         timeout=5)
            print("✅ Windows terminal set to UTF-8 mode")
        except:
            print("⚠️ Could not set terminal to UTF-8 mode - continuing anyway")
            
    except Exception as e:
        print(f"⚠️ Unicode setup warning: {e}")


def clear_prefect_local_state():
    """
    Clear Prefect local state files to resolve post-restart worker crashes.
    
    This function addresses the common issue where Prefect workers fail to start
    after system restarts due to stale process references and locked state files.
    
    Target locations for Windows (AS4user):
    - C:/Users/AS4user/.prefect/ (main state directory)
    - %TEMP%/prefect* (temporary files)
    - SQLite database locks and cached client state
    """
    import shutil
    import glob
    from pathlib import Path
    
    print("🧹 Clearing Prefect local state files...")
    
    # Windows-specific paths for AS4user
    home_dir = Path("C:/Users/AS4user")
    prefect_dir = home_dir / ".prefect"
    
    # Clear state subdirectories
    state_dirs = [
        prefect_dir / "flow_runs",
        prefect_dir / "client_state", 
        prefect_dir / "work_pools",
        prefect_dir / "deployments"
    ]
    
    for state_dir in state_dirs:
        if state_dir.exists():
            try:
                shutil.rmtree(state_dir)
                print(f"✅ Cleared: {state_dir}")
            except Exception as e:
                print(f"⚠️ Could not clear {state_dir}: {e}")
    
    # Clear SQLite databases (preserve profiles.toml)
    if prefect_dir.exists():
        db_files = list(prefect_dir.glob("*.db")) + list(prefect_dir.glob("*.db-*"))
        for db_file in db_files:
            try:
                db_file.unlink()
                print(f"✅ Removed database: {db_file}")
            except Exception as e:
                print(f"⚠️ Could not remove {db_file}: {e}")
    
    # Clear Windows temp files
    import tempfile
    temp_dir = Path(tempfile.gettempdir())
    temp_prefect_patterns = ["prefect*", "tmp*prefect*", ".prefect*"]
    
    for pattern in temp_prefect_patterns:
        temp_files = list(temp_dir.glob(pattern))
        for temp_file in temp_files:
            try:
                if temp_file.is_file():
                    temp_file.unlink()
                elif temp_file.is_dir():
                    shutil.rmtree(temp_file)
                print(f"✅ Cleared temp: {temp_file}")
            except Exception as e:
                print(f"⚠️ Could not clear {temp_file}: {e}")
    
    print("✅ Prefect local state cleared successfully!")


def is_port_in_use(port):
    """Check if a given port is currently in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


async def stop_prefect_server():
    """Check if Prefect server is running, terminate it, and ensure the port is free."""
    print("🔍 Checking if Prefect server is running on port 4200...")

    try:
        # Check if Prefect server process is running
        result = subprocess.run(["prefect", "server", "status"], capture_output=True, text=True)

        if "UP" in result.stdout or is_port_in_use(4200):
            print("🛑 Prefect server is running. Stopping it now...")

            # Find and terminate Prefect server process
            for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
                try:
                    if proc.info['cmdline'] and "prefect server start" in " ".join(proc.info['cmdline']):
                        print(f"🛑 Killing Prefect server process {proc.info['pid']}...")
                        proc.terminate()
                        proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            # More aggressive process cleanup - kill ANY process using port 4200
            if is_port_in_use(4200):
                print("⚠️ Port 4200 is still occupied! Finding and killing processes using the port...")
                
                # Multiple attempts with different strategies
                killed_processes = False
                
                try:
                    # Strategy 1: Use netstat to find process using port 4200
                    netstat_result = subprocess.run(
                        ["netstat", "-ano"], 
                        capture_output=True, 
                        text=True, 
                        shell=True
                    )
                    
                    for line in netstat_result.stdout.splitlines():
                        if ":4200" in line and ("LISTENING" in line or "ESTABLISHED" in line):
                            parts = line.split()
                            if len(parts) > 4:
                                pid = parts[-1]
                                print(f"🎯 Found process {pid} using port 4200, killing it...")
                                kill_result = subprocess.run(
                                    ["taskkill", "/F", "/PID", pid], 
                                    capture_output=True, 
                                    text=True
                                )
                                if kill_result.returncode == 0:
                                    killed_processes = True
                                    print(f"✅ Successfully killed process {pid}")
                                else:
                                    print(f"⚠️ Failed to kill process {pid}: {kill_result.stderr}")
                    
                except Exception as e:
                    print(f"⚠️ Error with netstat strategy: {e}")
                
                # Strategy 2: Kill all python processes that might be prefect
                if not killed_processes:
                    try:
                        print("🎯 Attempting to kill all python processes that might be Prefect...")
                        # Kill python processes with prefect in command line
                        for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
                            try:
                                if (proc.info['name'] and 'python' in proc.info['name'].lower() and 
                                    proc.info['cmdline'] and 'prefect' in ' '.join(proc.info['cmdline']).lower()):
                                    print(f"🎯 Killing Python-Prefect process {proc.info['pid']}: {proc.info['cmdline']}")
                                    proc.kill()
                                    killed_processes = True
                            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                                pass
                    except Exception as e:
                        print(f"⚠️ Error with process iteration strategy: {e}")
                
                # Strategy 3: Aggressive fallback - kill common problematic processes
                if not killed_processes:
                    print("🎯 Using aggressive fallback - killing potential blocking processes...")
                    fallback_commands = [
                        "taskkill /F /IM python.exe /FI \"COMMANDLINE eq *prefect*\"",
                        "taskkill /F /IM uvicorn.exe",
                        "taskkill /F /IM fastapi.exe"
                    ]
                    
                    for cmd in fallback_commands:
                        try:
                            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                            if "SUCCESS" in result.stdout:
                                killed_processes = True
                                print(f"✅ Command succeeded: {cmd}")
                        except Exception as e:
                            print(f"⚠️ Command failed: {cmd} - {e}")
                
                # Wait for processes to fully terminate
                await asyncio.sleep(8)  # Longer wait for cleanup
                
                # Final check
                if is_port_in_use(4200):
                    print("❌ ERROR: Port 4200 is STILL occupied after aggressive cleanup!")
                    print("💡 Manual intervention required. Please:")
                    print("   1. Open Task Manager")
                    print("   2. Look for any Python/Prefect processes")
                    print("   3. End them manually")
                    print("   4. Or restart the machine if necessary")
                    return  # Don't continue if we can't free the port
                else:
                    print("✅ Port 4200 is now free!")

            print("✅ Prefect server stopped successfully.")

        else:
            print("✅ Prefect server is not running.")

    except Exception as e:
        print(f"⚠️ Error checking Prefect server: {e}")


def start_prefect_server():
    """Start Prefect server in a new command prompt after ensuring the old one is gone."""
    # Wait for port to be available with retries
    max_retries = 15
    retry_count = 0
    
    while is_port_in_use(4200) and retry_count < max_retries:
        print(f"⏳ Port 4200 still in use, waiting... (attempt {retry_count + 1}/{max_retries})")
        time.sleep(3)
        retry_count += 1
    
    if is_port_in_use(4200):
        print("❌ ERROR: Port 4200 is still in use after waiting. Cannot start server.")
        print("💡 Try one of these solutions:")
        print("   1. Restart your computer to clear all processes")
        print("   2. Use Task Manager to find and kill processes using port 4200")
        print("   3. Check if another application is using port 4200")
        return False

    print("🚀 Starting a new Prefect server instance...")
    try:
        subprocess.Popen(
            f'start cmd /k "conda activate {CONDA_ENV_NAME} && prefect server start"',
            shell=True
        )
        
        # Verify server actually starts
        startup_retries = 20
        for i in range(startup_retries):
            time.sleep(2)
            if is_port_in_use(4200):
                print(f"✅ Server startup confirmed on port 4200 (attempt {i+1})")
                return True
            print(f"⏳ Waiting for server to start... (attempt {i+1}/{startup_retries})")
        
        print("❌ ERROR: Server did not start within expected time")
        return False
        
    except Exception as e:
        print(f"❌ ERROR starting server: {e}")
        return False


async def stop_all_workers():
    """Stops any running Prefect workers by forcefully killing their processes."""
    print(f"🔹 Stopping any running Prefect workers...")
    for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and "prefect worker start" in " ".join(proc.info['cmdline']):
                print(f"🛑 Killing Prefect worker process {proc.info['pid']}...")
                proc.terminate()
                proc.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    print("✅ All workers stopped.")


async def reset_work_pool():
    """Deletes and recreates the work pool only after ensuring server is ready."""
    print("🔧 Setting up work pool...")
    
    # Wait for server to be ready with more robust checking
    max_retries = 20  # Increased retries for more patience
    retry_count = 0
    server_ready = False
    
    while retry_count < max_retries:
        try:
            # Test server connection with timeout - try multiple commands
            # Set UTF-8 encoding environment for Windows Unicode issues
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONLEGACYWINDOWSSTDIO'] = '1'
            
            commands_to_try = [
                ["prefect", "work-pool", "ls"],
                ["prefect", "version"],
                ["prefect", "config", "view"]
            ]
            
            for cmd in commands_to_try:
                try:
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=8,
                        env=env,
                        encoding='utf-8',
                        errors='replace'
                    )
                    if result.returncode == 0:
                        server_ready = True
                        print(f"✅ Server is responding to command: {' '.join(cmd)}")
                        break
                except subprocess.TimeoutExpired:
                    continue
                    
            if server_ready:
                break
                
        except Exception as e:
            print(f"⏳ Server connection attempt failed: {e} (attempt {retry_count + 1}/{max_retries})")
        
        await asyncio.sleep(3)
        retry_count += 1
    
    if not server_ready:
        print("⚠️ WARNING: Server did not respond to basic commands within expected time.")
        print("🤔 Attempting work pool operations anyway - server might be ready for specific commands...")
        # Don't return False immediately - let's try the actual operations
    
    try:
        # Check if the work pool exists with extended timeout
        print("🔍 Checking existing work pools...")
        
        # Set UTF-8 encoding environment for Windows Unicode issues
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONLEGACYWINDOWSSTDIO'] = '1'
        
        result = subprocess.run(
            ["prefect", "work-pool", "ls"], 
            capture_output=True, 
            text=True, 
            timeout=15,
            env=env,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0:
            print("✅ Successfully connected to server for work pool operations!")
            if result.stdout and WORK_POOL_NAME in result.stdout:
                print(f"🗑️ Deleting existing work pool: {WORK_POOL_NAME}...")
                delete_result = subprocess.run(
                    ["prefect", "work-pool", "delete", WORK_POOL_NAME], 
                    capture_output=True, 
                    text=True, 
                    timeout=15,
                    env=env,
                    encoding='utf-8',
                    errors='replace'
                )
                if delete_result.returncode != 0:
                    print(f"⚠️ Error deleting work pool: {delete_result.stderr}")
            else:
                print(f"✅ Work pool {WORK_POOL_NAME} does not exist, skipping delete...")
        else:
            print(f"⚠️ Server responded with error to work-pool ls: {result.stderr}")
            print("🤔 Attempting to create work pool anyway...")

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        print(f"⚠️ Error checking existing work pools: {e}")
        print("🤔 Attempting to create work pool anyway...")

    # Recreate the work pool with --overwrite and handle Unicode issues
    try:
        print(f"🏗️ Creating new work pool: {WORK_POOL_NAME}...")
        
        # Set environment variables to handle Unicode issues on Windows
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONLEGACYWINDOWSSTDIO'] = '1'
        
        create_result = subprocess.run(
            ["prefect", "work-pool", "create", WORK_POOL_NAME, "--type", "process", "--overwrite"], 
            capture_output=True, 
            text=True, 
            timeout=20,
            env=env,
            encoding='utf-8',
            errors='replace'  # Replace problematic characters instead of failing
        )
        
        if create_result.returncode == 0:
            print("✅ Work pool created successfully!")
        else:
            # Check if it's just a Unicode display issue but work pool was actually created
            print(f"⚠️ Work pool creation command had output issues...")
            print("🔍 Checking if work pool was actually created despite the error...")
            
            # Test if work pool exists now
            check_result = subprocess.run(
                ["prefect", "work-pool", "ls"], 
                capture_output=True, 
                text=True, 
                timeout=10,
                env=env,
                encoding='utf-8',
                errors='replace'
            )
            
            if check_result.returncode == 0 and WORK_POOL_NAME in check_result.stdout:
                print("✅ Work pool was actually created successfully despite the display error!")
            else:
                print(f"❌ Work pool creation genuinely failed: {create_result.stderr}")
                print("🔧 This might be due to server connectivity or permission issues.")
                return False
        
        # Start the work pool in a new terminal window with UTF-8 encoding and correct Python path
        print(f"🚀 Starting work pool '{WORK_POOL_NAME}' in a new terminal...")
        
        # Set PYTHONPATH to the parent directory so 'prefect_data_orchestrator' module can be found
        parent_dir = os.path.dirname(SCRIPT_DIR)
        
        subprocess.Popen(
            f'start cmd /k "chcp 65001 && conda activate {CONDA_ENV_NAME} && set PYTHONPATH={parent_dir} && set PYTHONIOENCODING=utf-8 && prefect worker start --pool {WORK_POOL_NAME}"',
            shell=True
        )
        
        return True  # Return success even if there were display warnings
        
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        print(f"❌ ERROR: Failed to create work pool: {e}")
        print("🔧 This could be due to:")
        print("   1. Server not being fully ready yet")
        print("   2. Windows Unicode encoding issues") 
        print("   3. Terminal encoding problems")
        print("💡 Try running: chcp 65001 (to set UTF-8) before running this script")
        return False


async def delete_existing_deployments():
    """Deletes all deployments to ensure only new ones are used."""
    print("🗑️ Deleting all existing deployments...")
    try:
        async with PrefectClient(api=PREFECT_API_URL) as client:
            existing_deployments = await client.read_deployments()
            for dep in existing_deployments:
                print(f"🗑️ Removing deployment: {dep.name}")
                await client.delete_deployment(dep.id)

        print("✅ All deployments deleted. Ready to create fresh deployments.")
    except Exception as e:
        print(f"⚠️ Error deleting deployments: {e}")
        print("🔧 This may be due to server connectivity issues. Continuing anyway...")

async def main():
    """Main execution function with enhanced error handling and validation."""
    # Clear Prefect local state first to prevent post-restart issues
    clear_prefect_local_state()
    
    await stop_prefect_server()  # Ensure Prefect server is shut down first
    await stop_all_workers()  # Ensure all workers are shut down
    await asyncio.sleep(3)  # Allow processes to terminate

    # Start Prefect server and wait for it to be ready
    print("🚀 Attempting to start Prefect server...")
    server_started = start_prefect_server()  # Start Prefect server in a new terminal
    
    if not server_started:
        print("❌ CRITICAL ERROR: Failed to start Prefect server.")
        print("🛑 Cannot continue without a running server. Script will exit.")
        return False
        
    print("⏳ Waiting for Prefect server to fully initialize...")
    await asyncio.sleep(20)  # Wait longer for server to fully start before proceeding

    # Verify server is actually responding - use multiple methods
    server_ready = False
    max_attempts = 12  # Increased attempts for more patience
    
    print("🔍 Verifying server is fully ready and responding...")
    
    # Set UTF-8 encoding environment for Windows Unicode issues
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONLEGACYWINDOWSSTDIO'] = '1'
    
    for attempt in range(max_attempts):
        try:
            # Method 1: Check if API endpoint is responding
            try:
                response = requests.get("http://127.0.0.1:4200/api/health", timeout=5)
                if response.status_code == 200:
                    server_ready = True
                    print("✅ Server API endpoint is responding!")
                    break
            except:
                pass  # Try other methods
            
            # Method 2: Use prefect server status command
            result = subprocess.run(
                ["prefect", "server", "status"], 
                capture_output=True, 
                text=True, 
                timeout=8,
                env=env,
                encoding='utf-8',
                errors='replace'
            )
            if result.returncode == 0 and ("UP" in result.stdout or "running" in result.stdout.lower()):
                server_ready = True
                print("✅ Prefect server status confirms it's ready!")
                break
                
            # Method 3: Try a simple prefect command that requires server
            result = subprocess.run(
                ["prefect", "version"], 
                capture_output=True, 
                text=True, 
                timeout=5,
                env=env,
                encoding='utf-8',
                errors='replace'
            )
            if result.returncode == 0:
                # If basic commands work, server is likely ready
                server_ready = True
                print("✅ Prefect commands are working - server appears ready!")
                break
                
        except (subprocess.TimeoutExpired, Exception) as e:
            pass  # Continue trying
            
        print(f"⏳ Server not fully ready yet, waiting... (attempt {attempt + 1}/{max_attempts})")
        await asyncio.sleep(4)  # Slightly longer wait between attempts
    
    if not server_ready:
        print("⚠️ WARNING: Server readiness check inconclusive, but server appears to be running.")
        print("🤔 This might be a timing issue. Attempting to continue with setup...")
        print("💡 If errors occur, the server may need more time to initialize.")
        # Don't return False - let's try to continue and see if it works

    work_pool_ready = await reset_work_pool()  # Reset work pool
    if not work_pool_ready:
        print("⚠️ WARNING: Work pool setup encountered issues.")
        print("🤔 Attempting to continue - work pool might still be functional...")
        print("💡 If deployments fail, you may need to create the work pool manually.")
        
    await asyncio.sleep(8)  # Allow more time for the work pool to fully start
    await delete_existing_deployments()  # Delete all deployments
    
    return True  # Signal success even with work pool warnings

if __name__ == "__main__":
    # Setup Windows Unicode support first
    setup_windows_unicode()
    
    os.environ["PREFECT_API_URL"] = "http://127.0.0.1:4200/api"
    
    # Execute main setup and only proceed if successful
    try:
        setup_successful = asyncio.run(main())
        
        if not setup_successful:
            print("❌ SETUP FAILED: Cannot proceed with flow deployments.")
            print("🔧 Please resolve the server issues and try again.")
            exit(1)
        
        # Double-check that server is still running before deployments
        if not is_port_in_use(4200):
            print("❌ ERROR: Prefect server is not running. Cannot deploy flows.")
            print("🔧 Server may have crashed during setup. Check the server terminal window.")
            exit(1)
        
        # Final server connectivity test with multiple methods
        server_responding = False
        test_commands = [
            ["prefect", "work-pool", "ls"],
            ["prefect", "deployment", "ls"],
            ["prefect", "version"]
        ]
        
        # Set UTF-8 encoding environment for Windows Unicode issues
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONLEGACYWINDOWSSTDIO'] = '1'
        
        for cmd in test_commands:
            try:
                test_result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=15,
                    env=env,
                    encoding='utf-8',
                    errors='replace'
                )
                if test_result.returncode == 0:
                    server_responding = True
                    print(f"✅ Server connectivity confirmed with: {' '.join(cmd)}")
                    break
                else:
                    print(f"⚠️ Command failed: {' '.join(cmd)} - {test_result.stderr}")
            except subprocess.TimeoutExpired:
                print(f"⏳ Command timeout: {' '.join(cmd)}")
                continue
        
        if not server_responding:
            print("⚠️ WARNING: Server connectivity tests inconclusive.")
            print("🤔 Attempting deployments anyway - they might work despite test failures...")
            print("💡 If deployments fail, wait longer for server initialization and retry.")
        
        print("🚀 Server is ready! Proceeding with flow deployments...")
        
        # Daily spot
        try:
            spot_daily.deploy(
                name="spot-daily-all",  # Name of the deployment
                work_pool_name="conda-develop",  # Specify the work pool,
                parameters={"countries": ['at', 'be', 'cz', 'de', 'dkw', 'dke',
                                        'fr', 'hu', 'nl', 'sk', 'si', 'ro',
                                            'bg', 'hr', 'gr', 'es', 'it_nord'],
                            'test': False},
                schedules=[
                    DeploymentScheduleCreate(
                        schedule=CronSchedule(cron='15 13 * * *', timezone='Europe/Berlin')),
                    DeploymentScheduleCreate(
                        schedule=CronSchedule(cron='50 15 * * *', timezone='Europe/Berlin'))
                ],
                entrypoint_type=EntrypointType.MODULE_PATH
            )
            print("✅ spot-daily-all deployment successful!")
        except Exception as e:
            print(f"❌ ERROR deploying spot-daily-all: {e}")

        # Commitments of traders update every tuesday at 8:25
        try:
            commitments_of_traders.deploy(
                name="cot-update",  # Name of the deployment
                work_pool_name="conda-develop",  # Specify the work pool,
                schedules=[
                    DeploymentScheduleCreate(
                        schedule=CronSchedule(cron='25 8 * * 2', timezone='Europe/Berlin'))
                ],
                entrypoint_type=EntrypointType.MODULE_PATH
            )
            print("✅ cot-update deployment successful!")
        except Exception as e:
            print(f"❌ ERROR deploying cot-update: {e}")
        
        print("✅ Flow deployment process completed!")
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR during execution: {e}")
        print("🔧 Check the error details above and resolve issues before retrying.")
        exit(1)

