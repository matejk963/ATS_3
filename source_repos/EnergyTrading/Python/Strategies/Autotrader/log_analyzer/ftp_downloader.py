import paramiko
import time
from collections import deque
from datetime import datetime, timedelta
import re
import os

def subtract_business_day(dt):
    # Subtract one day
    one_day = timedelta(days=1)
    previous_day = dt - one_day
    
    # If the day is Sunday, subtract two more days to get to Friday
    if previous_day.weekday() == 6:  # Sunday
        previous_day -= timedelta(days=2)
    return previous_day

def check_mask(filename):
    now = datetime.now()
    one_day_ago = subtract_business_day(now).strftime('%Y-%m-%d')
    
    result = re.search(f"autotrader_child_[0-3].log.{one_day_ago}T.*.zst", filename)
    return result

def download_files_from_sftp(host, port, username, password, directory_path, local_dir, files):
    try:
        # Connect to the SFTP server
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)
        transport.banner_timeout = 30
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Create the local directory if it doesn't exist
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)

        # Download each file
        for file in files:
            remote_file_path = directory_path + '/' + file
            local_file_path = os.path.join(local_dir, file)
            print("Downloading: ", remote_file_path)
            sftp.get(remote_file_path, local_file_path)
            print(f"Downloaded {file} to {local_file_path}")
        
        sftp.close()
        transport.close()
    except Exception as e:
        print(f"An error occurred: {e}", str(e.__traceback__), e.__traceback__.tb_lineno)
        
def list_files_in_directory(host, port, username, password, directory_path, timeout=30):
    try:
        # Connect to the SFTP server
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)
        transport.banner_timeout = timeout
        sftp = paramiko.SFTPClient.from_transport(transport)
        
        # List files in the directory
        files = sftp.listdir(directory_path)
        
        filenames_to_download = []
        # Print the files
        for file in files:
            if check_mask(file):
                filenames_to_download.append(file)
        
        sftp.close()
        transport.close()
        
        return filenames_to_download
    except Exception as e:
        print(f"An error occurred: {e}")

def main():
    host = 'etc-sftp-production.visotech.com'
    port = 5567  # Default SFTP port
    username = 'autotrader-logs'
    password = 'fVYgrTmrMZsJria'
    directory_path = '/archive'  # Directory to list files from
    
    now = datetime.now()
    one_day_ago = subtract_business_day(now).strftime('%Y-%m-%d')
    local_directory = os.path.join("Z:", "autotrader_logs", one_day_ago)

    
    filenames = list_files_in_directory(host, port, username, password, directory_path)
    download_files_from_sftp(host, port, username, password, directory_path, local_directory, filenames)

        

if __name__ == "__main__":
    main()

