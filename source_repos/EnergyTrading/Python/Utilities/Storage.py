import os

def get_curr_storage_path():
    result = os.getenv('CURR_STORAGE_ENV')
    if not result:
        return 'C:/'
    else:
        return result