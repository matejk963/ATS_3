from Strategies.Base.feature_interface import FeatureInterface
import numpy as np
import torch
from datetime import time

class FeatureBAVolrat(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['ba_volrat_' + suffix]
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)
        
    def condition_long(self, data):
        return data[self.data_columns[0]] < -self.thold
    
    def condition_short(self, data):
        return data[self.data_columns[0]] > self.thold

    @classmethod
    def get_t(self):
        return ['thold']

class FeatureBASpread(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['ba_spread']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)
    
    def condition_long(self, data):
        return data['ba_spread'] < self.thold
    
    def condition_short(self, data):
        return data['ba_spread'] < self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureSBMargin(FeatureInterface):
    def __init__(self, strategy_data_columns, thold_sb_margin, thold_bo_volume=1, suffix=""):
        self.thold_sb_margin = thold_sb_margin
        self.thold_bo_volume = thold_bo_volume
        self.data_columns = ['bid_price', 'ask_price', 'sb_bid_price', 'sb_ask_price']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['sb_ask_price'] - data['ask_price'] > self.thold_sb_margin and data['b_ask_volume'] <= self.thold_bo_volume
    
    def condition_short(self, data):
        return data['bid_price'] - data['sb_bid_price'] > self.thold_sb_margin and data['b_bid_volume'] <= self.thold_bo_volume
    
class FeatureBestOrderOne(FeatureInterface):
    def __init__(self, strategy_data_columns, suffix=""):
        self.data_columns = ['b_vol', 'a_vol']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['a_vol'] < 1.5
    
    
    def condition_short(self, data):
        return data['b_vol'] < 1.5
    
class FeatureSparsity(FeatureInterface):
    def __init__(self, strategy_data_columns, thold_dense, thold_sparse, suffix=""):
        self.thold_dense = thold_dense
        self.thold_sparse = thold_sparse
        self.data_columns = ['a_price_sparsity', 'b_price_sparsity']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['a_price_sparsity'] > self.thold_sparse and data['b_price_sparsity'] < self.thold_dense
    
    def condition_short(self, data):
        return data['b_price_sparsity'] > self.thold_sparse and data['a_price_sparsity'] < self.thold_dense
    
    @classmethod
    def get_t(self):
        return ['thold_dense', 'thold_sparse']

class FeatureTimeIntervalLong(FeatureInterface):
    def __init__(self, strategy_data_columns, thold_from, thold_to, suffix=""):
        hours, minutes = thold_from.split('_')
        self.thold_from = time(int(hours), int(minutes))
        hours, minutes = thold_to.split('_')
        self.thold_to = time(int(hours), int(minutes))
        self.data_columns = ['timestamp']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return (data['timestamp'].time() > self.thold_from) and (data['timestamp'].time() < self.thold_to)
    
    def condition_short(self, data):
        return False
    
    @classmethod
    def get_t(self):
        return ['thold_from', 'thold_to']
    
