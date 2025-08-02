# -*- coding: utf-8 -*-
"""
Created on Thu Sep 14 17:04:39 2023

@author: Marek
"""

import numpy as np
import pandas as pd
import itertools
import abc
import random
from tqdm import tqdm
import sys
# Async definition
from multiprocessing import Pool, Value, Lock
from time import sleep

tol = 1e-4


class Calibration():
    __metaclass__ = abc.ABCMeta
    def __init__(self, method, opt_param, fix_param, fix_value):
        self.method = method
        self.__opt_param = {k: np.nan for k in opt_param}
        self.__fix_param = {k: v for (k, v) in zip(fix_param, fix_value)}
        self.__prev_cost_val = np.inf

    @abc.abstractmethod
    def cost_function(self):
        pass

    @property
    def opt_param(self):
        return self.__opt_param

    @property
    def fix_param(self):
        return self.__fix_param

    def update_opt_param(self, param_dict):
        param_dict_l = self.opt_param
        keys = param_dict.keys()
        if not all([abs(param_dict[k] - param_dict_l[k]) < tol for k in keys]):
            self.__opt_param.update(param_dict)
            param_change = True
        else:
            param_change = False
        return param_change

    def __init_callback(self, num_max):
        self.__callback_dict['global_min'] = np.inf
        self.__callback_dict['num_max'] = num_max
        self.__callback_dict['niter'] = 0

    def callback(self, x, f, accepted):
        if accepted:
            self.__progress(x, f)
            if self.__callback_dict['global_min'] - f > 1e-3:
                self.__callback_dict['global_min'] = f
                self.__callback_dict['niter'] = 0
            else:
                self.__callback_dict['niter'] += 1
        else:
            self.__callback_dict['niter'] += 1

        if self.__callback_dict['niter'] > self.__callback_dict['num_max']:
            return True

    def show_history(self):
        return self.__itr_res
    
    def calibrate_p(self, args) :
        pass


class ModelCalibration(Calibration):
    def __init__(self, model_class, score_class, opt_param, fix_param_dict):
        fix_params = fix_param_dict.keys()
        fix_value = fix_param_dict.values()
        method = score_class.method
        super().__init__(method, opt_param, fix_params, fix_value)
        self.change_model(model_class)
        self.change_scoring(score_class)

    def cost_function(self, value_list, pct=1):
        value_list = sorted(value_list, reverse=True)
        idx = int(len(value_list) * pct)
        return mean(value_list[:idx])

    def change_model(self, model_class):
        self.model = model_class
        self.model.set_params(self.fix_param)

    def change_scoring(self, score_class):
        self.score = score_class

    def fit(self, X, y):
        pass

    def predict(self, X):
        pass

    def get_params(self, deep=True):
        pass

    def set_params(self, params):
        self.model.set_params(params)
        return self.model

    def calibrate_p(self, X, y, split_list, opt_param_dict):
        # Find test sequence index
        # tests_idx = [False if i < np.max(np.where(train_idx)) + 1 else True
        #              for i in range(len(train_idx))]
        # All combinations from param 
        keys = opt_param_dict.keys()
        lists = opt_param_dict.values()
        combinations = list(itertools.product(*lists))
        # Create dictionaries for each combination
        params_dict_list = [dict(zip(keys, combo)) for combo in combinations]
        score_dict = {k: [] for k in combinations}
        for (train_idx, tests_idx) in split_list:
            # Training sample
            X_train = X[train_idx, :]
            y_train = y[train_idx]
            # Testing sample
            X_tests = X[tests_idx, :]
            y_tests = y[tests_idx]
            # Training of data
            out_dict = self.calibrate_single(X_train, y_train, X_tests, y_tests,
                                             params_dict_list)
            [score_dict[k].append(v) for k, v in out_dict.items()]
        return {k: self.cost_function(v) for k, v in score_dict.items()}

    def calibrate_single(self, X_train, y_train, X_tests, y_tests,
                         params_dict_list):
        combinations = [tuple(x.values()) for x in params_dict_list]
        score_dict = {k: 0 for k in combinations}
        for params_dict in params_dict_list:
            key = tuple(params_dict.values())
            if not self.update_opt_param(params_dict):
                continue
            self.model.reset()
            self.score.reset()
            self.set_params(params_dict)
            # Train & test model
            y_pred_train = self.model.fit(X_train, y_train)
            y_pred_tests = self.model.fit(X_tests, y_tests)
            # Score calculation
            # Burn period
            burn = self.score.burn
            [self.score.score(y_p, y_n)
             for y_p, y_n in zip(y_pred_train[-burn:], y_train[-burn:])]
            # Test period
            score_list = [self.score.score(y_p, y_n)
                          for y_p, y_n in zip(y_pred_tests, y_tests)]
            if len(score_list) - self.score.burn < self.score.burn * .2:
                idx_s = 0
            else:
                idx_s = self.score.burn
            score_dict[key] = self.cost_function(score_list[idx_s:], .2)
        return score_dict


