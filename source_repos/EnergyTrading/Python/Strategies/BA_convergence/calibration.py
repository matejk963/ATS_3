import pandas as pd
import numpy as np
import time
import itertools
import abc
from tqdm import tqdm
import sys
import random
# Async definition
from multiprocessing import Pool, cpu_count
import math
# Local packages
from Calibration.calibration_class import Calibration
from Utilities.cost_functions import cost_function

class LLStrategyCalibration(Calibration):
    def __init__(self, strategy_class, method, opt_param, fix_param_dict):
        fix_params = fix_param_dict.keys()
        fix_value = fix_param_dict.values()
        super().__init__(method, opt_param, fix_params, fix_value)
        self.change_strategy(strategy_class)

    def change_strategy(self, strategy_class):
        self.strategy = strategy_class
        self.set_params(self.fix_param)

    def cost_function(self, value_list, methods, diff_bool=False):
        return cost_function(value_list, methods)

    def set_params(self, params):
        # new_param_dict = {k: v for k, v in params.items()
        #                   if k in self.strategy.param_list}
        new_param_dict = {k: v if k not in params.keys() else params[k]
                          for k, v in self.strategy.param_dict.items()}
        self.strategy.param_dict.update(new_param_dict)
        return self.strategy

    def calibrate_p(self, data_lag,  backtest_class, opt_params,  method='mean', multip=True, cpu_percent=90, instr='m2'):
        # n = len(data_dict.keys())
        if method is None:
            m = self.method
        else:
            m = method


        keys = opt_params.keys()
        # All combinations from param
        lists = opt_params.values()
        combinations = list(itertools.product(*lists))
        params_s_dict = [dict(zip(keys, c)) for c in combinations]
        #params_s_dict=random.sample(params_s_dict, 10000)
        score_dict = {k.values(): [] for k in params_s_dict}
        # for i, (inst, data_inst) in enumerate(data_dict.items()):


        # data_tests = data
        # Evaluating params on data
        if multip:
            out_dict = self.calibrate_single_multip(data_lag,
                                         backtest_class,
                                         params_s_dict, cpu_percent, instr)
        else:
            pass
            # out_dict = self.calibrate_single(data_train, data_tests,
            #                                 backtest_class, model_class,
            #                                 btest_method, combinations)
        #[score_dict[k].append(v) for k, v in out_dict.items()]
        return out_dict#{k: self.cost_function(v, m) for k, v in score_dict.items()}

    def calibrate_single_multip(self, data_lag, backtest_class,
                          params_s_dict, cpu_percent, instr):
        combinations = [tuple(x.values()) for x in params_s_dict]
        score_dict = {k: 0 for k in combinations}

        pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")


        # if not self.update_opt_param(params):
        #     continue
        # Calculate model
        # df_model = self.calc_model(data_train, data_tests, model_class,
        #                            params_m_dict)
        static_data = {
            'data_lag': data_lag.reset_index(),
            'backtest_class': backtest_class,
            'instr': instr
        }

        strategy_data = {
            'constructor': {**self.strategy.get_constructor_params()},
            'param_dict': self.strategy.param_dict,
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
        strategy = cls.strategy#.get_from_copy(strategy_data['constructor'])
        strategy.param_dict = strategy_data['param_dict']
        cls.strategy = strategy

        data_lag = static_data['data_lag']

        backtest_class = static_data['backtest_class']
        instr=static_data['instr']

        key = tuple(params.values())
        if not cls.update_opt_param(params):
            return None
        out_ser = cls.simulate_single(data_lag,
                                        backtest_class, params, instr)

        output=cls.cost_function(out_ser.values, cls.method,
                          diff_bool=False)

        if not isinstance(output, list):
            output=[output]

        output_df = pd.DataFrame({k: strategy.stats_dict[k] for k in strategy.stats_dict.keys() if
                           k in ['timestamp', 'position', 'price_level']})
        output_df = pd.concat([output_df, ])

        num_trades=len(output_df[output_df['position'] != 0])
        num_days=len(set(out_ser.index.date))

        trades_per_day=num_trades/num_days

        # accuracy caluclation
        output_df['price_level'] = output_df['price_level'] - output_df['position'] * 0.0175
        output_df['revenue'] = -1 * output_df['position'] * output_df['price_level']

        even_index = output_df.iloc[1::2]['revenue'].reset_index(drop=True)  # Rows 1, 3, 5, ...
        odd_index = output_df.iloc[0::2]['revenue'].reset_index(drop=True)  # Rows 0, 2, 4, ...

        # Subtract odd-indexed rows from even-indexed rows
        difference = even_index + odd_index
        reutrn_df = pd.DataFrame(difference)
        reutrn_df.columns = ['returns']

        accuracy = sum(reutrn_df['returns'] > 0) / len(reutrn_df) if len(reutrn_df) > 0 else 0

        output=output+[num_trades, trades_per_day, accuracy]

        return {key: output}

    def simulate_single(self, data_lag, backtest_class, params_dict, instr):

        backtest_class.reset_time()
        self.strategy.reset()
        # Update parameters
        self.set_params(params_dict)
        #print(self.strategy.param_dict)
        # Simulate strategy
        return backtest_class.simulate_strategy(self.strategy, instr, data_lag)


