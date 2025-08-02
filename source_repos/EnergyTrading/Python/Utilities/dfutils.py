from typing import Optional, Union
import pandas as pd
import numpy as np
from datetime import datetime

def date_filter(
    df: pd.DataFrame, 
    date_condition: Union[str, datetime, np.datetime64], 
    column: Optional[str] = None, 
    operator: str = "=="
) -> pd.DataFrame:
    """
    Filters a DataFrame based on a date condition.

    Parameters:
        df (pd.DataFrame): The input DataFrame.
        date_condition (str | datetime | np.datetime64): The date to filter on.
        column (Optional[str]): The column to filter. If None, uses the index.
        operator (str): The comparison operator. Options: '==', '!=', '<', '>', '<=', '>='.
    
    Returns:
        pd.DataFrame: Filtered DataFrame.
    """
    # Ensure date_condition is a datetime.date object
    date_condition = pd.to_datetime(date_condition).date()

    # Get the target series (column or index)
    if column:
        target = df[column].dt.date
    else:
        target = df.index.date

    # Apply the chosen operator
    if operator == "==":
        return df[target == date_condition]
    elif operator == "!=":
        return df[target != date_condition]
    elif operator == "<":
        return df[target < date_condition]
    elif operator == ">":
        return df[target > date_condition]
    elif operator == "<=":
        return df[target <= date_condition]
    elif operator == ">=":
        return df[target >= date_condition]
    else:
        raise ValueError(f"Unsupported operator: {operator}")

def df_days_tag(df, col_name='timestamp'):
    try:
        unique_dates = df[col_name].dt.date.unique()
    except KeyError:
        raise KeyError(f"Column name ({col_name}) is not in df")
    
    # Create a dictionary to map unique dates to tags
    date_to_tag = {date: tag for tag, date in enumerate(unique_dates)}
    
    # Add a new column for the tags
    df['day'] = df['timestamp'].dt.date.map(date_to_tag)
    
    return df.copy()

def show_in_window(fig):
    import plotly.io as pio
    # Configure Plotly plot to be autosizable
    pio.renderers.default = 'browser'
    fig.update_layout(autosize=True)
    # Execute the application
    pio.show(fig)

def dict_iloc(dictionary, index: int):
    keys = [*dictionary.keys()]
    return dictionary[keys[index]]
    