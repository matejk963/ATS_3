import abc
import logging
import time
import numpy as np

from .own_tools.math_features import EMA, DifferentialEMA, DerivativeEMA, FeatureTrdMomentum, calculate_dti_time, trd_gap_calc

log = logging.getLogger("observer_strategy.predictor_statistics")

tol = 1e-5

class PredictorsStats(object):
    strategy_id = None
    predictors_dict = {}
    models_dict = {}
    trd_price_stack = []
    last_value = None
    timestamp = None

    def __init__(self, strategy_id=''):
        self.strategy_id = strategy_id
        self.init_models()
        self.init_predictors()
    
    def init_predictors(self):
        # Delta predictors
        self.predictors_dict['delta_a_05'] = None
        self.predictors_dict['delta_a_10'] = None
        self.predictors_dict['delta_a_50'] = None
        self.predictors_dict['delta_a_75'] = None
        self.predictors_dict['delta_b_05'] = None
        self.predictors_dict['delta_b_10'] = None
        self.predictors_dict['delta_b_50'] = None
        self.predictors_dict['delta_b_75'] = None
        self.predictors_dict['delta_mid_05'] = None
        self.predictors_dict['delta_mid_10'] = None
        self.predictors_dict['delta_mid_50'] = None
        self.predictors_dict['delta_mid_75'] = None
        self.predictors_dict['delta_ba_05'] = None
        self.predictors_dict['delta_ba_10'] = None
        self.predictors_dict['delta_ba_50'] = None
        self.predictors_dict['delta_ba_75'] = None
        
        # Volume ratio predictors
        self.predictors_dict['ba_volrat_00'] = None
        self.predictors_dict['ba_volrat_05'] = None
        self.predictors_dict['ba_volrat_08'] = None
        self.predictors_dict['ba_volrat_10'] = None
        self.predictors_dict['ba_volrat_15'] = None
        self.predictors_dict['ba_volrat_20'] = None
        self.predictors_dict['ba_volrat_25'] = None
        
        # Diff AM WM predictors
        self.predictors_dict['diff_am_wm_00'] = None
        self.predictors_dict['diff_am_wm_05'] = None
        self.predictors_dict['diff_am_wm_08'] = None
        self.predictors_dict['diff_am_wm_10'] = None
        self.predictors_dict['diff_am_wm_15'] = None
        self.predictors_dict['diff_am_wm_20'] = None
        self.predictors_dict['diff_am_wm_25'] = None
        
        # Delta MW predictors
        self.predictors_dict['delta_mw_00_05'] = None
        self.predictors_dict['delta_mw_05_05'] = None
        self.predictors_dict['delta_mw_08_05'] = None
        self.predictors_dict['delta_mw_10_05'] = None
        self.predictors_dict['delta_mw_15_05'] = None
        self.predictors_dict['delta_mw_20_05'] = None
        self.predictors_dict['delta_mw_25_05'] = None
        self.predictors_dict['delta_mw_00_10'] = None
        self.predictors_dict['delta_mw_05_10'] = None
        self.predictors_dict['delta_mw_08_10'] = None
        self.predictors_dict['delta_mw_10_10'] = None
        self.predictors_dict['delta_mw_15_10'] = None
        self.predictors_dict['delta_mw_20_10'] = None
        self.predictors_dict['delta_mw_25_10'] = None
        self.predictors_dict['delta_mw_00_50'] = None
        self.predictors_dict['delta_mw_05_50'] = None
        self.predictors_dict['delta_mw_08_50'] = None
        self.predictors_dict['delta_mw_10_50'] = None
        self.predictors_dict['delta_mw_15_50'] = None
        self.predictors_dict['delta_mw_20_50'] = None
        self.predictors_dict['delta_mw_25_50'] = None
        self.predictors_dict['delta_mw_00_75'] = None
        self.predictors_dict['delta_mw_05_75'] = None
        self.predictors_dict['delta_mw_08_75'] = None
        self.predictors_dict['delta_mw_10_75'] = None
        self.predictors_dict['delta_mw_15_75'] = None
        self.predictors_dict['delta_mw_20_75'] = None
        self.predictors_dict['delta_mw_25_75'] = None
        
        # Price and spread predictors
        self.predictors_dict['b_price_sparsity'] = None
        self.predictors_dict['a_price_sparsity'] = None
        self.predictors_dict['b_price'] = None
        self.predictors_dict['a_price'] = None
        self.predictors_dict['ba_spread'] = None
        
        # Diff EMA predictors
        self.predictors_dict['diff_ema_am_wm_00'] = None
        self.predictors_dict['diff_ema_am_wm_05'] = None
        self.predictors_dict['diff_ema_am_wm_08'] = None
        self.predictors_dict['diff_ema_am_wm_10'] = None
        self.predictors_dict['diff_ema_am_wm_15'] = None
        self.predictors_dict['diff_ema_am_wm_20'] = None
        self.predictors_dict['diff_ema_am_wm_25'] = None
        self.predictors_dict['diff_ema_ba_mba'] = None
        
        # Lambda trade predictors
        self.predictors_dict['lamb_tr_b_05'] = None
        self.predictors_dict['lamb_tr_a_05'] = None
        self.predictors_dict['lamb_tr_b_10'] = None
        self.predictors_dict['lamb_tr_a_10'] = None
        self.predictors_dict['lamb_tr_b_50'] = None
        self.predictors_dict['lamb_tr_a_50'] = None
        self.predictors_dict['lamb_tr_b_75'] = None
        self.predictors_dict['lamb_tr_a_75'] = None
        
        # ILambda predictors
        self.predictors_dict['ilamb_b_10'] = None
        self.predictors_dict['ilamb_a_10'] = None
        self.predictors_dict['ilamb_b_50'] = None
        self.predictors_dict['ilamb_a_50'] = None
        self.predictors_dict['ilamb_b_75'] = None
        self.predictors_dict['ilamb_a_75'] = None
        
        # DLambda predictors
        self.predictors_dict['dlamb_b_75'] = None
        self.predictors_dict['dlamb_a_75'] = None
        
        # Trade momentum predictors
        self.predictors_dict['trd_momentum_10'] = None
        self.predictors_dict['trd_momentum_acc_10'] = None
        self.predictors_dict['trd_momentum_50'] = None
        self.predictors_dict['trd_momentum_acc_50'] = None
        self.predictors_dict['trd_momentum_100'] = None
        self.predictors_dict['trd_momentum_acc_100'] = None
        
        # Other predictors
        self.predictors_dict['ret'] = None
        self.predictors_dict['vpin_10'] = None
        self.predictors_dict['vpin_20'] = None
        self.predictors_dict['vpin_50'] = None
        self.predictors_dict['vpin_100'] = None
        self.predictors_dict['dti_300s'] = None
        self.predictors_dict['trd_gap'] = None


    def init_models(self):
        self.models_dict['delta_a_05'] = DifferentialEMA(5)
        self.models_dict['delta_a_10'] = DifferentialEMA(10)
        self.models_dict['delta_a_50'] = DifferentialEMA(50)
        self.models_dict['delta_a_75'] = DifferentialEMA(75)
        self.models_dict['delta_b_05'] = DifferentialEMA(5)
        self.models_dict['delta_b_10'] = DifferentialEMA(10)
        self.models_dict['delta_b_50'] = DifferentialEMA(50)
        self.models_dict['delta_b_75'] = DifferentialEMA(75)
        self.models_dict['delta_mid_05'] = DifferentialEMA(5)
        self.models_dict['delta_mid_10'] = DifferentialEMA(10)
        self.models_dict['delta_mid_50'] = DifferentialEMA(50)
        self.models_dict['delta_mid_75'] = DifferentialEMA(75)
        self.models_dict['delta_ba_05'] = DifferentialEMA(5)
        self.models_dict['delta_ba_10'] = DifferentialEMA(10)
        self.models_dict['delta_ba_50'] = DifferentialEMA(50)
        self.models_dict['delta_ba_75'] = DifferentialEMA(75)
        
        # Delta MW models
        self.models_dict['delta_mw_00_05'] = DifferentialEMA(5)
        self.models_dict['delta_mw_05_05'] = DifferentialEMA(5)
        self.models_dict['delta_mw_08_05'] = DifferentialEMA(5)
        self.models_dict['delta_mw_10_05'] = DifferentialEMA(5)
        self.models_dict['delta_mw_15_05'] = DifferentialEMA(5)
        self.models_dict['delta_mw_20_05'] = DifferentialEMA(5)
        self.models_dict['delta_mw_25_05'] = DifferentialEMA(5)
        self.models_dict['delta_mw_00_10'] = DifferentialEMA(10)
        self.models_dict['delta_mw_05_10'] = DifferentialEMA(10)
        self.models_dict['delta_mw_08_10'] = DifferentialEMA(10)
        self.models_dict['delta_mw_10_10'] = DifferentialEMA(10)
        self.models_dict['delta_mw_15_10'] = DifferentialEMA(10)
        self.models_dict['delta_mw_20_10'] = DifferentialEMA(10)
        self.models_dict['delta_mw_25_10'] = DifferentialEMA(10)
        self.models_dict['delta_mw_00_50'] = DifferentialEMA(50)
        self.models_dict['delta_mw_05_50'] = DifferentialEMA(50)
        self.models_dict['delta_mw_08_50'] = DifferentialEMA(50)
        self.models_dict['delta_mw_10_50'] = DifferentialEMA(50)
        self.models_dict['delta_mw_15_50'] = DifferentialEMA(50)
        self.models_dict['delta_mw_20_50'] = DifferentialEMA(50)
        self.models_dict['delta_mw_25_50'] = DifferentialEMA(50)
        self.models_dict['delta_mw_00_75'] = DifferentialEMA(75)
        self.models_dict['delta_mw_05_75'] = DifferentialEMA(75)
        self.models_dict['delta_mw_08_75'] = DifferentialEMA(75)
        self.models_dict['delta_mw_10_75'] = DifferentialEMA(75)
        self.models_dict['delta_mw_15_75'] = DifferentialEMA(75)
        self.models_dict['delta_mw_20_75'] = DifferentialEMA(75)
        self.models_dict['delta_mw_25_75'] = DifferentialEMA(75)

        #ema's
        self.models_dict['mid_priceS'] = EMA(75)
        self.models_dict['ba_spreadS'] = EMA(75)
        self.models_dict['mid_priceSW_00'] = EMA(75)
        self.models_dict['mid_priceSW_05'] = EMA(75)
        self.models_dict['mid_priceSW_08'] = EMA(75)
        self.models_dict['mid_priceSW_10'] = EMA(75)
        self.models_dict['mid_priceSW_15'] = EMA(75)
        self.models_dict['mid_priceSW_20'] = EMA(75)
        self.models_dict['mid_priceSW_25'] = EMA(75)

        #dlamb
        self.models_dict['dlamb_b_75'] = DifferentialEMA(75)
        self.models_dict['dlamb_a_75'] = DifferentialEMA(75)

        # trd momentum
        self.models_dict['trd_momentum_10'] = FeatureTrdMomentum(10)
        self.models_dict['trd_momentum_50'] = FeatureTrdMomentum(50)
        self.models_dict['trd_momentum_100'] = FeatureTrdMomentum(100)

        self.models_dict['trd_side_list'] = []*75
        self.models_dict['trd_list'] = []
        
        self.timestamp = time.time()

    def reset(self):
        pass
        # if self.model_type is None:
        #     pass
        # elif self.model_type == 'EMA':
        #     tau = self.model_params[0]
        #     tol = self.model_params[1]
        #     self.model_dict['spread'] = EmaModel(tau, 0, tol, False)
        # elif self.model_type == 'MSTD_x':
        #     tau = self.model_params[0]
        #     tol = self.model_params[1]
        #     std0 = self.model_params[2]
        #     burn = self.model_dict['spread'].burn
        #     self.model_dict['spread'] = MstdModel(tau, 30, 2., 0, std0, tol, burn, False, False)
        # elif self.model_type == 'MSTD_t':
        #     tau = self.model_params[0]
        #     tol = self.model_params[1]
        #     std0 = self.model_params[2]
        #     burn = self.model_dict['spread'].burn
        #     self.model_dict['spread'] = MstdModel(tau, 30, 2., 0, std0, tol, burn, True, False)
        # elif self.model_type == 'MID':
        #     tol = self.model_params[1]
        #     self.model_dict['spread'] = MidModel(0, tol)
        # else:
        #     raise ValueError("Unknown model type in ModelStats: %s." % self.model_type)
        self.timestamp = time.time()

    def _safe_get(self, data_dict, key):
        if key not in data_dict:
            log.error(f"Missing column '{key}' in data_dict for strategy {self.strategy_id}")
            return None
        return data_dict[key]

    def update_arrays(self, trade_object, mid_price):
        self.models_dict['trd_list'].append(trade_object)
        self.models_dict['trd_side_list'].append(1 if trade_object.price >= mid_price else -1)

    def update_values(self, data_dict):
        # Check for required columns at the beginning
        required_columns = ['trd_object', 'a_price', 'b_price', 'mid_price', 'ba_spread', 
                          'ba_volrat_00', 'ba_volrat_05', 'ba_volrat_08', 'ba_volrat_10', 'ba_volrat_15', 'ba_volrat_20', 'ba_volrat_25',
                          'mid_priceW_00', 'mid_priceW_05', 'mid_priceW_08', 'mid_priceW_10', 'mid_priceW_15', 'mid_priceW_20', 'mid_priceW_25',
                          'b_price_sparsity', 'a_price_sparsity', 'trd_price']
        
        for column in required_columns:
            if column not in data_dict:
                log.error(f"Missing column '{column}' in data_dict for strategy {self.strategy_id}")
                return None

        self.update_arrays(data_dict['trd_object'], data_dict['mid_price'])

        self.predictors_dict['delta_a_05'] = self.models_dict['delta_a_05'].push(data_dict['a_price'])
        self.predictors_dict['delta_a_10'] = self.models_dict['delta_a_10'].push(data_dict['a_price'])
        self.predictors_dict['delta_a_50'] = self.models_dict['delta_a_50'].push(data_dict['a_price'])
        self.predictors_dict['delta_a_75'] = self.models_dict['delta_a_75'].push(data_dict['a_price'])
        self.predictors_dict['delta_b_05'] = self.models_dict['delta_b_05'].push(data_dict['b_price'])
        self.predictors_dict['delta_b_10'] = self.models_dict['delta_b_10'].push(data_dict['b_price'])
        self.predictors_dict['delta_b_50'] = self.models_dict['delta_b_50'].push(data_dict['b_price'])
        self.predictors_dict['delta_b_75'] = self.models_dict['delta_b_75'].push(data_dict['b_price'])
        self.predictors_dict['delta_mid_05'] = self.models_dict['delta_mid_05'].push(data_dict['mid_price'])
        self.predictors_dict['delta_mid_10'] = self.models_dict['delta_mid_10'].push(data_dict['mid_price'])
        self.predictors_dict['delta_mid_50'] = self.models_dict['delta_mid_50'].push(data_dict['mid_price'])
        self.predictors_dict['delta_mid_75'] = self.models_dict['delta_mid_75'].push(data_dict['mid_price'])
        self.predictors_dict['delta_ba_05'] = self.models_dict['delta_ba_05'].push(data_dict['ba_spread'])
        self.predictors_dict['delta_ba_10'] = self.models_dict['delta_ba_10'].push(data_dict['ba_spread'])
        self.predictors_dict['delta_ba_50'] = self.models_dict['delta_ba_50'].push(data_dict['ba_spread'])
        self.predictors_dict['delta_ba_75'] = self.models_dict['delta_ba_75'].push(data_dict['ba_spread'])
        
        # Volume ratio predictors
        self.predictors_dict['ba_volrat_00'] = data_dict['ba_volrat_00']
        self.predictors_dict['ba_volrat_05'] = data_dict['ba_volrat_05']
        self.predictors_dict['ba_volrat_08'] = data_dict['ba_volrat_08']
        self.predictors_dict['ba_volrat_10'] = data_dict['ba_volrat_10']
        self.predictors_dict['ba_volrat_15'] = data_dict['ba_volrat_15']
        self.predictors_dict['ba_volrat_20'] = data_dict['ba_volrat_20']
        self.predictors_dict['ba_volrat_25'] = data_dict['ba_volrat_25']
        
        # Diff AM WM predictors
        self.predictors_dict['diff_am_wm_00'] = np.log(data_dict['mid_price']/data_dict['mid_priceW_00'])
        self.predictors_dict['diff_am_wm_05'] = np.log(data_dict['mid_price']/data_dict['mid_priceW_05'])
        self.predictors_dict['diff_am_wm_08'] = np.log(data_dict['mid_price']/data_dict['mid_priceW_08'])
        self.predictors_dict['diff_am_wm_10'] = np.log(data_dict['mid_price']/data_dict['mid_priceW_10'])
        self.predictors_dict['diff_am_wm_15'] = np.log(data_dict['mid_price']/data_dict['mid_priceW_15'])
        self.predictors_dict['diff_am_wm_20'] = np.log(data_dict['mid_price']/data_dict['mid_priceW_20'])
        self.predictors_dict['diff_am_wm_25'] = np.log(data_dict['mid_price']/data_dict['mid_priceW_25'])
        
        # Delta MW predictors
        self.predictors_dict['delta_mw_00_05'] = self.models_dict['delta_mw_00_05'].push(data_dict['mid_priceW_00'])
        self.predictors_dict['delta_mw_05_05'] = self.models_dict['delta_mw_05_05'].push(data_dict['mid_priceW_05'])
        self.predictors_dict['delta_mw_08_05'] = self.models_dict['delta_mw_08_05'].push(data_dict['mid_priceW_08'])
        self.predictors_dict['delta_mw_10_05'] = self.models_dict['delta_mw_10_05'].push(data_dict['mid_priceW_10'])
        self.predictors_dict['delta_mw_15_05'] = self.models_dict['delta_mw_15_05'].push(data_dict['mid_priceW_15'])
        self.predictors_dict['delta_mw_20_05'] = self.models_dict['delta_mw_20_05'].push(data_dict['mid_priceW_20'])
        self.predictors_dict['delta_mw_25_05'] = self.models_dict['delta_mw_25_05'].push(data_dict['mid_priceW_25'])
        self.predictors_dict['delta_mw_00_10'] = self.models_dict['delta_mw_00_10'].push(data_dict['mid_priceW_00'])
        self.predictors_dict['delta_mw_05_10'] = self.models_dict['delta_mw_05_10'].push(data_dict['mid_priceW_05'])
        self.predictors_dict['delta_mw_08_10'] = self.models_dict['delta_mw_08_10'].push(data_dict['mid_priceW_08'])
        self.predictors_dict['delta_mw_10_10'] = self.models_dict['delta_mw_10_10'].push(data_dict['mid_priceW_10'])
        self.predictors_dict['delta_mw_15_10'] = self.models_dict['delta_mw_15_10'].push(data_dict['mid_priceW_15'])
        self.predictors_dict['delta_mw_20_10'] = self.models_dict['delta_mw_20_10'].push(data_dict['mid_priceW_20'])
        self.predictors_dict['delta_mw_25_10'] = self.models_dict['delta_mw_25_10'].push(data_dict['mid_priceW_25'])
        self.predictors_dict['delta_mw_00_50'] = self.models_dict['delta_mw_00_50'].push(data_dict['mid_priceW_00'])
        self.predictors_dict['delta_mw_05_50'] = self.models_dict['delta_mw_05_50'].push(data_dict['mid_priceW_05'])
        self.predictors_dict['delta_mw_08_50'] = self.models_dict['delta_mw_08_50'].push(data_dict['mid_priceW_08'])
        self.predictors_dict['delta_mw_10_50'] = self.models_dict['delta_mw_10_50'].push(data_dict['mid_priceW_10'])
        self.predictors_dict['delta_mw_15_50'] = self.models_dict['delta_mw_15_50'].push(data_dict['mid_priceW_15'])
        self.predictors_dict['delta_mw_20_50'] = self.models_dict['delta_mw_20_50'].push(data_dict['mid_priceW_20'])
        self.predictors_dict['delta_mw_25_50'] = self.models_dict['delta_mw_25_50'].push(data_dict['mid_priceW_25'])
        self.predictors_dict['delta_mw_00_75'] = self.models_dict['delta_mw_00_75'].push(data_dict['mid_priceW_00'])
        self.predictors_dict['delta_mw_05_75'] = self.models_dict['delta_mw_05_75'].push(data_dict['mid_priceW_05'])
        self.predictors_dict['delta_mw_08_75'] = self.models_dict['delta_mw_08_75'].push(data_dict['mid_priceW_08'])
        self.predictors_dict['delta_mw_10_75'] = self.models_dict['delta_mw_10_75'].push(data_dict['mid_priceW_10'])
        self.predictors_dict['delta_mw_15_75'] = self.models_dict['delta_mw_15_75'].push(data_dict['mid_priceW_15'])
        self.predictors_dict['delta_mw_20_75'] = self.models_dict['delta_mw_20_75'].push(data_dict['mid_priceW_20'])
        self.predictors_dict['delta_mw_25_75'] = self.models_dict['delta_mw_25_75'].push(data_dict['mid_priceW_25'])
        
        # Price and spread predictors
        self.predictors_dict['b_price_sparsity'] = data_dict['b_price_sparsity']
        self.predictors_dict['a_price_sparsity'] = data_dict['a_price_sparsity']
        self.predictors_dict['b_price'] = data_dict['b_price']
        self.predictors_dict['a_price'] = data_dict['a_price']
        self.predictors_dict['ba_spread'] = data_dict['ba_spread']


        # EMA mid price update just single time
        self.predictors_dict['mid_priceS'] = self.models_dict['mid_priceS'].push(data_dict['mid_price'])
        self.predictors_dict['ba_spreadS'] = self.models_dict['ba_spreadS'].push(data_dict['ba_spread'])
        # Diff EMA predictors
        self.predictors_dict['diff_ema_am_wm_00'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_00'].push(data_dict['mid_priceW_00']))
        self.predictors_dict['diff_ema_am_wm_05'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_05'].push(data_dict['mid_priceW_05']))
        self.predictors_dict['diff_ema_am_wm_08'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_08'].push(data_dict['mid_priceW_08']))
        self.predictors_dict['diff_ema_am_wm_10'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_10'].push(data_dict['mid_priceW_10']))
        self.predictors_dict['diff_ema_am_wm_15'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_15'].push(data_dict['mid_priceW_15']))
        self.predictors_dict['diff_ema_am_wm_20'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_20'].push(data_dict['mid_priceW_20']))
        self.predictors_dict['diff_ema_am_wm_25'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_25'].push(data_dict['mid_priceW_25']))
        self.predictors_dict['diff_ema_ba_mba'] = round(data_dict['ba_spread'] - self.predictors_dict['ba_spreadS'], 2)
        
        # Lambda trade predictors
        self.predictors_dict['lamb_tr_b_05'] = sum([1 for x in self.models_dict['trd_side_list'][-5:] if ((x - -1) < tol)])/5
        self.predictors_dict['lamb_tr_a_05'] = sum([1 for x in self.models_dict['trd_side_list'][-5:] if ((x - 1) < tol)])/5
        self.predictors_dict['lamb_tr_b_10'] = sum([1 for x in self.models_dict['trd_side_list'][-10:] if ((x - -1) < tol)])/10
        self.predictors_dict['lamb_tr_a_10'] = sum([1 for x in self.models_dict['trd_side_list'][-10:] if ((x - 1) < tol)])/10
        self.predictors_dict['lamb_tr_b_50'] = sum([1 for x in self.models_dict['trd_side_list'][-50:] if ((x - -1) < tol)])/50
        self.predictors_dict['lamb_tr_a_50'] = sum([1 for x in self.models_dict['trd_side_list'][-50:] if ((x - 1) < tol)])/50
        self.predictors_dict['lamb_tr_b_75'] = sum([1 for x in self.models_dict['trd_side_list'][-75:] if ((x - -1) < tol)])/75
        self.predictors_dict['lamb_tr_a_75'] = sum([1 for x in self.models_dict['trd_side_list'][-75:] if ((x - 1) < tol)])/75
        
        # ILambda predictors
        self.predictors_dict['ilamb_b_10'] = self.predictors_dict['lamb_tr_b_05'] >= self.predictors_dict['lamb_tr_b_10']
        self.predictors_dict['ilamb_a_10'] = self.predictors_dict['lamb_tr_a_05'] >= self.predictors_dict['lamb_tr_a_10']
        self.predictors_dict['ilamb_b_50'] = self.predictors_dict['lamb_tr_b_05'] >= self.predictors_dict['lamb_tr_b_50']
        self.predictors_dict['ilamb_a_50'] = self.predictors_dict['lamb_tr_a_05'] >= self.predictors_dict['lamb_tr_a_50']
        self.predictors_dict['ilamb_b_75'] = self.predictors_dict['lamb_tr_b_05'] >= self.predictors_dict['lamb_tr_b_75']
        self.predictors_dict['ilamb_a_75'] = self.predictors_dict['lamb_tr_a_05'] >= self.predictors_dict['lamb_tr_a_75']
        
        # DLambda predictors
        self.predictors_dict['dlamb_b_75'] = self.models_dict['dlamb_b_75'].push(self.predictors_dict['lamb_tr_b_05'])
        self.predictors_dict['dlamb_a_75'] = self.models_dict['dlamb_a_75'].push(self.predictors_dict['lamb_tr_a_05'])
        
        # Trade momentum predictors
        self.predictors_dict['trd_momentum_10'], self.predictors_dict['trd_momentum_acc_10'] = self.models_dict['trd_momentum_10'].push(data_dict['trd_price'])
        self.predictors_dict['trd_momentum_50'], self.predictors_dict['trd_momentum_acc_50'] = self.models_dict['trd_momentum_50'].push(data_dict['trd_price'])
        self.predictors_dict['trd_momentum_100'], self.predictors_dict['trd_momentum_acc_100'] = self.models_dict['trd_momentum_100'].push(data_dict['trd_price'])
        
        # Other predictors
        self.predictors_dict['ret'] = None
        self.predictors_dict['vpin_10'] = None
        self.predictors_dict['vpin_20'] = None
        self.predictors_dict['vpin_50'] = None
        self.predictors_dict['vpin_100'] = None
        self.predictors_dict['dti_300s'] = calculate_dti_time(self.models_dict['trd_list'])
        self.predictors_dict['trd_gap'] = trd_gap_calc(data_dict)
        
        # Price and spread predictors
        self.predictors_dict['b_price_sparsity'] = data_dict['b_price_sparsity']
        self.predictors_dict['a_price_sparsity'] = data_dict['a_price_sparsity']
        self.predictors_dict['b_price'] = data_dict['b_price']
        self.predictors_dict['a_price'] = data_dict['a_price']
        self.predictors_dict['ba_spread'] = data_dict['ba_spread']
        

        # EMA mid price update just single time
        self.predictors_dict['mid_priceS'] = self.models_dict['mid_priceS'].push(data_dict['mid_price'])
        self.predictors_dict['ba_spreadS'] = self.models_dict['ba_spreadS'].push(data_dict['ba_spread'])
        # Diff EMA predictors
        self.predictors_dict['diff_ema_am_wm_00'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_00'].push(data_dict['mid_priceW_00']))
        self.predictors_dict['diff_ema_am_wm_05'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_05'].push(data_dict['mid_priceW_05']))
        self.predictors_dict['diff_ema_am_wm_08'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_08'].push(data_dict['mid_priceW_08']))
        self.predictors_dict['diff_ema_am_wm_10'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_10'].push(data_dict['mid_priceW_10']))
        self.predictors_dict['diff_ema_am_wm_15'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_15'].push(data_dict['mid_priceW_15']))
        self.predictors_dict['diff_ema_am_wm_20'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_20'].push(data_dict['mid_priceW_20']))
        self.predictors_dict['diff_ema_am_wm_25'] = np.log(
            self.predictors_dict['mid_priceS']/self.models_dict['mid_priceSW_25'].push(data_dict['mid_priceW_25']))
        self.predictors_dict['diff_ema_ba_mba'] = round(data_dict['ba_spread'] - self.predictors_dict['ba_spreadS'], 2)
        
        # Lambda trade predictors
        self.predictors_dict['lamb_tr_b_05'] = sum([1 for x in self.models_dict['trd_side_list'][-5:] if ((x - -1) < tol)])/5
        self.predictors_dict['lamb_tr_a_05'] = sum([1 for x in self.models_dict['trd_side_list'][-5:] if ((x - 1) < tol)])/5
        self.predictors_dict['lamb_tr_b_10'] = sum([1 for x in self.models_dict['trd_side_list'][-10:] if ((x - -1) < tol)])/10
        self.predictors_dict['lamb_tr_a_10'] = sum([1 for x in self.models_dict['trd_side_list'][-10:] if ((x - 1) < tol)])/10
        self.predictors_dict['lamb_tr_b_50'] = sum([1 for x in self.models_dict['trd_side_list'][-50:] if ((x - -1) < tol)])/50
        self.predictors_dict['lamb_tr_a_50'] = sum([1 for x in self.models_dict['trd_side_list'][-50:] if ((x - 1) < tol)])/50
        self.predictors_dict['lamb_tr_b_75'] = sum([1 for x in self.models_dict['trd_side_list'][-75:] if ((x - -1) < tol)])/75
        self.predictors_dict['lamb_tr_a_75'] = sum([1 for x in self.models_dict['trd_side_list'][-75:] if ((x - 1) < tol)])/75
        
        # ILambda predictors
        self.predictors_dict['ilamb_b_10'] = self.predictors_dict['lamb_tr_b_05'] >= self.predictors_dict['lamb_tr_b_10']
        self.predictors_dict['ilamb_a_10'] = self.predictors_dict['lamb_tr_a_05'] >= self.predictors_dict['lamb_tr_a_10']
        self.predictors_dict['ilamb_b_50'] = self.predictors_dict['lamb_tr_b_05'] >= self.predictors_dict['lamb_tr_b_50']
        self.predictors_dict['ilamb_a_50'] = self.predictors_dict['lamb_tr_a_05'] >= self.predictors_dict['lamb_tr_a_50']
        self.predictors_dict['ilamb_b_75'] = self.predictors_dict['lamb_tr_b_05'] >= self.predictors_dict['lamb_tr_b_75']
        self.predictors_dict['ilamb_a_75'] = self.predictors_dict['lamb_tr_a_05'] >= self.predictors_dict['lamb_tr_a_75']
        
        # DLambda predictors
        self.predictors_dict['dlamb_b_75'] = self.models_dict['dlamb_b_75'].push(self.predictors_dict['lamb_tr_b_05'])
        self.predictors_dict['dlamb_a_75'] = self.models_dict['dlamb_a_75'].push(self.predictors_dict['lamb_tr_a_05'])
        
        # Trade momentum predictors
        self.predictors_dict['trd_momentum_10'], self.predictors_dict['trd_momentum_acc_10'] = self.models_dict['trd_momentum_10'].push(data_dict['trd_price'])
        self.predictors_dict['trd_momentum_50'], self.predictors_dict['trd_momentum_acc_50'] = self.models_dict['trd_momentum_50'].push(data_dict['trd_price'])
        self.predictors_dict['trd_momentum_100'], self.predictors_dict['trd_momentum_acc_100'] = self.models_dict['trd_momentum_100'].push(data_dict['trd_price'])
        
        # Other predictors
        self.predictors_dict['ret'] = None
        self.predictors_dict['vpin_10'] = None
        self.predictors_dict['vpin_20'] = None
        self.predictors_dict['vpin_50'] = None
        self.predictors_dict['vpin_100'] = None
        self.predictors_dict['dti_300s'] = calculate_dti_time(self.models_dict['trd_list'])
        self.predictors_dict['trd_gap'] = None

        self.predictors_dict['trd_gap'] = trd_gap_calc(data_dict)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.attributes_list}