class FeatureScaledSparsity(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['scaled_sparsity']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['scaled_sparsity'] > self.thold
    
    def condition_short(self, data):
        return data['scaled_sparsity'] < -self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']

class FeatureTradedAboveBO(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['trd_price', 'b_price', 'a_price']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['trd_price'] > data['a_price'] + self.thold
    
    def condition_short(self, data):
        return data['trd_price'] < data['b_price'] - self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureOrderT1(FeatureInterface):
    def __init__(self, strategy_data_columns, suffix=""):
        self.data_columns = ['bid_t1', 'ask_t1']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['ask_t1']
    
    def condition_short(self, data):
        return data['bid_t1']
    
    @classmethod
    def get_t(self):
        return []
    
class FeatureIntensity(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['int']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['int'] > self.thold
    
    def condition_short(self, data):
        return data['int'] > self.thold

    @classmethod
    def get_t(self):
        return ['thold']

class FeatureTrdGapCounter(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['trd_gap_counter']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['trd_gap_counter'] > self.thold
    
    def condition_short(self, data):
        return data['trd_gap_counter'] > self.thold

    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureOutputModel(FeatureInterface):
    def __init__(self, strategy_data_columns, suffix=""):
        self.data_columns = ['output_y_hat']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        if np.isnan(data['output_y_hat']):
            return False
        return round(data['output_y_hat']) == 2
    
    def condition_short(self, data):
        if np.isnan(data['output_y_hat']):
            return False
        return round(data['output_y_hat']) == 0
    
class FeatureXGBModel(FeatureInterface):
    def __init__(self, strategy_data_columns, thold_for, thold_against, suffix=""):
        self.data_columns = ['xgb_short', 'xgb_neu', 'xgb_long']
        self.thold_for = thold_for
        self.thold_against = thold_against
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    @staticmethod
    def thold_function(array, thold_for, thold_against, suffix=""):
        new_array = np.array(array)/sum(array)
        best, sbest = sorted([(v, i) for i, v in enumerate(new_array)], reverse=True)[:2]
        b_sb_diff = best[0] - sbest[0]
        return best[1] if (array[best[1]] > thold_for) and (b_sb_diff > thold_against) else 1
    
    def condition_long(self, data):
        arr = [x for x in self.data_columns]
        return self.thold_function()
    
    def condition_short(self, data):
        if np.isnan(data['output_y_hat']):
            return False
        return round(data['output_y_hat']) == 0

class FeatureIntervalPriceDiff(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['interval_pdiff']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        if np.isnan(data['interval_pdiff']):
            return False
        return data['interval_pdiff'] > self.thold
    
    def condition_short(self, data):
        if np.isnan(data['interval_pdiff']):
            return False
        return data['interval_pdiff'] < -self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureIntervalIntensity(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['interval_int']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        if np.isnan(data['interval_int']):
            return False
        return data['interval_int'] > self.thold
    
    def condition_short(self, data):
        if np.isnan(data['interval_int']):
            return False
        return data['interval_int'] > self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    


class FeatureActionSum(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['action_sum_' + suffix]
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data[self.data_columns[0]] > self.thold
    
    def condition_short(self, data):
        return data[self.data_columns[0]] < -self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureActionAbsSum(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['action_abs_sum_' + suffix]
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data[self.data_columns[0]] > self.thold
    
    def condition_short(self, data):
        return data[self.data_columns[0]] > self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']


class FeatureCloseLevel(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['_close_level']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['_close_level'] > self.thold
    
    def condition_short(self, data):
        return data['_close_level'] < (1-self.thold)
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureBODiff(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['diff_b_price', 'diff_a_price']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['diff_b_price'] > self.thold
    
    def condition_short(self, data):
        return data['diff_a_price'] < -self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureSPDiff(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['diff_b_price_sparsity', 'diff_a_price_sparsity']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['diff_a_price_sparsity'] > self.thold
    
    def condition_short(self, data):
        return data['diff_b_price_sparsity'] > self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureFarLevel(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['_far_level']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['_far_level'] < self.thold
    
    def condition_short(self, data):
        return data['_far_level'] > (1-self.thold)
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeaturePMovement(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['p_movement_0.3']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['p_movement_0.3'] > self.thold
    
    def condition_short(self, data):
        return data['p_movement_0.3'] < -self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureRandom(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['random']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['random'] > self.thold
    
    def condition_short(self, data):
        return data['random'] <= self.thold
    


class FeatureDailyChangeDirection(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['daily_change_direction']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['daily_change_direction'] < self.thold
    
    def condition_short(self, data):
        return data['daily_change_direction'] > -self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureSeqDay(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['sequence_day_number']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['sequence_day_number'] == self.thold
    
    def condition_short(self, data):
        return data['sequence_day_number'] == self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    

class FeatureDayWeek(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['dayweek']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['dayweek'] >= self.thold
    
    def condition_short(self, data):
        return data['dayweek'] >= self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    
class FeatureDayHour(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['hour']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['hour'] >= self.thold
    
    def condition_short(self, data):
        return data['hour'] >= self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']
    

class FeatureDirection(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['trd_price']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return self.thold == 1
    
    def condition_short(self, data):
        return self.thold == 0
    
    @classmethod
    def get_t(self):
        return ['thold']
    

class FeatureSeqInDirection(FeatureInterface):
    def __init__(self, strategy_data_columns, thold, suffix=""):
        self.thold = thold
        self.data_columns = ['seq_inc', 'seq_dec']
        # Mandatory check
        self.check_data(strategy_data_columns, self.data_columns)

    def condition_long(self, data):
        return data['seq_inc'] > self.thold
    
    def condition_short(self, data):
        return data['seq_dec'] > self.thold
    
    @classmethod
    def get_t(self):
        return ['thold']