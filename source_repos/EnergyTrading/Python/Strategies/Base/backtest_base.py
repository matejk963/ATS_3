import numpy as np
import abc
import pandas as pd

tol = 1e-6

class BacktestClass():
    __metaclass__ = abc.ABCMeta
    
    current_t = 0
    nT = 0
    volm_class = None
    trade_type = []
    pnl_dict = {}
    prices_dict = {}
    
    def __init__(self, volm_class, trade_type):
        self.volm_class = volm_class
        self.trade_type = trade_type
        pnl_list = ['timestamp', 'pnl', 'mtm', 'vol']
        self.pnl_dict = {k: [] for k in pnl_list}

    @abc.abstractmethod
    def simulate_strategy(self):
        pass

    @property
    def is_active(self):
        if self.current_t + 1 <= self.nT:
            active = True
        else:
            active = False
        return active

    @property
    def curr_profit(self):
        val_pnl = sum(self.pnl_dict['pnl'])
        val_mtm = sum(self.mtm_dict['mtm'])
        return val_pnl + val_mtm

    @property
    def profit_series(self):
        # Cummulative profit series
        vol = self.volm_class.base_volume
        pnl_list = self.pnl_dict['pnl']
        mtm_list = self.pnl_dict['mtm']
        profit_list = np.cumsum([(p + m) / vol for p, m in
                                 zip(pnl_list, mtm_list)])
        return pd.Series(profit_list, index=self.pnl_dict['timestamp'])

    @property
    def profit_active_series(self):
        # Cummulative profit series
        vol = self.volm_class.base_volume
        pos_list = self.pnl_dict['vol']
        pnl_list = self.pnl_dict['pnl']
        mtm_list = self.pnl_dict['mtm']
        tst_list = self.pnl_dict['timestamp']
        profit_list = np.cumsum([(p + m) / vol for p, m, v in
                                 zip(pnl_list, mtm_list, pos_list)
                                 if abs(v) > 0])
        ts_list = [t for t, v in zip(tst_list, pos_list) if abs(v) > 0]
        return pd.Series(profit_list, index=ts_list)

    @property
    def profit_trade_series(self):
        vol = self.volm_class.base_volume
        pos_list = self.pnl_dict['vol']
        pnl_list = self.pnl_dict['pnl']
        mtm_list = self.pnl_dict['mtm']
        tst_list = self.pnl_dict['timestamp']
        dpos_list = [0]
        dpos_list = [x - y for x, y in zip(pos_list[:-1], pos_list[1:])]
        cls_list = [True if abs(x) > 0  and v == 0 else False
                    for x, v in zip(dpos_list, pos_list)]
        prof_list = np.cumsum([(p + m) / vol for p, m in
                               zip(pnl_list, mtm_list)])
        ts_list = [t for t, a in zip(tst_list, cls_list) if a]
        profit_list = [p for p, a in zip(prof_list, cls_list) if a]
        return pd.Series(profit_list, index=ts_list)

    def trades_summary(self, freq):
        # Position summary
        pos_list = self.pnl_dict['vol']
        dpos_list = [x - y for x, y in zip(pos_list[:-1], pos_list[1:])]
        dpos_list.append(0)
        act_list = [0 if x == 0 else 1 for x in dpos_list]
        act_series = pd.Series(act_list, index=self.pnl_dict['timestamp'])
        return act_series.resample(freq).sum() / 2

    def execute(self, strategy_class, vol):
        if strategy_class.last_status in ['BID', 'ASK']:
            pass
        else:
            volume = vol
        return volume

    def save_trade(self, data_dict, price, vol, position):
        # Append profit from last trade
        timestamp_ = data_dict['timestamp']
        price_1 = data_dict['mid_price']
        price_0 = self.prices_dict['mid_price']
        # PNL
        val_pnl = -price * vol
        # MTM
        val_mtm = (price_1 - price_0) * (position - vol) + price_1 * vol
        self.pnl_dict['timestamp'].append(timestamp_)
        self.pnl_dict['pnl'].append(val_pnl)
        self.pnl_dict['mtm'].append(val_mtm)
        self.pnl_dict['vol'].append(position)

    def reset_time(self):
        self.current_t = 0
        self.nT = 0
        self.pnl_dict = {k: [] for k in self.pnl_dict.keys()}
        self.prices_dict = {k: [] for k in self.prices_dict.keys()}
        self.volm_class.reset()
        self.__LoB_num = 0

    def progress_time(self):
        self.current_t += 1
