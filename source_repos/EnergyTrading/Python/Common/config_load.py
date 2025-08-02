import os

def get_config_path() -> str:
    PATH_ = os.getenv('PROJECT_CONFIG')

    # config check
    if PATH_:
        try:
            # Open the file and perform the necessary operations
            with open(PATH_) as _:
                # Read or process the file content
                pass
                # Further processing of config_data
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {PATH_}")
        except Exception as e:
            raise Exception(f"An error occurred while opening the file: {e}")
    else:
        raise ValueError('Empty environment variable: PROJECT_CONFIG')
    
    return PATH_


def get_ob_path() -> str:
    PATH_ = os.getenv('PROJECT_OBPATH')
    
    return PATH_
