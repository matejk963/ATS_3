import pandas as pd
import os
import datetime as dt

def save_nested_dict_to_parquet(data_dict, base_directory):
    """
    Recursively traverse a nested dictionary and save DataFrames as parquet files in a directory structure
    that mirrors the dictionary's keys.

    Parameters:
        data_dict (dict): A nested dictionary where the innermost values are DataFrames.
        base_directory (str): The base directory where the folder structure and parquet files will be saved.
    """
    def sanitize_key(key):
        """Convert keys to strings and sanitize them to ensure valid file and directory names."""
        if isinstance(key, (int, float, pd.Timestamp)):
            key = str(key)
        return str(key).replace(" ", "_").replace(":", "-").replace("/", "-").replace("\\", "-")

    def save_recursive(current_dict, current_path):
        for key, value in current_dict.items():
            # Sanitize the key to ensure it is a valid directory or file name
            sanitized_key = sanitize_key(key)

            # Construct the new path
            new_path = os.path.join(current_path, sanitized_key)

            if isinstance(value, dict):
                # Create a folder for the current key if it doesn't exist
                os.makedirs(new_path, exist_ok=True)
                save_recursive(value, new_path)
            elif isinstance(value, pd.DataFrame):
                # Save the DataFrame as a parquet file
                parquet_file = os.path.join(new_path + ".parquet")
                value.to_parquet(parquet_file)
            else:
                raise ValueError(f"Unexpected value type: {type(value)} at key: {key}")

    # Start the recursive saving process
    save_recursive(data_dict, base_directory)
    
import os
import pandas as pd


def load_nested_dict_from_parquet(base_directory, keys=None, dates=None):
    """
    Traverse a directory structure and rebuild a nested dictionary where parquet files are
    loaded as DataFrames and directory levels represent nested keys. Dates are handled
    separately, and keys specify the path to traverse below the dates.

    Parameters:
        base_directory (str): The base directory containing the saved folder structure and parquet files.
        keys (list of str, optional): A list of keys to specify the path to traverse below the dates.
                                      Defaults to None, meaning all data is loaded.
        dates (list of str, optional): A list of specific dates (e.g., ["YYYY-MM-DD", ...]) to extract data for.
                                       Defaults to None, meaning all dates are loaded.

    Returns:
        dict: A nested dictionary with dates as keys and DataFrames loaded from parquet files.
    """
    def load_recursive(current_path, depth):
        nested_dict = {}
        for item in os.listdir(current_path):
            item_path = os.path.join(current_path, item)

            if os.path.isdir(item_path):
                # Handle directories
                key = item

                # If keys are provided, only recurse if the key matches the current level
                if keys is None or (depth < len(keys) and key == keys[depth]):
                    nested_dict[key] = load_recursive(item_path, depth + 1)

            elif item.endswith(".parquet"):
                # Handle parquet files
                key = os.path.splitext(item)[0]
                try:
                    nested_dict[key] = pd.read_parquet(item_path)
                except Exception as e:
                    print(f"Failed to load parquet file '{item_path}': {e}")

        return nested_dict

    # Start the recursive loading process
    result = {}
    for spread_type in os.listdir(base_directory):
        spread_type_path = os.path.join(base_directory, spread_type)

        if not os.path.isdir(spread_type_path):
            continue

        if dates:
            # Load data for the specified dates
            result[spread_type] = {}
            for date in dates:
                date_path = os.path.join(spread_type_path, date)
                if os.path.exists(date_path):
                    result[spread_type][date] = load_recursive(date_path, depth=0)
                else:
                    print(f"Date folder '{date}' not found under spread type '{spread_type}'.")
        else:
            # Load all data if no specific dates are specified
            result[spread_type] = {}
            for date in os.listdir(spread_type_path):
                date_path = os.path.join(spread_type_path, date)
                if os.path.isdir(date_path):
                    result[spread_type][date] = load_recursive(date_path, depth=0)

    return result


if __name__=='__main__':
    test = load_nested_dict_from_parquet(base_directory='//192.168.10.91/d/data/Data/Spot/Model/Forecasts/Nominal',
                                            dates=[dt.datetime(2025,1,15).strftime('%Y-%m-%d_%H-%M-%S')])