import paramiko
import time
from collections import deque

from environment import TP_SFTP as FTP

def get_last_n_lines_from_sftp(host, port, username, password, file_path, n):
    # Connect to the SFTP server
    transport = paramiko.Transport((host, port))
    transport.connect(username=username, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)
    
    # Use a deque to store the last n lines
    buffer = deque(maxlen=n)
    
    # Open the remote file
    with sftp.file(file_path, 'r') as remote_file:
        # Iterate through each line in the remote file
        for line in remote_file:
            buffer.append(line)
    
    sftp.close()
    transport.close()
    
    return list(buffer)

def main():
    host = FTP.host
    port = 5567  # Default SFTP port
    username = FTP.user
    password = FTP.passwd
    file_path = '/'
    n = 10  # Number of last lines to read
    
    while True:
        try:
            last_n_lines = get_last_n_lines_from_sftp(host, port, username, password, file_path, n)
            for line in last_n_lines:
                print(line, end='')
            print("\n" + "="*40 + "\n")  # Separator for readability
        except Exception as e:
            print(f"An error occurred: {e}")
        
        # Wait for 5 seconds
        time.sleep(5)

if __name__ == "__main__":
    main()
