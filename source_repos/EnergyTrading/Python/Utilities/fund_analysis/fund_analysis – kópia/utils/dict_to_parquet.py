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

def load_nested_dict_from_parquet(base_directory, dates=None):
    """
    Traverse a directory structure and rebuild a nested dictionary where parquet files are
    loaded as DataFrames and directory levels represent nested keys. Load data for specified
    dates, with each date as a key in the resulting dictionary.

    Parameters:
        base_directory (str): The base directory containing the saved folder structure and parquet files.
        dates (list of str, optional): A list of specific dates (e.g., ["YYYY-MM-DD", ...]) to extract data for.
                                       Defaults to None, meaning all data is loaded.

    Returns:
        dict: A nested dictionary with dates as keys and DataFrames loaded from parquet files.
    """
    def load_recursive(current_path):
        nested_dict = {}
        for item in os.listdir(current_path):
            item_path = os.path.join(current_path, item)

            if os.path.isdir(item_path):
                # If the item is a directory, recurse into it
                key = item
                nested_dict[key] = load_recursive(item_path)
            elif item.endswith(".parquet"):
                # If the item is a parquet file, load it as a DataFrame
                key = os.path.splitext(item)[0]
                try:
                    nested_dict[key] = pd.read_parquet(item_path)
                except Exception as e:
                    print(f"Failed to load parquet file '{item_path}': {e}")
        return nested_dict

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
                    result[spread_type][date] = load_recursive(date_path)
                else:
                    print(f"Date folder '{date}' not found under spread type '{spread_type}'.")
        else:
            # Load all data if no specific dates are specified
            result[spread_type] = load_recursive(spread_type_path)

    return result



test = load_nested_dict_from_parquet(base_directory='//192.168.10.91/d/data/Data/Spot/Model/Forecasts/Nominal',
                                        date=dt.datetime(2025,1,15).strftime('%Y-%m-%d_%H-%M-%S'))