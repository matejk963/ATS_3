import numpy as np
import itertools
import abc
from tqdm import tqdm
import time
import math
import sys
# Async definition
from multiprocessing import Pool, cpu_count
# Local packages
from Calibration.calibration_class import Calibration

class IBStrategyCalibration(Calibration):
    def __init__(self, strategy_class, method, opt_param, fix_param_dict):
        fix_params = fix_param_dict.keys()
        fix_value = fix_param_dict.values()
        super().__init__(method, opt_param, fix_params, fix_value)
        self.change_strategy(strategy_class)

    def change_strategy(self, strategy_class):
        self.strategy = strategy_class
        self.set_params(self.fix_param)

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
    
    def calibrate_p(self, data_dict, backtest_class, model_class,
                    opt_params, method='mean', multip=True, cpu_percent=90):
        n = len(data_dict.keys())
        if method is None:
            m = self.method
        else:
            m = method
        
        keys = opt_params.keys()
        # All combinations from param 
        lists = opt_params.values()
        combinations = list(itertools.product(*lists))
        params_s_dict = [dict(zip(keys, c)) for c in combinations]
        score_dict = {k: [] for k in combinations}
        for i, (inst, data_inst) in enumerate(data_dict.items()):
            print('Running instrument %s: %s / %s' % (inst, i, n - 1))

            data_tests = data_inst['tests']
            # Evaluating params on data
            if multip:
                out_dict = self.calibrate_single_multip(data_tests,
                                             backtest_class, model_class, 
                                             params_s_dict, cpu_percent)
            else:
                pass
                # out_dict = self.calibrate_single(data_train, data_tests,
                #                                 backtest_class, model_class, 
                #                                 btest_method, combinations)
            [score_dict[k].append(v) for k, v in out_dict.items()]
        return {k: self.cost_function(v, m) for k, v in score_dict.items()}

    def calibrate_single_multip(self, data_tests, backtest_class,
                         model_class, params_s_dict, cpu_percent):
        combinations = [tuple(x.values()) for x in params_s_dict]
        score_dict = {k: 0 for k in combinations}
        
        pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")


        # if not self.update_opt_param(params):
        #     continue
        # Calculate model
        # df_model = self.calc_model(data_train, data_tests, model_class,
        #                            params_m_dict)
        static_data = {
            'data_tests': data_tests,
            'backtest_class': backtest_class,
        }

        strategy_data = {
            'constructor': {**{'model_class': model_class}, **self.strategy.get_constructor_params()},
            'param_dict': self.strategy.param_dict
        }

        total_cores = cpu_count()
        # Ensure at least 2 cores are reserved for the system
        usable_cores = max(2, total_cores - 2) 
        # Calculate cores based on the specified percentage, rounding down but ensuring at least 1 core is used
        cores_to_use = max(1, min(math.floor(usable_cores * (cpu_percent / 100.0)), usable_cores))


        with Pool(processes=cores_to_use) as pool:
            async_results = [pool.apply_async(self.async_task, args=(self, strategy_data, static_data, params_dict, )) for params_dict in params_s_dict]

            # Periodically check progress and update the progress counter
            last_c = 0
            while True:
                completed = sum(1 for res in async_results if res.ready())
                diff_c = completed - last_c
                last_c = completed
                if diff_c > 0:
                    pbar.update(diff_c)
                # progress = (completed+COUNTER_) / (len(async_results)*len(params_dict_list['modl'])) * 100
                # sys.stdout.write(f'\rCompleted tasks: {progress:.2f}%')
                # sys.stdout.flush()

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
    def async_task(cls, strategy_data, static_data, params):
        strategy = cls.strategy.get_from_copy(strategy_data['constructor'])
        strategy.param_dict = strategy_data['param_dict']
        cls.strategy = strategy

        data_tests = static_data['data_tests']
        backtest_class = static_data['backtest_class']

        key = tuple(params.values())
        if not cls.update_opt_param(params):
            return None
        out_ser = cls.simulate_single(data_tests,
                                        backtest_class, params)
        return {key: cls.cost_function(out_ser.values, cls.method,
                                                diff_bool=False)}

    def simulate_single(self, data_tests,
                        backtest_class, params_dict):
        instr = list(data_tests.keys())[0]
        backtest_class.reset_time()
        self.strategy.reset()
        # Update parameters
        self.set_params(params_dict)
        # Prepare data
        df_ba = data_tests['ords']
        df_tr = data_tests['trds'].copy()
        data_dict = self.prepare_data(instr, backtest_class.__class__, df_ba, df_tr)
        # Simulate strategy
        return backtest_class.simulate_strategy(self.strategy,
                                        instr, data_dict)
    
    def simulate_strategy_params(self, data_tests, params_dict,
                                 backtest_class):
        instr = list(data_tests.keys())[0]
        backtest_class.reset_time()
        self.strategy.reset()
        # Update parameters
        self.set_params(params_dict)
        # Get model data for test period
        df_ba = data_tests['ords']

        df_tr = data_tests['trds'].copy()
        data_dict = self.prepare_data(instr, backtest_class.__class__,df_ba, df_tr)
        # Simulate strategy
        return backtest_class.simulate_strategy(self.strategy,
                                                instr, data_dict)
