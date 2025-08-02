# -*- coding: utf-8 -*-
"""
Created on Fri Mar 25 10:27:25 2022

@author: zelenaymar
"""

import numpy as np
import pandas as pd
from datetime import datetime, time
import matplotlib.pyplot as plt
from OrderBook.OrderBook import OrderBookSnaps

from Utilities.data_functions import clean_data
l_path = '//192.168.10.91/date/Data/orderbooks/base/'
l_path = r'W:\Data\orderbooks\base/'
# l_path = r'Z:\Data\orderbooks\base'


class SpreadViewer():
    def __init__(self):
        self.spread_dict = {}
        self.n = 0


class SpreadSingle():
    def __init__(self, market_list, tenor_list, tn1_list, tn2_list=[],
                 brk_list=[]):
        self.market_list = market_list
        self.tenor_list = tenor_list
        self.tn1_list = tn1_list
        self.tn2_list = tn2_list
        if not brk_list:
            self._brk_list = ['otc', 'ice', 'eex']
        else:
            self._brk_list = brk_list

    def tenor(self, tenor):
        out_dict = {}
        out_dict['m1q'] = 'm'
        out_dict['m2q'] = 'm'
        out_dict['m3q'] = 'm'
        out_dict['q1y'] = 'q'
        out_dict['q2y'] = 'q'
        out_dict['q3y'] = 'q'
        out_dict['q4y'] = 'q'
        try:
            return out_dict[tenor]
        except(KeyError):
            return tenor

    @property
    def tenors_list(self):
        if not self.tn2_list:
            return [self.tenor(t) + '_' + str(n) for t, n in zip(self.tenor_list, self.tn1_list)]
        else:
            return [self.tenor(t) + '_' + str(n1) + '_' + str(n2) for t, n1, n2 in
                    zip(self.tenor_list, self.tn1_list, self.tn2_list)]

    def product_dates(self, dates, n_s, tn_bool=True):
        if tn_bool:
            tn_list = self.tn1_list
        else:
            tn_list = self.tn2_list
        if not tn_list:
            return [None] * len(self.tenor_list)
        # Product dates
        pd_list = [dates.shift(1, freq='B') if ((t == 'da') or (t == 'd')) else
                   dates.shift(tn, freq='W-MON') if t == 'w' else
                   dates.shift(tn, freq='YS') if t == 'dec' else
                   dates.shift(tn, freq='QS') if t == 'm1q' else
                   (dates + n_s * dates.freq).shift(tn, freq='AS-Apr') if t in ['sum'] else
                   (dates + n_s * dates.freq).shift(tn, freq='AS-Oct') if t in ['win'] else
                   (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                   for t, tn in zip(self.tenor_list, tn_list)]
        return pd_list

    def unify_data(self, data_dict, fillna=True, col_list=['bid', 'ask']):
        data_ = pd.DataFrame([], dtype=float)
        for m, t in zip(self.market_list, self.tenors_list):
            aux_dict = {m + '_' + t + '_' + c: data_dict[m][t][c] for c in col_list}
            data_ = data_.merge(pd.DataFrame(aux_dict), 'outer',
                                left_index=True,right_index=True)
        if fillna:
            data_ = data_.ffill()
        else:
            pass
        data_dict_ = {m: {} for m in self.market_list}
        for m, t in zip(self.market_list, self.tenors_list):
            data_dict_[m][t] = {k: data_.loc[:, m + '_' + t + '_' + k].rename(k)
                                for k in col_list}
        return data_dict_

    def __get_series_best_otc(self, market, tenor, data_class, p1_d, p2_d,
                              bT, eT, start_time, end_time, gran, prod):
        venue_list = ['eex']
        mkt_l = ['bidbestprice', 'askbestprice']
        data_loader = data_class.data[market][tenor]
        bT_ = datetime.combine(bT, start_time)
        eT_ = datetime.combine(eT, end_time)
        t = tenor.split('_')[0]
        print('Loading data...\n')
        print(f'BO for market & date: {market} // {tenor} & {bT} // {eT} \n')
        ts_s = datetime.now().timestamp()
        data_loader.create_connection('PostgreSQL')
        data = data_loader.get_best_ob_data(market, t, venue_list, p1_d,
                                            bT_, eT_, prod, p2_d)
        data = data.between_time(start_time, end_time)
        # mid_series = .5 * (data.iloc[:, 0] + data.iloc[:, 1])
        # data = data_loader.filter_data(data, mid_series, 20)
        ts_e = datetime.now().timestamp()
        print('Data load completed in %d sec.\n' % (ts_e - ts_s))
        data = data.rename(columns={k: k[:3] for k in mkt_l})
        return data

    def __get_series_best_tp(self, market, tenor, data_class, p1_d, p2_d,
                             bT, eT, start_time, end_time, gran, prod):
        venue_list = self._brk_list
        mkt_l = ['bidbestprice', 'askbestprice']
        data_loader = data_class.data[market][tenor]
        bT_ = datetime.combine(bT, start_time)
        eT_ = datetime.combine(eT, end_time)
        t = tenor.split('_')[0]
        print('Loading data...\n')
        print(f'BO for market & date: {market} // {tenor} & {bT} // {eT} \n')
        ts_s = datetime.now().timestamp()
        data_loader.create_connection('PostgreSQL')
        data = data_loader.get_best_ob_data(market, t, venue_list, p1_d,
                                            bT_, eT_, prod, p2_d)
        data = data.between_time(start_time, end_time)
        # mid_series = .5 * (data.iloc[:, 0] + data.iloc[:, 1])
        # data = data_loader.filter_data(data, mid_series, 20)
        ts_e = datetime.now().timestamp()
        print('Data load completed in %d sec.\n' % (ts_e - ts_s))
        data = data.rename(columns={k: k[:3] for k in mkt_l})
        return data

    def __get_series_best_ob(self, market, tenor, data_class, depth,
                             start_date, end_date, start_time, end_time, gran):
        bTs = datetime.combine(start_date, start_time)
        eTs = datetime.combine(end_date, end_time)
        stor_class = data_class.data[market][tenor]
        LoB, ts_list = stor_class.LoB_select(start_date, end_date, start_time,
                                             end_time, freq=gran)
        LoB_class = OrderBookSnaps(verbose=True)
        LoB_class.update_data(LoB, ts_list)
        if depth == 0:
            series_bid = LoB_class.best_bid_all
            series_ask = LoB_class.best_ask_all
        else:
            series_bid = LoB_class.price_vol_bid(depth)
            series_ask = LoB_class.price_vol_ask(depth)
        LoB_class.clear()
        variable_dict = {'bid': series_bid.tolist(), 'ask': series_ask.tolist()}
        variable_dict = clean_data(variable_dict, 'bid', 'ask', 'mid_price',
                                   'ba_price', factor=10)
        df_data = pd.DataFrame({k: variable_dict[k] for k in ['bid', 'ask']},
                               index=series_bid.index)
        return df_data.loc[bTs:eTs, :]

    def __get_series_trd_otc(self, market, tenor, data_class, p1_d, p2_d,
                             bT, eT, start_time, end_time, prod, gran,
                             data_dict_):
        venues = self._brk_list
        data_loader = data_class.data[market][tenor]
        t = tenor.split('_')[0]
        print('Loading data...\n')
        print(f'Trades for market & date: {market} // {tenor} & {bT} // {eT} \n')
        ts_s = datetime.now().timestamp()
        data_loader.create_connection('OracleSQL')

        data = data_loader.get_trades(market, t, venues, p1_d,
                                      bT, eT, prod, p2_d)
        data = data.rename_axis('datetime')
        data = data.between_time(start_time, end_time)
        if not data_dict_:
            data = data[data['broker_id']==1441]
            # data = data_loader.filter_data(data, data['price'], 20)
        else:
            df_ba = pd.concat([x for x in data_dict_[market][tenor].values()], axis=1)
            df_ba = df_ba.rename(columns={'bid': 'b_price', 'ask': 'a_price'})
            data = data_loader.clean_trades(data, df_ba)
        ts_e = datetime.now().timestamp()
        print('Data load completed in %d sec.\n' % (ts_e - ts_s))

        # Divide between Buy & Sell trades
        # act_list = data['action'].values.tolist()
        val_list = data['price'].values.tolist()
        vol_list = data['volume'].values.tolist()
        brk_list = data['broker_id'].values.tolist()
        if not data_dict_:
            act_list = data['action'].values.tolist()
        else:
            
            mid_series = .5 * (data_dict_[market][tenor]['bid'] +
                               data_dict_[market][tenor]['ask'])
            mid_series.index.name = 'timestamp'
            df_reset = data.reset_index()
            df_reset = df_reset.drop_duplicates(subset='datetime', keep='first').set_index('datetime')
            ts_new = mid_series.index.union(df_reset.index)
            mid_series = mid_series.reset_index().drop_duplicates(subset='timestamp', keep='first').set_index('timestamp')
            mid_series = mid_series.reindex(ts_new).ffill().loc[data.index]
            #mid_df = mid_series.reindex(ts_new).ffill().reset_index()
            #mid_df = mid_df.drop_duplicates(subset='index', keep='first').set_index('index')
            #mid_series = mid_df.squeeze().loc[data.index]
            mid_list = mid_series[0].tolist()
            act_list = [-1 if p >= m else 1 for p, m in zip(val_list, mid_list)]
        bid_list = [v if x == 1 else np.nan for v, x in zip(val_list, act_list)]
        ask_list = [v if x == -1 else np.nan for v, x in zip(val_list, act_list)]
        # data_dict = {'bid': bid_list, 'ask': ask_list}
        data_aux_dict = {'volume': vol_list, 'broker_id': brk_list}
        agg_dict = {'volume': 'sum', 'broker_id': 'first'}
        #
        bid_vol_list = [v if x == 1 else np.nan for v, x in zip(vol_list, act_list)]
        ask_vol_list = [v if x == -1 else np.nan for v, x in zip(vol_list, act_list)]
        df_val = pd.DataFrame({'bid': [p * v for p, v in zip(bid_list, bid_vol_list)],
                               'ask': [p * v for p, v in zip(ask_list, ask_vol_list)]},
                              index=data.index)
        df_vol = pd.DataFrame({'bid': bid_vol_list, 'ask': ask_vol_list},
                              index = data.index)
        if gran is None:
            df_vol_aux = df_vol.groupby(data.index).sum()
            df_data = df_val.groupby(data.index).sum() / df_vol_aux
            # df_data = pd.DataFrame(data_dict, index=data.index)
            df_data_aux = pd.DataFrame(data_aux_dict, index=data.index)
            df_data_aux = df_data_aux.groupby(data.index).agg(agg_dict)
        else:
            df_data = df_val.resample(gran).sum() / df_vol.resample(gran).sum()
            df_data_aux = pd.DataFrame(data_aux_dict, index=data.index).resample(gran).agg(agg_dict)
        df_data = pd.concat([df_data, df_data_aux], axis=1)
        return df_data

    def __get_series_trdvol_otc(self, market, tenor, data_class, p1_d, p2_d,
                                bT, eT, start_time, end_time, prod, gran):
        venues = self._brk_list
        data_loader = data_class.data[market][tenor]
        t = tenor.split('_')[0]
        print('Loading data...\n')
        print(f'TrdVol for market & date: {market} // {tenor} & {bT} // {eT} \n')
        ts_s = datetime.now().timestamp()
        data_loader.create_connection('OracleSQL')

        data = data_loader.get_trades(market, t, venues, p1_d,
                                      bT, eT, prod, p2_d)
        data = data.between_time(start_time, end_time)
        # data = data_loader.filter_data(data, data['price'], 20)
        ts_e = datetime.now().timestamp()
        print('Data load completed in %d sec.\n' % (ts_e - ts_s))

        # Divide between Buy & Sell trades
        timestamp = data['price'].index
        val_list = data['price'].values.tolist()
        vol_list = data['volume'].values.tolist()
        brk_list = data['broker_id'].values.tolist()
        # Filter through brokers
        idx_brk = [True if venue_dict(b) in self._brk_list else False
                   for b in brk_list]
        data_dict = {'price': [x for x, i in zip(val_list, idx_brk) if i],
                     'vol': [x for x, i in zip(vol_list, idx_brk) if i]}
        if gran is None:
            df_data = pd.DataFrame(data_dict, index=timestamp[idx_brk])
            df_data = df_data.groupby(df_data.index).agg({'price': 'mean',
                                                          'vol': 'sum'})
        else:
            df_val = pd.DataFrame({'price': [p * v for p, v in zip(val_list, vol_list)],
                                   'vol': vol_list}, index=timestamp[idx_brk])
            df_data = df_val.resample(gran).sum()
            df_data['price'] /= df_data['vol']
        return df_data

    def __get_index_inst_trd(self, market, data_class, start_date, end_date,
                             start_time, end_time):
        venues = self._brk_list
        data_loader = data_class
        print(f'Loading data Trade Inst for dates {start_date} // {end_date} \n')
        data_loader.create_connection('OracleSQL')
        data = data_class.get_trades_inst(market, venues, start_date, end_date,
                                          prod='base', spread_bool=False)
        data = data.between_time(start_time, end_time)
        return data.index

    def get_time_index(self, market, data_class, gran, start_date, end_date,
                       start_time, end_time):
        if gran == 'optu':
            return self.__get_index_inst_trd(market, data_class, start_date,
                                             end_date, start_time, end_time)
        else:
            return None

    def get_price_series(self, market, tenor, data_class, prod_d1, prod_d2, 
                         start_date, end_date, start_time, end_time,
                         prod, gran, depth, data_dict):
        tenor = self.tenor(tenor)
        if data_class.data_type == 'best_order_otc':
            return self.__get_series_best_otc(market, tenor, data_class,
                                              prod_d1, prod_d2, start_date,
                                              end_date, start_time, end_time,
                                              gran, prod)
        elif data_class.data_type == 'order_book':
            return self.__get_series_best_ob(market, tenor, data_class, depth,
                                             start_date, end_date, start_time,
                                             end_time, gran)
        elif data_class.data_type == 'best_order_tp':
            return self.__get_series_best_tp(market, tenor, data_class,
                                             prod_d1, prod_d2, start_date,
                                             end_date, start_time, end_time,
                                             gran, prod)
        elif data_class.data_type == 'trades_otc':
            return self.__get_series_trd_otc(market, tenor, data_class,
                                             prod_d1, prod_d2, start_date,
                                             end_date, start_time, end_time,
                                             prod, gran, data_dict)
        # elif data_class.data_type == 'trade_vol_otc':
        #     return self.__get_series_trdvol_otc(market, tenor, data_class, fbT,
        #                                         start_date, end_date, start_time,
        #                                         end_time, gran)
        else:
            ValueError('Unknown data type %s.\n' % data_class.data_type)

    def aggregate_data(self, data_class, dates, n_s=1, gran=None,
                       depth=0, start_time=time.min, end_time=time.max,
                       col_list=['bid', 'ask'], data_dict={}):
        # Output
        data_ = {m: {} for m in self.market_list}
        for m, t in zip(self.market_list, self.tenors_list):
            data_[m][t] = {k: pd.Series([], dtype=float) for k in col_list}
        # Check data availability
        if data_class.state == 0:
            return data_
        # Product dates
        pd1_list = self.product_dates(dates, n_s, True)
        pd2_list = self.product_dates(dates, n_s, False)
        for m, t, p1_d, p2_d in zip(self.market_list, self.tenors_list,
                                    pd1_list, pd2_list):
            if p2_d is None:
                df_prod_dates = pd.DataFrame([p1_d], columns=dates).T
            else:
                df_prod_dates = pd.DataFrame([p1_d, p2_d], columns=dates).T
            for p_d, ds in df_prod_dates.groupby(0).groups.items():
                sD = datetime.combine(ds[0], start_time)
                eD = datetime.combine(ds[-1], end_time)
                if p2_d is None:
                    pd_2 = None
                else:
                    pd_2 = df_prod_dates.loc[ds[0], 1]
                try:
                    df_ba = self.get_price_series(m, t, data_class, p_d, pd_2, sD, eD,
                                                  start_time, end_time, 'base',
                                                  gran, depth, data_dict)
                except Exception as e:
                    if str(e) == 'No Trades for criteria':
                        print('No Trades for criteria, continuing...')
                        continue
                    else:
                        print(f'Unexpected exception: {e}')
                        break
                for c in col_list:
                    if not data_[m][t][c].empty:
                        data_[m][t][c] = pd.concat([data_[m][t][c], df_ba.loc[:, c]], axis=0)
                    else:
                        data_[m][t][c] = df_ba.loc[:, c]
                del df_ba
        # Unify data
        if data_class.data_type in ['trades_otc', 'trade_vol_otc']:
            fillna = False
        else:
            fillna = True
        data_ = self.unify_data(data_, fillna, col_list)
        return data_

    def spread_maker(self, data_dict, coeff_list, trade_type=[]):
        n = len(self.market_list)
        market_list = self.market_list
        tenors_list = self.tenors_list
        if not trade_type:
            trade_type = ['mid'] * n
        aux_series = data_dict[market_list[0]][tenors_list[0]]['bid']
        # Data spread
        data_ = {k: pd.Series([0] * aux_series.size, index=aux_series.index, name=k)
                 for k in ['bid', 'ask']}
        # Check if trade type is combined
        if all([x == 'cmb' for x in trade_type]):
            trade_type_list = [['mm' if i == j else 'agg' for i in enumerate(range(n))]
                               for j in enumerate(range(n))]
            df_data_dict = {k: self.spread_maker(data_dict, coeff_list, tp)
                            for k, tp in enumerate(trade_type_list)}
            data_aux = pd.concat([d.loc[:, 'bid'] for d in df_data_dict.values()], axis=1)
            data_['bid'] = data_aux.min(axis=1).rename('bid')
            data_aux = pd.concat([d.loc[:, 'ask'] for d in df_data_dict.values()], axis=1)
            data_['ask'] = data_aux.max(axis=1).rename('ask')
            return pd.concat([data_['bid'], data_['ask']], axis=1)
        elif any([x == 'cmb' for x in trade_type]):
            ValueError('Trade type cmb must be for all markets.')
        else:
            pass
        for m, t, c, tt in zip(market_list, tenors_list, coeff_list, trade_type):
            df_data = {k: [] for k in ['bid', 'ask']}
            if tt == 'mid':
                df_data['bid'] = .5 * (data_dict[m][t]['bid'] + data_dict[m][t]['ask'])
                df_data['ask'] = .5 * (data_dict[m][t]['bid'] + data_dict[m][t]['ask'])
            elif tt == 'mm':
                if c > 0:
                    side_a = 'ask'
                    side_b = 'bid'
                else:
                    side_a = 'bid'
                    side_b = 'ask'
                # Bid
                df_data['bid'] = data_dict[m][t][side_b]
                # Ask
                df_data['ask'] = data_dict[m][t][side_a]
            elif tt == 'agg':
                if c > 0:
                    side_a = 'bid'
                    side_b = 'ask'
                else:
                    side_a = 'ask'
                    side_b = 'bid'
                # Bid
                df_data['bid'] = data_dict[m][t][side_b]
                # Ask
                df_data['ask'] = data_dict[m][t][side_a]
            elif tt == 'cmb':
                pass
            else:
                ValueError('Uknown trade type %s.\n' % tt)
            data_['bid'] += c * df_data['bid']
            data_['ask'] += c * df_data['ask']
            del df_data
        data_['bid'] = data_['bid'].rename('bid')
        data_['ask'] = data_['ask'].rename('ask')
        return pd.concat([data_['bid'], data_['ask']], axis=1)

    def time_snapshot(self, df_data, data_class, gran, start_time, end_time):
        ts = None
        start_date = df_data.index.min()
        end_date = df_data.index.max()
        for m in set(self.market_list):
            ts_aux = self.get_time_index(m, data_class, gran, start_date, end_date,
                                         start_time, end_time)
            if ts is None:
                ts = ts_aux
            else:
                ts = ts.union(ts_aux)
        if ts is None:
            return df_data
        else:
            # Drop duplicates
            ts = ts[~ts.duplicated(keep='first')]
            ts_all = df_data.index.union(ts)
            df_data = df_data.reindex(ts_all).ffill().loc[ts, :]
            mid_ser = .5 * (df_data.loc[:, 'bid'] + df_data.loc[:, 'ask'])
            df_data = df_data[mid_ser != mid_ser.shift()]
            return df_data

    def add_trades(self, data_dict, trade_dict, coeff_list, mm_bool=[]):
        market_list = self.market_list
        tenors_list = self.tenors_list
        if not mm_bool:
            mm_bool = [True] * len(market_list)
        # Trade data
        instr_dict = {}
        aux_dict = {}
        for m, t, c, i in zip(market_list, tenors_list, coeff_list, mm_bool):
            if i is False:
                continue
            aux_dict[m + '_' + t + '_bid'] = trade_dict[m][t]['bid']
            aux_dict[m + '_' + t + '_ask'] = trade_dict[m][t]['ask']
            # Index spread based on coeff & product based on agg trade
            if c > 0:
                instr_dict[m + '_' + t + '_bid'] = ['bid', c]
                instr_dict[m + '_' + t + '_ask'] = ['ask', c]
            else:
                instr_dict[m + '_' + t + '_bid'] = ['ask', -c]
                instr_dict[m + '_' + t + '_ask'] = ['bid', -c]
        df_data = pd.DataFrame(aux_dict).dropna(how='all')
        # data_tdict = df_data.to_dict('split')
        timestamp = df_data.index
        # Reindex bid/ask data
        dn_dict = {m: {} for m in market_list} 
        for m, t in zip(market_list, tenors_list):
            dn_dict[m][t] = {k: [] for k in ['bid', 'ask']}
            ts_new = data_dict[m][t]['bid'].index.union(timestamp)
            dn_dict[m][t]['bid'] = data_dict[m][t]['bid'].reindex(ts_new).ffill()
            dn_dict[m][t]['ask'] = data_dict[m][t]['ask'].reindex(ts_new).ffill()
            dn_dict[m][t]['bid'] = dn_dict[m][t]['bid'].reindex(timestamp)
            dn_dict[m][t]['ask'] = dn_dict[m][t]['ask'].reindex(timestamp)
            del ts_new
        # Data spread
        #data_ = {k: pd.Series([0] * len(timestamp), index=timestamp, name=k)
        #         for k in ['bid', 'ask']}
        data_ = {k: pd.DataFrame([], dtype=float) for k in ['bid', 'ask']}
        '''
        for t, v in zip(data_tdict['index'], data_tdict['data']):
            idx_nan = [j for x in v if np.isnan(x)]
            for i in idx_nan:
                instr = data_tdict['index']
        '''
        for instr_name in df_data.columns:
            data_aux = pd.Series([0] * len(timestamp), index=timestamp)
            side = instr_dict[instr_name][0]
            c_mm = instr_dict[instr_name][1]
            if side == 'bid':
                side_o = 'ask'
            else:
                side_o = 'bid'
            for m, t, c in zip(market_list, tenors_list, coeff_list):
                name = m + '_' + t
                if name == instr_name[:-4]:
                    data_aux += c * df_data.loc[:, instr_name]
                else:
                    if c * c_mm > 0:
                        side_agg = side_o
                    else:
                        side_agg = side
                    data_aux += c * dn_dict[m][t][side_agg]
            data_[side] = pd.concat([data_[side], data_aux], axis=1)
        data_['bid'] = data_['bid'].max(axis=1).rename('buy')
        data_['ask'] = data_['ask'].min(axis=1).rename('sell')
        # # spread mid
        # data_ms = pd.Series([0] * len(timestamp), index=timestamp)
        # for m, t, c in zip(market_list, tenors_list, coeff_list):
        #     data_ms += c * (dn_dict[m][t]['bid'] + dn_dict[m][t]['ask']) * .5
        # data_['bid'][data_['bid'] > data_ms] = np.nan
        # data_['ask'][data_['ask'] < data_ms] = np.nan
        return pd.concat([data_['bid'], data_['ask']], axis=1)

    def get_trades_otc(self, data_dict, trade_dict, coeff_list, mm_bool=[]):
        market_list = self.market_list
        tenors_list = self.tenors_list
        if not mm_bool:
            mm_bool = [True] * len(market_list)
        # Trade data
        instr_dict = {}
        aux_dict = {}
        ref_dict = {}
        for m, t, c, i in zip(market_list, tenors_list, coeff_list, mm_bool):
            if i is False:
                continue
            aux_dict[m + '_' + t + '_bid'] = trade_dict[m][t]['bid']
            aux_dict[m + '_' + t + '_ask'] = trade_dict[m][t]['ask']
            ref_dict[m + '_' + t + '_volume'] = trade_dict[m][t]['volume']
            #ref_dict[m + '_' + t + '_broker_id'] = trade_dict[m][t]['broker_id']
            # Index spread based on coeff & product based on agg trade
            if c > 0:
                instr_dict[m + '_' + t + '_bid'] = ['bid', c]
                instr_dict[m + '_' + t + '_ask'] = ['ask', c]
            else:
                instr_dict[m + '_' + t + '_bid'] = ['ask', -c]
                instr_dict[m + '_' + t + '_ask'] = ['bid', -c]
        df_data = pd.DataFrame(aux_dict).dropna(how='all')
        df_ref = pd.DataFrame(ref_dict).dropna(how='all')
        # data_tdict = df_data.to_dict('split')
        timestamp = df_data.index.drop_duplicates()
        # Reindex bid/ask data
        dn_dict = {m: {} for m in market_list} 
        for m, t in zip(market_list, tenors_list):
            dn_dict[m][t] = {k: [] for k in ['bid', 'ask']}
            ts_new = data_dict[m][t]['bid'].index.union(timestamp)
            dn_dict[m][t]['bid'] = data_dict[m][t]['bid'].reindex(ts_new).ffill()
            dn_dict[m][t]['ask'] = data_dict[m][t]['ask'].reindex(ts_new).ffill()
            dn_dict[m][t]['bid'] = dn_dict[m][t]['bid'].reindex(timestamp)
            dn_dict[m][t]['ask'] = dn_dict[m][t]['ask'].reindex(timestamp)
            del ts_new
        # Data spread
        data_ = {k: pd.DataFrame([], dtype=float) for k in ['bid', 'ask']}
        '''
        for t, v in zip(data_tdict['index'], data_tdict['data']):
            idx_nan = [j for x in v if np.isnan(x)]
            for i in idx_nan:
                instr = data_tdict['index']
        '''
        for instr_name in df_data.columns:
            data_aux = pd.Series([0] * len(timestamp), index=timestamp)
            side = instr_dict[instr_name][0]
            c_mm = instr_dict[instr_name][1]
            if side == 'bid':
                side_o = 'ask'
            else:
                side_o = 'bid'
            for m, t, c in zip(market_list, tenors_list, coeff_list):
                name = m + '_' + t
                if name == instr_name[:-4]:
                    data_aux += c * df_data.loc[:, instr_name]
                else:
                    if c * c_mm > 0:
                        side_agg = side_o
                    else:
                        side_agg = side
                    data_aux += c * dn_dict[m][t][side_agg]
            data_[side] = pd.concat([data_[side], data_aux], axis=1)
        data_['bid'] = data_['bid'].max(axis=1).rename('buy')
        data_['ask'] = data_['ask'].min(axis=1).rename('sell')
        data_ = pd.concat([data_['bid'], data_['ask']], axis=1)
        data_['price'] = data_['buy'].combine_first(data_['sell'])
        data_['action'] = data_.apply(source_value, axis=1)
        if len(df_ref.columns) > 1:
            cols = df_ref.columns
            data_['volume'] = df_ref[cols[0]].combine_first(df_ref[cols[1]])
        else:
            data_['volume'] = df_ref.iloc[:, 0]
        # # spread mid
        # data_ms = pd.Series([0] * len(timestamp), index=timestamp)
        # for m, t, c in zip(market_list, tenors_list, coeff_list):
        #     data_ms += c * (dn_dict[m][t]['bid'] + dn_dict[m][t]['ask']) * .5
        # data_['bid'][data_['bid'] > data_ms] = np.nan
        # data_['ask'][data_['ask'] < data_ms] = np.nan
        data_.index = pd.to_datetime(data_.index)
        return data_.iloc[:, 2:]


class SpreadViewerData():
    def __init__(self):
        self.data = {}
        self.__data_type = ''
        self.state = 0

    @property
    def data_type(self):
        return self.__data_type

    @property
    def markets(self):
        return [m + '_' + t for m, v in self.data.items() for t in v.keys()]

    def clear(self):
        self.data = {}
        self.__data_type = ''
        self.state = 0

    def change_user_data(self, user_name):
        for m, data_d in self.data.items():
            for t in data_d.keys():
                self.data[m][t]._user = user_name

    def load_best_order_otc(self, market_list, tenors_list, date_list, data_class,
                            start_time=time.min, end_time=time.max):
        # Load data from best Bid&Ask OTC table
        self.data = {m: {} for m in market_list}
        for k, (m, t) in enumerate(zip(market_list, tenors_list)):
            self.data[m][t] = data_class
        self.__data_type = 'best_order_otc'
        self.state = 1
        return 0

    def load_best_ob_tp(self, market_list, tenors_list, date_list, data_class,
                        start_time=time.min, end_time=time.max):
        # Load data from best Bid&Ask OTC table
        self.data = {m: {} for m in market_list}
        for k, (m, t) in enumerate(zip(market_list, tenors_list)):
            self.data[m][t] = data_class
        self.__data_type = 'best_order_tp'
        self.state = 1
        return 0

    def load_trades_otc(self, market_list, tenors_list, data_class,
                        start_time=time.min, end_time=time.max):
        # Load trades
        self.data = {m: {} for m in market_list}
        for k, (m, t) in enumerate(zip(market_list, tenors_list)):
            self.data[m][t] = data_class
        self.__data_type = 'trades_otc'
        self.state = 1
        return 0

    def load_best_ob(self, market_list, tenors_list, date_list, product_date_list,
                     start_time=time.min, end_time=time.max, freq=None, v_thres=1):
        # Load data from OrderBook
        LoB_dict = {m: {} for m in market_list}
        self.data = LoB_dict
        LoB_new = OrderBookSnaps(verbose=True)
        for k, dt in enumerate(date_list):
            datestr = dt.strftime('%y-%m-%d')
            # Load data
            pd_aux = [p_d[k] for p_d in product_date_list]
            pd_m = pd_aux[0]
            # Load new data
            for i, (m, t, p_d) in enumerate(zip(market_list, tenors_list, pd_aux)):
                # Load data Order book i
                file_path = l_path + t.split('_')[0] + '/'
                file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt.strftime('%y%m%d') + '.p'
                print('%s Loading OrderBook %d...' % (datestr, i))
                time_load = LoB_new.import_data(file_path + file_name)
                print('OrderBook %d created in %d sec' % (i, time_load))
                # Truncate to active trading period
                bT = LoB_new.time_list[0]
                eT = LoB_new.time_list[-1]
                LoB_new.LoB_truncate(thres_vol=v_thres)
                LoB, ts_list = LoB_new.LoB_select(bT, eT, start_time, end_time,
                                                  freq=freq)
                LoB_new.update_data(LoB, ts_list)
                try:
                    LoB_dict[m][t].merge_data(LoB_new)
                except(KeyError):
                    LoB_dict[m][t] = OrderBookSnaps(verbose=True)
                    LoB_dict[m][t].merge_data(LoB_new)
                LoB_new.clear()
        self.__data_type = 'order_book'
        self.state = 1
        return 0


def norm_coeff(coeff_list, market_list):
    coeff_new = []
    for m, c in zip(market_list, coeff_list):
        unit = translate_unit(m)
        if unit == 'MWh':
            # No conversion to MWh
            pass
        elif unit == 'kTh':
            # Convert to MWh
            c *= .341214
        elif unit == 't':
            pass
        else:
            ValueError('Unknown unit %s.' & unit)
        coeff_new.append(c)
    return coeff_new


def translate_unit(market):
    unit_dict = {}
    unit_dict['ttf'] = 'MWh'
    unit_dict['the'] = 'MWh'
    unit_dict['psv'] = 'MWh'
    unit_dict['cegh'] = 'MWh'
    unit_dict['nbp'] = 'kTh'
    unit_dict['zee'] = 'kTh'
    unit_dict['de'] = 'MWh'
    unit_dict['fr'] = 'MWh'
    unit_dict['it'] = 'MWh'
    unit_dict['eua'] = 't'
    return unit_dict[market]


def venue_dict(venue_code):
    v_dict = {}
    v_dict[20] = 'eex'
    v_dict[25] = 'eex'
    v_dict[14] = 'eex'
    v_dict[28] = 'nasdaq'
    v_dict[30] = 'ice'

    try:
        venue = v_dict[venue_code]
    except(KeyError):
        venue = 'otc'
    return venue


def source_value(row):
    if pd.notnull(row['buy']):
        return 1
    elif pd.notnull(row['sell']):
        return -1
    else:
        return np.nan
