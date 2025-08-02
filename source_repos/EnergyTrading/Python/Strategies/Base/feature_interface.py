from abc import ABC, abstractmethod

class FeatureInterface(ABC):
    @abstractmethod
    def condition_short(data):
        # mandatory
        pass
    
    @abstractmethod
    def condition_long(data):
        # mandatory
        pass
    def condition_close_short(data):
        # optional, define only when feature is designated to close short position
        return False
    def condition_close_long(data):
        # optional, define only when feature is designated to close long position
        return False
    
    def condition_close(data):
        # method that is called in strategy.check_state
        return False
    
    @staticmethod
    def check_data(strategy_data_columns, data_columns):
        missing_columns = [col for col in data_columns if col not in strategy_data_columns]
        if missing_columns:
            # Construct a user-friendly message listing the missing columns
            error_message = f"The following columns are missing from strategy_data_columns: {', '.join(missing_columns)}"
            raise AssertionError(error_message)
        # If all columns are present, the assertion implicitly passes, and no error is raised.
        # You could optionally add an 'else' block or a return statement if needed for further logic.
    


# ----------------- EXAMPLE ----------------------
# - - - - - implement from parent like this
class FeatureRatio(FeatureInterface):
    def __init__(self, strategy_data_columns, thold_ratio_long=.5, thold_ratio_short=-.5):
        self.t_long = thold_ratio_long
        self.t_short = thold_ratio_short
        self.data_columns = ['ratio']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)
        
    def condition_long(self, data):
        return data['ratio'] > self.t_long
    
    def condition_short(self, data):
        return data['ratio'] < self.t_short
