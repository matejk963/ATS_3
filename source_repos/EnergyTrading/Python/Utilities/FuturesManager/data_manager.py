import pandas as pd

class DataManager:
    def __init__(self, data):
        self.data = data
        self.current_filtered_df = None
        self.comparison_filtered_df = None
        self.selected_keys = []
        self.selected_comparison_keys = []

    def update_selected_keys(self, level, key, comparison=False):
        """Update navigation keys."""
        if comparison:
            self.selected_comparison_keys = self.selected_comparison_keys[:level]
            self.selected_comparison_keys.append(key)
        else:
            self.selected_keys = self.selected_keys[:level]
            self.selected_keys.append(key)

    def filter_dataframe(self, df, level_0_value):
        """Filter DataFrame by level-0 column."""
        if isinstance(df.columns, pd.MultiIndex):
            filtered_df = df.loc[:, df.columns.get_level_values(0) == level_0_value]
            return filtered_df
        return df
