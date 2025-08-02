# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
from datetime import datetime, time
from tqdm.notebook import tqdm


from Strategies.Base.backtest_base import BacktestClass


class BacktestModular():
    def __init__(self):
        super().__init__()
        self._price_list = ['timestamp', 'mid_price', 'bid_price', 'ask_price',
                      'trd_price', 'trd_side']
        self.prices_dict = {k: [] for k in self._price_list}
        self.processed_idxs = []
        self.open_positions_idxs = []

    def simulate_strategy(self, strategy, df_data, idxs, cached_returns=None, not_verbose=True):
        # Simulate strategy defined by strategy class
        # Prepare data
        progress_bar = tqdm(total=len(idxs), disable=not_verbose) 
        open_flag = False
        end_flag = False
        idx_counter = 0
        prev_idx = 0
        last_idx = 0
        
        while (idx_counter < len(idxs)):
            position = strategy.get_open_position()

            if position == 0:
                if open_flag:
                    open_flag = False

                while last_idx >= idxs[idx_counter]:
                    if idx_counter + 1 >= len(idxs):
                        end_flag = True
                        break
                    idx_counter += 1
                    progress_bar.update(1)

                last_idx = idxs[idx_counter]

            else:
                if not open_flag:
                    self.open_positions_idxs.append(last_idx)
                    open_flag = True
                if cached_returns:
                    last_idx += cached_returns[idxs[idx_counter]]["long" if position > 0 else "short"][0]
                else:
                    last_idx += 1

            if last_idx < prev_idx:
                print("wut")
            prev_idx = last_idx
            
            # Get the row directly from DataFrame instead of dictionary
            row_data = df_data.loc[last_idx]
            
            # Convert to dictionary only for this specific row (much more efficient)
            row_dict = row_data.to_dict()
            
            price, vol = strategy.process(row_dict)
            self.processed_idxs.append(last_idx)
            
            # Update last prices - only convert the specific row we need
            self.prices_dict.update(row_dict)
            
            position = strategy.get_open_position()
            if vol == 0 and position == 0:
                idx_counter += 1
                # Update the progress bar
                progress_bar.update(1)
        progress_bar.close()
    
    def cache_return(self, strategy, np_arr, idxs) -> dict:
        return_dict = {}

        for idx in idxs:
            try:
                np_data = np_arr[np.where(np_arr[:, 0] >= idx)]
                short_r, long_r = None, None
                
                strategy.position_dict = strategy.init_position_dict
                i, j = 0, 0

                for row in np_data:              
                    short_r = strategy.simulate_position_short(row)
                    if short_r:
                        break
                    i += 1
        
                strategy.position_dict = strategy.init_position_dict
                for row in np_data:
                    long_r = strategy.simulate_position_long(row)
                    if long_r:
                        break
                    j += 1
        
                return_dict[idx] = {
                    'short': (i, round(short_r, 2)),
                    'long': (j, round(long_r, 2))
                }
            except Exception as e:
                print("i", i, "j", j)
                print("Position dict", strategy.position_dict)
                print("index", idx)
                print("np data shape", np_data.shape)
        return return_dict


    def cost_function(self, output_series, method):
        # Process output from calibration
        ret = np.diff(output_series.values, n=1)
        if method == 'avg':
            output_val = -np.mean(ret)
        elif method == 'std':
            output_val = np.std(ret)
        elif method == 'sharp':
            output_val = -np.mean(ret) / np.std(ret)
        elif method == 'cumpnl':
            output_val = -ret[-1]
        else:
            ValueError('backtest_class: cost function unknown method :', method)
        return output_val
    
    
    @staticmethod
    def calc_returns_new(strategy):
        df = pd.DataFrame({k: strategy.stats_dict[k] for k in strategy.stats_dict.keys() if k in [
            'timestamp', 'position', 'action', 'price_level', 'open_price']})
        df['open_price'] = df['open_price'].ffill()
        last_position = None
        returns = []
        is_closing = lambda x, y: abs(y) < abs(x)
        
        for row in df.to_dict(orient='records'):
            if last_position is None:
                # For the first row, include it but set return as 0 since it's opening a position
                r = 0
                returns.append({'timestamp': row['timestamp'],
                            'position': row['position'],
                            'action': row['action'],
                            'open_price': row['open_price'],
                            'price_level': row['price_level'],
                            'returns': r*abs(row['action'])})
                last_position = row['position']
                continue
                
            if is_closing(last_position, row['position']):
                if row['action'] > 0:
                    # closing short
                    r = row['open_price'] - row['price_level']
                else:
                    # closing long
                    r = row['price_level'] - row['open_price']
            else:
                r = np.nan
                
            returns.append({'timestamp': row['timestamp'],
                        'position': row['position'],
                        'action': row['action'],
                        'open_price': row['open_price'],
                        'price_level': row['price_level'],
                        'returns': r*abs(row['action'])})
            
            # Update last_position for the next iteration
            last_position = row['position']
            
        return pd.DataFrame(returns)
