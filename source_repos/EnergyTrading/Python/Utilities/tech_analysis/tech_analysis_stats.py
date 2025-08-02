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

    def get_moving_average(self, window=20, ma_type='exp'):
        """
        Calculate the moving average for the spread dataframe.
        """
        type_dict = {
            'exp': self._get_exp_ma,
            'simple': self._get_simple_ma
        }

        if ma_type not in type_dict:
            raise ValueError(f"Invalid moving average type: {ma_type}. Choose 'exp' or 'simple'.")

        spread_df = self.spread_df.copy()
        spread_df['mean'] = type_dict[ma_type](spread_df, window)  # Call function with window parameter
        spread_df = self._get_bollinger_bands(spread_df,window)

        return spread_df
    
    def get_ma_cloud(self, windows=[20, 50], ma_type='exp'):
        fast = self.get_moving_average(window=windows[0],ma_type=ma_type)
        slow = self.get_moving_average(window=windows[1],ma_type=ma_type)
        cloud = pd.concat([fast['mean'], slow['mean']], axis=1,
                          keys=['fast', 'slow'])
        return cloud
    
    
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
    
    def _get_bollinger_bands(self, df, window, std_const = 2):
        non_mean_col = [a for a in df.columns if a not in ['mean', 'lower_band', 'upper_band']][0]
        difference = pd.Series(df[non_mean_col].values - df['mean'].values, index=df.index)
        diff_std = difference.rolling(window).std()
        df['upper_band'] = df['mean'] + std_const * diff_std
        df['lower_band'] = df['mean'] - std_const * diff_std
        return df
