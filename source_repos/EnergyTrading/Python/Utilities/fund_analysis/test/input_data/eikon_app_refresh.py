import subprocess
import time
import psutil
import os

# Path to the application EXE file
APP_PATH = r"C:\Users\krajcovic\AppData\Local\Refinitiv\Refinitiv Workspace\RefinitivWorkspace.exe"

try:
    subprocess.Popen(f'start "" "{APP_PATH}"', shell=True)
    print("Application started successfully!")
except Exception as e:
    print(f"Error starting application: {e}")