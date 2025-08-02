import numpy as np
import pandas as pd
import itertools
import abc
from tqdm import tqdm
import time
import math
import sys
import pickle
# Async definition
from multiprocessing import Pool, cpu_count

class ModularStrategyCalibration():
    def __init__(self, method):
        self.method = method

    def change_strategy(self, strategy_class, features_pool, strategy_data_columns):
        self.strategy_cls = strategy_class
        self.strategy_data = {'features_pool': features_pool, 'columns': strategy_data_columns}

    def cost_function(self, value_list, method, diff_bool=False):
        if diff_bool:
            ret = np.diff(value_list, n=1)
            # ret = ret[abs(ret) > 0]
            if len(ret[abs(ret) > 0]) == 0:
                return 0
        else:
            ret = np.asarray(value_list)
        if method == 'sharp':
            return np.mean(ret) / np.std(ret)
        elif method == 'mean':
            return np.mean(ret)
        elif method == 'cumpnl':
            return value_list[-1]
        else:
            raise ValueError('Unknown method of optimisation %s' % self.method)

    def set_params(self, params):
        # new_param_dict = {k: v for k, v in params.items()
        #                   if k in self.strategy.param_list}
        new_param_dict = {k: v if k not in params.keys() else params[k]
                          for k, v in self.strategy.param_dict.items()}
        self.strategy.update_params(new_param_dict)
        return self.strategy

    @staticmethod
    def set_model_params(model_class, params):
        new_param_dict = {k: v for k, v in params.items()
                        if k in model_class.param_keys}
        model_class.update_params(new_param_dict)
        return model_class
    
    @staticmethod
    def prepare_data(instr, b_class, df_ba, df_tr):
        data_dict = {}
        data_dict[instr] = b_class.merge_data(df_ba, df_tr, False)
        return data_dict
    
    @staticmethod
    def combination_id(result):
        features = [[*result[feature]['params'].values()] for feature in result.keys() if 'feature' in feature and result[feature].get('params', None)]
        profit = [[result[feature]] for feature in result.keys() if feature in ['make_profit_margin', 'stop_loss', 'stop_profit',
                                                                                'burnout_period', 'makeagg_ratio']]
        features += profit
        return '_'.join(map(str,sum([*features], [])))
    
    def calibrate_single_multip(self, data_tests, backtest_class, combinations, cached_r, fix_params, idxs, cpu_percent):

        score_dict = {self.combination_id(k): 0 for k in combinations}

        pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")

        static_data = {
            'data_tests': data_tests,
            'backtest_class': backtest_class,
            'fix_params': fix_params,
            'idxs': idxs,
            'cached_r': cached_r
        }

        total_cores = cpu_count()
        # Ensure at least 2 cores are reserved for the system
        usable_cores = max(2, total_cores - 2) 
        # Calculate cores based on the specified percentage, rounding down but ensuring at least 1 core is used
        cores_to_use = max(1, min(math.floor(usable_cores * (cpu_percent / 100.0)), usable_cores))


        with Pool(processes=cores_to_use) as pool:
            async_results = [pool.apply_async(self.async_task, args=(self, static_data, params_dict, )) for params_dict in combinations]

            # Periodically check progress and update the progress counter
            last_c = 0
            while True:
                completed = sum(1 for res in async_results if res.ready())
                diff_c = completed - last_c
                last_c = completed
                if diff_c > 0:
                    pbar.update(diff_c)

                if completed == len(async_results):
                    break
                time.sleep(.1)
            # Close the pool and wait for the tasks to complete
            pool.close()
            pool.join()

            # Collect results from the AsyncResult objects
            for async_result in async_results:
                score_dict.update(async_result.get())
        # COUNTER_ += len(params_dict_list['strt'])
        pbar.close()
        return score_dict

    @staticmethod
    def async_task(cls, static_data, params):
        strategy = cls.strategy_cls(cls.strategy_data['features_pool'],
                                cls.strategy_data['columns'],
                                {**params, **static_data['fix_params']}) # join fixed and dynamic param dict

        data_tests = static_data['data_tests']
        backtest_class = static_data['backtest_class']
        idxs = static_data['idxs']
        fees = static_data['fix_params']['br_fee']
        cached_r = static_data['cached_r']

        key = cls.combination_id(params)

        out_ser = cls.simulate_single(strategy, data_tests, cached_r,
                                        backtest_class, idxs, fees)
        return {key: out_ser}

    def simulate_single(self, strategy, data_tests, cached_r,
                        backtest_class, idxs, fees):
        backtest_class.simulate_strategy(strategy, data_tests, idxs, cached_returns=cached_r)
        try:
            xx =  backtest_class.calc_returns_new(strategy)
            if len(xx) < 1:
                return -6.9

            fees = abs(xx['action']).sum()*fees
            # pd.DataFrame({k: strategy.stats_dict[k] for k in strategy.stats_dict.keys() if k in [
            # 'timestamp', 'position', 'action', 'price_level', 'open_price']}).to_csv('xx.csv')
            # pickle.dump(backtest_class.processed_idxs, open('debug.pkl', 'wb'))
            return xx['returns'].sum()-fees

        except Exception as e:
            return str(e)
    
    def simulate_strategy_params(self, data_tests, params_dict,
                                backtest_class):
        backtest_class.reset_time()
        # Simulate strategy
        return backtest_class.simulate_strategy(self.strategy, data_tests)
