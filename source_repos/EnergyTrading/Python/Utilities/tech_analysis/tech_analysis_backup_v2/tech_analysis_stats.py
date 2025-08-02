import pandas as pd

class TechAnalysisStats:
    """Handles moving average calculations for spread data."""

    def __init__(self, spread_df):
        """
        Initialize TechAnalysisStats with a specific spread dataframe.
        
        :param spread_df: Pandas DataFrame containing spread data
        """
        if isinstance(spread_df, pd.DataFrame):
            self.spread_df = spread_df
            print("Spread data successfully set.")
        else:
            raise ValueError("Invalid data format. Expected a Pandas DataFrame.")

    def get_moving_average(self, window=20, type='exp'):
        """
        Calculate the moving average for the spread dataframe.
        """
        type_dict = {
            'exp': self._get_exp_ma,
            'simple': self._get_simple_ma
        }

        if type not in type_dict:
            raise ValueError(f"Invalid moving average type: {type}. Choose 'exp' or 'simple'.")

        spread_df = self.spread_df.copy()
        spread_df['mean'] = type_dict[type](spread_df, window)  # Call function with window parameter

        return spread_df
    
    def get_statistics(self):
        spread = self.spread_df.sort_index().copy()
        returns = spread.diff().dropna()
        descriptive_stats = returns.describe()
        return returns, descriptive_stats

    def _get_exp_ma(self, df, window):
        """Calculate Exponential Moving Average (EMA)."""
        return df.ewm(span=window, adjust=False).mean()

    def _get_simple_ma(self, df, window):
        """Calculate Simple Moving Average (SMA)."""
        return df.rolling(window=window).mean()