class MMStrategyCalibration(Calibration):
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

    def calibrate_p_old(self, data_dict, backtest_class, model_class, opt_param_dict,
                    btest_method, method='mean'):
        n = len(data_dict.keys())
        if method is None:
            m = self.method
        else:
            m = method
        # All combinations from param 
        keys = opt_param_dict.keys()
        lists = opt_param_dict.values()
        combinations = list(itertools.product(*lists))
        # Create dictionaries for each combination
        params_dict_list = [dict(zip(keys, combo)) for combo in combinations]
        score_dict = {k: [] for k in combinations}
        for i, (inst, data_inst) in enumerate(data_dict.items()):
            print('Running instrument %s: %s / %s' % (inst, i, n - 1))
            if not data_inst['train']:
                data_train = None
            else:
                data_train = data_inst['train']
            data_tests = data_inst['tests']
            # Evaluating params on data
            out_dict = self.calibrate_single(data_train, data_tests,
                                             backtest_class, model_class, 
                                             btest_method, params_dict_list)
            [score_dict[k].append(v) for k, v in out_dict.items()]
        return {k: self.cost_function(v, m) for k, v in score_dict.items()}

    def calibrate_p(self, data_dict, backtest_class, model_class, opt_param_dict,
                    btest_method, method='mean', multip=True, pct=.3):
        n = len(data_dict.keys())
        if method is None:
            m = self.method
        else:
            m = method
        # # All combinations from param 
        # keys = opt_param_dict.keys()
        # lists = opt_param_dict.values()
        # combinations = list(itertools.product(*lists))
        # rand_comb = random.sample(combinations, int(pct*len(combinations)))
        # # Model combinations
        # m_keys = [k for k in opt_param_dict.keys()
        #               if k in model_class.param_keys]
        # # m_lists = [v for k, v in opt_param_dict.items()
        # #               if k in model_class.param_keys]
        # # m_comb = list(itertools.product(*m_lists))
        # rand_combM = [tuple(c[i] for i, k in enumerate(keys) if k in m_keys)
        #               for c in rand_comb]
        # rand_combM = [x for x in set(rand_combM)]
        # # Strategy combinations
        # s_keys = [k for k in opt_param_dict.keys()
        #               if k not in model_class.param_keys]
        # # s_lists = [v for k, v in opt_param_dict.items()
        # #               if k not in model_class.param_keys]
        # # s_comb = list(itertools.product(*s_lists))
        # rand_combS = [tuple(c[i] for i, k in enumerate(keys) if k in s_keys)
        #               for c in rand_comb]
        # rand_combS = [x for x in set(rand_combS)]
        # # Create dictionaries for each combination
        # params_dict_list = {'comb': [dict(zip(keys, c)) for c in rand_comb],
        #                     'modl': [dict(zip(m_keys, c)) for c in rand_combM],
        #                     'strt': [dict(zip(s_keys, c)) for c in rand_combS]}
        # Generate all combinations
        keys = list(opt_param_dict.keys())
        lists = list(opt_param_dict.values())
        combinations = list(itertools.product(*lists))
        rand_comb = random.sample(combinations, int(pct*len(combinations)))
        
        # Model and Strategy keys
        m_keys = [k for k in keys if k in model_class.param_keys]
        s_keys = [k for k in keys if k not in model_class.param_keys]
        
        # Generate model and strategy combinations from rand_comb
        rand_combM = [tuple(c[i] for i, k in enumerate(keys) if k in m_keys) for c in rand_comb]
        rand_combS = [tuple(c[i] for i, k in enumerate(keys) if k in s_keys) for c in rand_comb]
        
        # Create dictionaries for model and strategy combinations
        model_dicts = [dict(zip(m_keys, m)) for m in set(rand_combM)]
        strategy_dicts = [dict(zip(s_keys, s)) for s in set(rand_combS)]
        
        # Mapping of model combinations to strategy combinations
        strt_to_modl_map = {}
        for c in rand_comb:
            m_comb = tuple(c[i] for i, k in enumerate(keys) if k in m_keys)
            s_comb = tuple(c[i] for i, k in enumerate(keys) if k in s_keys)
            s_dict = dict(zip(s_keys, s_comb))
            if m_comb not in strt_to_modl_map:
                strt_to_modl_map[m_comb] = []
            strt_to_modl_map[m_comb].append(s_dict)
        # Create the final structure
        params_dict_list = {
            'comb': [dict(zip(keys, c)) for c in rand_comb],
            'modl': model_dicts,
            'strt': strt_to_modl_map}

        score_dict = {k: [] for k in rand_comb}
        for i, (inst, data_inst) in enumerate(data_dict.items()):
            print('Running instrument %s: %s / %s' % (inst, i, n - 1))
            if not data_inst['train']:
                data_train = None
            else:
                data_train = data_inst['train']
            data_tests = data_inst['tests']
            model_class.inst = inst
            # Evaluating params on data
            if multip:
                out_dict = self.calibrate_single_multip(data_train, data_tests,
                                             backtest_class, model_class,
                                             btest_method, params_dict_list)
            else:
                out_dict = self.calibrate_single(data_train, data_tests,
                                                backtest_class, model_class, 
                                                btest_method, params_dict_list)
            [score_dict[k].append(v) for k, v in out_dict.items()]
        return {k: self.cost_function(v, m) for k, v in score_dict.items()}

    def calibrate_single_old(self, data_train, data_tests, backtest_class,
                         model_class, btest_method, params_dict_list):
        combinations = [tuple(x.values()) for x in params_dict_list]
        score_dict = {k: 0 for k in combinations}
        pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")
        for params_dict in params_dict_list:
            key = tuple(params_dict.values())
            if not self.update_opt_param(params_dict):
                continue
            # Simulate strategy
            out_ser = self.simulate_strategy_params(data_train, data_tests, params_dict,
                                                    backtest_class, model_class, btest_method)
            score_dict[key] = self.cost_function(out_ser.values, self.method)
            pbar.update(1)
        pbar.close()
        return score_dict

    def calibrate_single(self, data_train, data_tests, backtest_class,
                         model_class, btest_method, params_dict_list):
        combinations = [tuple(x.values()) for x in params_dict_list['comb']]
        score_dict = {k: 0 for k in combinations}
        pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")
        for params_m_dict in params_dict_list['modl']:
            if not self.update_opt_param(params_m_dict):
                continue
            key = tuple(params_m_dict.values())
            # Calculate model
            df_model = self.calc_model(data_train, data_tests, model_class,
                                       params_m_dict)
            for params_s_dict in params_dict_list['strt'][key]:
                params_a_dict = {**params_m_dict, **params_s_dict}
                params_dict = {k: params_a_dict[k] for k in self.opt_param.keys()}
                key = tuple(params_dict.values())
                if not self.update_opt_param(params_dict):
                    continue
                out_ser = self.simulate_single(data_tests, df_model,
                                               params_dict, btest_method,
                                               backtest_class, model_class)
                score_dict[key] = self.cost_function(out_ser.values, self.method,
                                                     diff_bool=True)
                pbar.update(1)
        pbar.close()
        return score_dict

    def calibrate_single_multip(self, data_train, data_tests, backtest_class,
                         model_class, btest_method, params_dict_list):
        combinations = [tuple(x.values()) for x in params_dict_list['comb']]
        score_dict = {k: 0 for k in combinations}
        # COUNTER_ = 0
        pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")

        for params_m_dict in params_dict_list['modl']:
            if not self.update_opt_param(params_m_dict):
                continue
            key = tuple(params_m_dict.values())
            # Calculate model
            df_model = self.calc_model(data_train, data_tests, model_class,
                                       params_m_dict)
            static_data = {
                'df_model': df_model,
                'params_m_dict': params_m_dict,
                'data_tests': data_tests,
                'btest_method': btest_method,
                'backtest_class': backtest_class,
                'model_class': model_class
            }

            strategy_data = {
                'constructor': self.strategy.get_constructor_params(),
                'param_dict': self.strategy.param_dict
            }

            with Pool() as pool:
                async_results = [pool.apply_async(self.async_task, args=(self, strategy_data, static_data, params_s_dict, )) for params_s_dict in params_dict_list['strt'][key]]

                # Periodically check progress and update the progress counter
                last_c = 0
                while True:
                    completed = sum(1 for res in async_results if res.ready())
                    diff_c = completed - last_c
                    last_c = completed
                    # if diff_c > 0:
                    pbar.update(diff_c)
                        # progress = (completed+COUNTER_) / (len(async_results)*len(params_dict_list['modl'])) * 100
                        # sys.stdout.write(f'\rCompleted tasks: {progress:.2f}%')
                        # sys.stdout.flush()

                    if completed == len(async_results):
                        break
                    sleep(.2)
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
    def async_task(cls, strategy_data, static_data, params_s_dict):
        strategy = cls.strategy.get_from_copy(strategy_data['constructor'])
        strategy.param_dict = strategy_data['param_dict']
        cls.strategy = strategy

        params_m_dict = static_data['params_m_dict']
        df_model = static_data['df_model']
        data_tests = static_data['data_tests']
        btest_method = static_data['btest_method']
        backtest_class = static_data['backtest_class']
        model_class = static_data['model_class']

        params_a_dict = {**params_m_dict, **params_s_dict}
        params_dict = {k: params_a_dict[k] for k in cls.opt_param.keys()}
        key = tuple(params_dict.values())
        if not cls.update_opt_param(params_dict):
            return None
        out_ser = cls.simulate_single(data_tests, df_model,
                                        params_dict, btest_method,
                                        backtest_class, model_class)
        return {key: cls.cost_function(out_ser.values, cls.method,
                                                diff_bool=True)}

    def calc_model(self, data_train, data_tests, model_class, params_dict):
        model_class.reset()
        model_class = self.set_model_params(model_class, params_dict)
        # Train & test model
        if not data_train:
            pass
        else:
            df_trained = model_class.predict(data_train)
        # Get model data for test period
        df_data = data_tests['ords']
        return model_class.mm_model_raw(df_data)

    def simulate_single(self, data_tests, raw_model, params_dict, btest_method,
                        backtest_class, model_class):
        instr = list(data_tests.keys())[0]
        backtest_class.reset_time()
        self.strategy.reset()
        # Update parameters
        self.set_params(params_dict)
        # Create bands
        df_model = model_class.mm_model(raw_model, {**params_dict,
                                                    **self.fix_param}, False)
        # Prepare data
        df_ba = data_tests['ords']
        df_tr = self.adjust_trds(data_tests['trds'].copy(), df_model)
        data_dict = self.prepare_data(instr, backtest_class.__class__,
                                      df_model, df_ba, df_tr)
        # Simulate strategy
        return backtest_class.simulate_strategy(self.strategy, btest_method,
                                                instr, data_dict)

    def simulate_strategy_params(self, data_train, data_tests, params_dict,
                                 backtest_class, model_class, btest_method):
        instr = list(data_tests.keys())[0]
        model_class.reset()
        backtest_class.reset_time()
        self.strategy.reset()
        # Update parameters
        self.set_params(params_dict)
        model_class = self.set_model_params(model_class, params_dict)
        # Train & test model
        if not data_train:
            pass
        else:
            df_trained = model_class.predict(data_train)
        # Get model data for test period
        df_ba = data_tests['ords']
        df_model = model_class.mm_model(df_ba, {**params_dict,
                                                **self.fix_param})
        df_tr = self.adjust_trds(data_tests['trds'].copy(), df_model)
        data_dict = self.prepare_data(instr, backtest_class.__class__,
                                      df_model, df_ba, df_tr)
        # Simulate strategy
        return backtest_class.simulate_strategy(self.strategy, btest_method,
                                                instr, data_dict)

    @staticmethod
    def prepare_data(instr, b_class, df_model, df_ba, df_tr):
        df_ba = df_ba.loc[df_model.index, :]
        data_dict = {}
        data_dict[instr] = b_class.merge_data(df_ba, df_tr, False)
        ts = data_dict[instr].index
        df_model = df_model[~df_model.index.duplicated(keep='first')]
        df_model = df_model.reindex(ts.drop_duplicates()).ffill()
        data_dict['output'] = df_model.loc[ts, :]
        return data_dict

    @staticmethod
    def adjust_trds(df_tr, df_model):
        df_model = df_model[~df_model.index.duplicated(keep='first')]
        timestamp = df_tr.index
        ts_new = df_model.index.union(timestamp).drop_duplicates()
        df_model = df_model.reindex(ts_new).ffill().loc[timestamp, :]
        lb = df_model.iloc[:, 0]
        ub = df_model.iloc[:, 2]
        df_tr.loc[lb.isna()] = np.nan
        df_tr.loc[(df_tr['price'] > ub) & (df_tr['action'] == 1), :] = np.nan
        df_tr.loc[(df_tr['price'] < lb) & (df_tr['action'] == -1), :] = np.nan
        return df_tr.dropna(how='all')


