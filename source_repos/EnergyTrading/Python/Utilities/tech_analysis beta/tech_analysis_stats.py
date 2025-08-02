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

    def get_moving_average(self, window=20, ma_type='exp', column_name='spread_value'): # Added column_name
        """
        Calculate the moving average for the spread dataframe.
        """
        type_dict = {
            'exp': self._get_exp_ma,
            'simple': self._get_simple_ma
        }

        if ma_type not in type_dict:
            raise ValueError(f"Invalid moving average type: {ma_type}. Choose 'exp' or 'simple'.")

        # Ensure the specified column exists
        if column_name not in self.spread_df.columns:
            raise ValueError(f"Column '{column_name}' not found in spread_df. Available columns: {self.spread_df.columns.tolist()}")

        spread_df_copy = self.spread_df.copy()
        
        # Calculate MA only on the specified column
        # Ensure the input to MA functions is a DataFrame to keep the column name for _get_bollinger_bands
        ma_series = type_dict[ma_type](spread_df_copy[[column_name]], window)
        
        # Assign the MA result to a 'mean' column in the copy
        spread_df_copy['mean'] = ma_series[column_name] # ma_series will have the original column name if input was DataFrame

        # Pass the original column_name to _get_bollinger_bands
        spread_df_copy = self._get_bollinger_bands(spread_df_copy, window, column_name=column_name)

        return spread_df_copy
    
    def get_ma_cloud(self, windows=[20, 50], ma_type='exp', column_name='spread_value'): # Added column_name
        # Pass column_name to underlying get_moving_average calls
        fast = self.get_moving_average(window=windows[0],ma_type=ma_type, column_name=column_name)
        slow = self.get_moving_average(window=windows[1],ma_type=ma_type, column_name=column_name)
        cloud = pd.concat([fast['mean'], slow['mean']], axis=1,
                          keys=['fast', 'slow'])
        return cloud
    
    
    def get_statistics(self):
        # This method might also need column_name if it operates on a specific column
        # For now, assuming it works on the primary data column or all if appropriate
        spread = self.spread_df.sort_index().copy()
        returns = spread.diff().dropna()
        descriptive_stats = returns.describe()
        return returns, descriptive_stats

    def _get_exp_ma(self, df_column, window): # df_column is expected to be a DataFrame with one column
        """Calculate Exponential Moving Average (EMA)."""
        return df_column.ewm(span=window, adjust=False).mean()

    def _get_simple_ma(self, df_column, window): # df_column is expected to be a DataFrame with one column
        """Calculate Simple Moving Average (SMA)."""
        return df_column.rolling(window=window).mean()
    
    def _get_bollinger_bands(self, df, window, column_name, std_const = 2): # Added column_name
        """Calculate Bollinger Bands based on the specified data column."""
        if 'mean' not in df.columns:
            raise ValueError("'mean' column must be present in DataFrame to calculate Bollinger Bands.")
        if column_name not in df.columns:
            raise ValueError(f"Column '{column_name}' for Bollinger Bands base not found in DataFrame. Available: {df.columns.tolist()}")
            
        # Calculate difference from the mean of the *original specified data column*
        difference = pd.Series(df[column_name].values - df['mean'].values, index=df.index)
        diff_std = difference.rolling(window).std()
        df['upper_band'] = df['mean'] + std_const * diff_std
        df['lower_band'] = df['mean'] - std_const * diff_std
        return df