class MMModelCalibration(Calibration):
    def __init__(self, model_class, method, opt_param, fix_param_dict):
        fix_params = fix_param_dict.keys()
        fix_value = fix_param_dict.values()
        self.async_static_data = {}
        super().__init__(method, opt_param, fix_params, fix_value)
        self.change_model(model_class)

    def cost_function(self, value_list, pct=1):
        value_list = sorted(value_list, reverse=True)
        idx = int(len(value_list) * pct)
        return mean(value_list[:idx])

    def change_model(self, model_class):
        self.model = model_class
        self.set_params(self.fix_param)

    def set_params(self, params):
        self.model.update_params(params)
        return self.model

    @staticmethod
    def set_model_params(model_class, params):
        new_param_dict = {k: v for k, v in params.items()
                          if k in model_class.param_keys}
        model_class.update_params(new_param_dict)
        return model_class

    def calibrate_p(self, data_dict, ema_class, opt_param_dict):
        # All combinations from param 
        n = len(data_dict.keys())
        keys = opt_param_dict.keys()
        lists = opt_param_dict.values()
        combinations = list(itertools.product(*lists))
        # Tick Model combinations
        t_keys = [k for k in opt_param_dict.keys()
                  if k in ema_class.param_keys]
        t_lists = [v for k, v in opt_param_dict.items()
                   if k in ema_class.param_keys]
        t_comb = list(itertools.product(*t_lists))
        # Strategy combinations
        m_keys = [k for k in opt_param_dict.keys()
                  if k not in ema_class.param_keys]
        m_lists = [v for k, v in opt_param_dict.items()
                   if k not in ema_class.param_keys]
        m_comb = list(itertools.product(*m_lists))
        # Create dictionaries for each combination
        params_dict_list = {'comb': [dict(zip(keys, c)) for c in combinations],
                            'tick': [dict(zip(t_keys, c)) for c in t_comb],
                            'modl': [dict(zip(m_keys, c)) for c in m_comb]}
        score_dict = {k: [] for k in combinations}
        for i, (inst, data_inst) in enumerate(data_dict.items()):
            print('Running instrument %s: %s / %s' % (inst, i, n - 1))
            # pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")
            # for params_t_dict in params_dict_list['tick']:
            #     # Create ticks for underlying data
            #     X = self.prepare_data(data_inst['X'], ema_class, params_t_dict)
            #     for (train_idx, tests_idx) in split_list:
            #         # Training sample
            #         X_train = X[train_idx]
            #         # Testing sample
            #         X_tests = X[tests_idx]
            #         # Training of data
            #         out_dict = self.calibrate_single(X_train, X_tests,
            #                                          params_dict_list, pbar)             
            #         [score_dict[inst][k].append(v) for k, v in out_dict.items()]
            df_data = data_inst['X']
            split_list = data_inst['split_list']
            out_dict = self.calibrate_instr(df_data, ema_class, split_list,
                                            params_dict_list)
            [score_dict[k].append(v) for k, v in out_dict.items()]
        return score_dict
    
    def calibrate_instr(self, df_data, ema_class, split_list, params_dict_list):
        combinations = [tuple(x.values()) for x in params_dict_list['comb']]
        score_dict = {k: 0 for k in combinations}
        pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")
        for params_t_dict in params_dict_list['tick']:
            if not self.update_opt_param(params_t_dict):
                continue
            # Create ticks for underlying data
            ts = df_data.index
            X = self.prepare_data(df_data, ema_class, params_t_dict)
            # Model iteration
            for params_m_dict in params_dict_list['modl']:
                params_a_dict = {**params_t_dict, **params_m_dict}
                params_dict = {k: params_a_dict[k] for k in self.opt_param.keys()}
                key = tuple(params_dict.values())
                if not self.update_opt_param(params_dict):
                    continue
                score_list = []
                for (train_idx, tests_idx) in split_list:
                    # Training sample
                    X_train = X[train_idx]
                    # Testing sample
                    X_tests = X[tests_idx]
                    # Index score
                    ts_test = ts[tests_idx]
                    idx_s = [True]
                    idx_s.extend([False if abs(x - xt) > 0 else True for x, xt
                                  in zip(ts_test[:-1].day, ts_test[1:].day)])
                    # Training of data
                    score = self.run_model(X_train, X_tests, params_dict, idx_s)
                    score_list.append(score)
                score_dict[key] = mean(score_list)
                pbar.update(1)
        return score_dict
    
    def run_model(self, X_train, X_tests, params_dict, idx_score):
        self.model.reset()
        self.set_params(params_dict)
        # Train & test model
        if X_train.size == 0:
            pass
        else:
            x, P = self.model.fit(X_train)
            self.model.soft_reset()
        # Test and evaluate score
        x, P = self.model.fit(X_tests)
        return self.model.score(idx_score=idx_score)

    def prepare_data(self, data_series, ema_class, params_dict):
        ema_class.reset()
        ema_class = self.set_model_params(ema_class, params_dict)
        # Calculate ema model on data
        df_ema = ema_class.mm_model_raw(data_series)
        return (data_series.iloc[:, 0] - df_ema.iloc[:, 0]).values.reshape(-1,)

    def simulate_model(self, data_dict, ema_class, dt_class, params_dict):
        out_dict = {k: [] for k in data_dict.keys()}
        self.set_params(params_dict)
        ema_class = self.set_model_params(ema_class, params_dict)
        dt_class = self.set_model_params(dt_class, params_dict)
        for inst, data_inst in data_dict.items():
            # Reset models
            self.model.reset()
            ema_class.reset()
            dt_class.reset()
            # Calculate ema model on data
            df_data = data_inst['X']
            df_ema = ema_class.mm_model_raw(df_data)
            # ML estimate of parameters
            X_data = (df_data.iloc[:, 0] - df_ema.iloc[:, 0]).values.reshape(-1,)
            df_period = pd.Series(self.model.calc_period(X_data), index=df_data.index)
            # Calculate derivation model on data
            df_dt = dt_class.mm_model_raw(df_data)
            # Unify models
            df_model = df_ema.iloc[:, 0] + df_dt.iloc[:, 0] * df_period
            out_dict[inst] = pd.concat([df_model, df_ema.iloc[:, 1]], axis=1)
        return out_dict


def mean(value_list):
    return sum(value_list) / len(value_list)


def sharp_ratio(value_list):
    return np.mean(value_list) / np.std(value_list)

