# -*- coding: utf-8 -*-
"""
Created on Wed Aug 16 15:59:21 2023

@author: Marek
"""

import abc
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from datetime import time as tm
from time import time
from dateutil.relativedelta import relativedelta
import pytz
import requests
import json
import io
import os

from Common.config_load import get_config_path as CONFIG_PATH
from Database.DB_reader import Database

class TPDataTemplate():
    __metaclass__ = abc.ABCMeta
    def __init__(self):
        self.db_connection = None

    @property
    def status(self):
        if self.db_connection is None:
            status = 0
        else:
            status = 1
        return status

    @property
    def com_dict(self):
        my_dict = {}
        my_dict['de'] = 'pwr'
        my_dict['hu'] = 'pwr'
        my_dict['fr'] = 'pwr'
        my_dict['it'] = 'pwr'
        my_dict['es'] = 'pwr'
        my_dict['de_fr'] = 'pwr'
        my_dict['de_hu'] = 'pwr'
        my_dict['de_at'] = 'pwr'
        my_dict['de_cz'] = 'pwr'
        my_dict['it_de'] = 'pwr'
        my_dict['nl_de'] = 'pwr'
        my_dict['ttf'] = 'gas'
        my_dict['the'] = 'gas'
        my_dict['eua'] = 'eua'
        return my_dict

    @property
    def mkt_dict(self):
        my_dict = {}
        my_dict['de'] = 'Germany'
        my_dict['fr'] = 'France'
        my_dict['hu'] = 'Hungary'
        my_dict['it'] = 'Italy'
        my_dict['es'] = 'Spain'
        my_dict['de_fr'] = 'Germany/France'
        my_dict['de_hu'] = 'Germany/Hungary'
        my_dict['de_at'] = 'Germany/Austria'
        my_dict['de_cz'] = 'Germany/Czech'
        my_dict['it_de'] = 'Italy/Germany'
        my_dict['nl_de'] = 'Holland/Germany'
        my_dict['ttf'] = 'TTF Hi Cal 51.6'
        my_dict['the'] = 'THE'
        my_dict['eua'] = 'EUA'
        return my_dict

    @property
    def prod_dict(self):
        my_dict = {}
        my_dict['base'] = 'Baseload'
        my_dict['peak'] = 'Peaks'
        return my_dict

    @staticmethod
    def venue_check(com, tenor, venue):
        if (com == 'gas') & (venue.upper() == 'EEX'):
            return 'pegas'
        else:
            return venue

    @staticmethod
    def seqid_dict(com):
        my_dict = {}
        if com == 'pwr':
            my_dict['D'] = 10000100
            my_dict['WEND'] = 10000101
            my_dict['W'] = 10000102
            my_dict['M'] = 10000104
            my_dict['Q'] = 10000105
            my_dict['Y'] = 10000106
        elif com == 'gas':
            my_dict['DA'] = 10000302
            my_dict['WEND'] = 10000302
            my_dict['BOM'] = 10000301
            my_dict['M'] = 10000305
            my_dict['Q'] = 10000306
            my_dict['S'] = 10000307
            my_dict['SUM'] = 10000307
            my_dict['WIN'] = 10000307
            my_dict['Y'] = 10000309
        elif com == 'eua':
            my_dict['DEC'] = 10000400
        else:
            raise ValueError('Unknown commodity %s' % com)
        return my_dict

    @property
    def instid_dict(self):
        my_dict = {}
        my_dict['de'] = {'eex': 10641710, 'otc': 10001126}
        my_dict['fr'] = {'eex': 10001075, 'otc': 10001109}
        my_dict['hu'] = {'eex': 10011036, 'otc': 10001137}
        my_dict['it'] = {'eex': 10100480, 'otc': 10001157}
        my_dict['es'] = {'eex': 10012528, 'otc': 10001183}
        my_dict['ttf'] = {'eex': 10002806, 'otc': 10002096}
        my_dict['the'] = {'eex': 10002148}
        my_dict['eua'] = {'eex': 10003008, 'ice': 10003007}
        my_dict['de_fr'] = {'eex': 10641750}
        my_dict['de_hu'] = {'eex': 10642360}
        my_dict['de_at'] = {'eex': 10641886}
        my_dict['de_cz'] = {'eex': 10642316}
        my_dict['it_de'] = {'eex': 10642564}
        my_dict['nl_de'] = {'eex': 10643876}
        return my_dict

    @property
    def base_url_dict(self):

        base_dict={}
        base_dict['ref_data'] = r'https://referencedata.trayport.com'
        base_dict['analytics'] = r'https://analytics.trayport.com/api'
        return base_dict

    @property
    def ref_url_dict(self):

        ref_dict = {}
        ref_dict['instruments'] = '/instruments'
        ref_dict['markets'] = '/markets'
        ref_dict['sequences'] = '/sequences'
        return ref_dict

    @property
    def analytics_url_dict(self):
        anal_dict = {}
        anal_dict['trades'] = '/trades'
        anal_dict['orders'] = '/orders/book'
        anal_dict['best_orders'] = '/orders/book/top'
        return anal_dict

    def url_composer(self, data_type):
        if data_type in self.ref_url_dict.keys():
            url = self.base_url_dict['ref_data'] +\
                self.ref_url_dict[data_type]
        elif data_type in self.analytics_url_dict.keys():
            url = self.base_url_dict['analytics'] +\
                self.analytics_url_dict[data_type]
        else:
            raise Exception('data_type not known')

        return url

    @property
    def broker_id_dict(self):
        my_dict = {}
        my_dict['EEX'] = 1441
        my_dict['GFI'] = 2
        my_dict['TFS'] = 7
        my_dict['42FS'] = 8
        my_dict['ICAP'] = 4
        my_dict['EEX7'] = 1441
        my_dict['SPEC'] = 5
        my_dict['EEXS'] = 1441
        my_dict['GRFN'] = 3
        my_dict['BGC'] = 10
        return my_dict

    @staticmethod
    def calc_itemid(tenor, start_date):
        delta = relativedelta(start_date, datetime(2022,1,1))
        if tenor.upper() in ['DA', 'WEND']:
            idem_id = 2
        elif tenor.upper() == 'D':
            idem_id = int((start_date - datetime(2022,1,1)).days) + 7010
        elif tenor.upper() == 'W':
            idem_id = int((start_date - datetime(2022,1,3)).days / 7) + 1045
        elif tenor.upper() == 'M':
            idem_id = delta.months + 12 * delta.years + 217
        elif tenor.upper() == 'Q':
            idem_id = int((delta.months + 12 * delta.years) / 3) + 73
        elif tenor.upper() == 'Y':
            idem_id = int((delta.months + 12 * delta.years) / 12) + 19
        elif tenor.upper() == 'DEC':
            idem_id = int((delta.months + 12 * delta.years) / 12) * 40 + 670 - 40
        else:
            raise ValueError('Unknown tenor %s' % tenor)
        return idem_id

    def calc_seqid(self, mkt, tenor):
        com = self.com_dict[mkt]
        return str(self.seqid_dict(com)[tenor.upper()])

    def calc_instname(self, mkt, prod, venue):
        inst_name = ''
        inst_name += self.mkt_dict[mkt]
        com = self.com_dict[mkt]
        if com == 'pwr':
            inst_name += ' ' + self.prod_dict[prod]
        elif com in ['gas', 'eua']:
            pass
        else:
            raise ValueError('Unknown commodity %s' % com)
        if venue == 'otc':
            pass
        elif venue == 'eex':
            if inst_name in ['France Baseload']:
                inst_name = 'EEX ' + inst_name + ' Anon'
            elif inst_name in ['Spain Baseload', 'Italy Baseload']:
                inst_name += ' EEX Anon'
            elif inst_name in ['Germany/France Baseload', 'Germany/Hungary Baseload', 'Germany/Austria Baseload']:
                aux_name_list = inst_name.split('/')
                inst_name = aux_name_list[0] + ' Baseload EEX/' + aux_name_list[1] + ' EEX'
            elif inst_name in ['Germany/Czech Baseload']:
                aux_name_list = inst_name.split('/')
                inst_name = aux_name_list[0] + ' Baseload EEX/' + aux_name_list[1] + ' PXE FIN'
            elif inst_name in ['Italy/Germany Baseload', 'Holland/Germany Baseload']:
                aux_name_list = inst_name.split('/')
                inst_name = aux_name_list[0] + ' Baseload EEX Anon/' + aux_name_list[1] + ' EEX'
            else:
                inst_name += ' EEX'
        elif venue == 'pegas':
            if inst_name in ['THE']:
                inst_name = 'NCG PEGAS'
            else:
                inst_name += ' PEGAS'
        elif venue == 'ice':
            inst_name += ' ICE ENDEX'
            if com == 'pwr':
                inst_name += ' Fin'
        return inst_name

    def get_instnames(self, mkt, prod, venue_list):
        return tuple(self.calc_instname(mkt, prod, v) for v in venue_list)

    @abc.abstractmethod
    def get_orders_data(self, market, tenor, venue_list, start_date1, bT, eT,
                        prod, start_date2):
        pass

    @abc.abstractmethod
    def get_best_orders_data(self, market, tenor, start_date1, bT, eT,
                             prod, start_date2):
        pass

    @abc.abstractmethod
    def get_trades(self, market, tenor, venue_list, start_date1, bT, eT,
                   prod, start_date2):
        pass

    @staticmethod
    def filter_data(df_data, price_series, factor, day_bool=True):
        if day_bool:
            idx = np.abs(np.diff(price_series.index.day)) > 0
            # price_series.iloc[1:][idx] = np.nan
            price_series.iloc[np.where(np.insert(idx, 0, False))] = np.nan
        # Filter data
        stop_bool = False
        while not stop_bool:
            # Diff
            dp_series = np.log(price_series).diff()
            dp_series = dp_series.fillna(0)
            # Stats
            aux_series = dp_series.drop([dp_series.idxmin(), dp_series.idxmax()])
            avg = aux_series[aux_series != 0].mean()
            std = aux_series[aux_series != 0].std()
            #idx = [abs(x - avg) <= std * factor for x in dp_series]
            idx = [i for i, x in enumerate(dp_series) if abs(x - avg) > std * factor]
            if not idx:
                stop_bool = True
            else:
                i_list = list(range(idx[0])) + list(range(idx[0]+1, dp_series.size))
                price_series = price_series.iloc[i_list]
                df_data = df_data.iloc[i_list, :]
        return df_data

    @staticmethod
    def process_best_orders(df_data):
        mid_ser = .5 * (df_data.loc[:, 'bidbestprice'] + df_data.loc[:, 'askbestprice'])
        return df_data[mid_ser != mid_ser.shift()]

    @staticmethod
    def process_best_orders_all(df_data):
        # Create a boolean condition that checks if any of the key price columns change
        condition = (
            (df_data['bidbestprice'] != df_data['bidbestprice'].shift()) |
            (df_data['askbestprice'] != df_data['askbestprice'].shift()) |
            (df_data['bidbestprice_aonn'] != df_data['bidbestprice_aonn'].shift()) |
            (df_data['askbestprice_aonn'] != df_data['askbestprice_aonn'].shift())
        )
        return df_data[condition]

    @staticmethod
    def clean_trades(df_trades, df_ba, factor=7, is_verbose=False):
        # Align time of trades with bid ask data
        df_ba = df_ba.groupby(df_ba.index).mean()
        ts_new = df_ba.index.union(df_trades.index)
        ts_new = ts_new[~ts_new.duplicated(keep='first')]
        df_ba_ = df_ba.reindex(ts_new).ffill().reindex(df_trades.index)
        # Make distribution of trades outside of bid ask
        mrg_b = (df_ba_.loc[:, 'b_price'] - df_trades.loc[:, 'price']).clip(lower=0)
        mrg_a = (df_trades.loc[:, 'price'] - df_ba_.loc[:, 'a_price']).clip(lower=0)
        mrg_df = mrg_a - mrg_b
        brk_df = df_trades.loc[:, 'broker_id']
        # Margin outlyers detection
        avg_o = mrg_df.mean()
        std_o = mrg_df.std()
        # idx = [i for i, (x, b) in enumerate(zip(mrg_df, brk_df))
        #        if abs(x - avg_o) > std_o * factor and b != 1441]
        idx = [True if abs(x - avg_o) > std_o * factor and b != 1441 else False
               for x, b in zip(mrg_df, brk_df)]
        if is_verbose:
            print('Deleting following trades \n')
            print(df_trades.iloc[idx, :])
            print('\n')
        return df_trades.loc[~np.array(idx), :]


class TPData(TPDataTemplate):
    def __init__(self):
        self.db_connection = None

    @property
    def order_query(self):
        query = "select datetime, unique_id, action, price, volume, side, " + \
                "status, impliedtype, persistentorderid, companyid, brokerid, allornone " + \
                "from trayport_orders_view ord " + \
                "where ord.instid in " + \
                "(select id_instrument from trayport_instrument where instname in :mkt ) " + \
                "and ord.firstsequenceid = :seqid1 " + \
                "and ord.firstsequenceitemid = :itemid1 " + \
                "and ord.secondsequenceitemid = :itemid2 " + \
                "and ord.datetime >= to_timestamp(:bT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "and ord.datetime  < to_timestamp(:eT, 'dd.mm.yyyy HH24:MI:SS')" + \
                "order by datetime ASC"
        return query

    @property
    def best_order_query_old(self):
        query = "select datetime, bidbestprice, askbestprice " + \
                "from trayport_instordersummary_all tia " + \
                "where tia.instid in " + \
                "(select id_instrument from trayport_instrument where instname in :mkt ) " + \
                "and tia.firstsequenceid = :seqid1 " + \
                "and tia.firstsequenceitemid = :itemid1 " + \
                "and tia.secondsequenceitemid = :itemid2 " + \
                "and tia.datetime >= to_timestamp(:bT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "and tia.datetime  < to_timestamp(:eT, 'dd.mm.yyyy HH24:MI:SS')" + \
                "order by datetime ASC"
        return query

    @property
    def best_order_query(self):
        query = "select datetime, bidbestprice, askbestprice, bidbestprice_aonn, askbestprice_aonn " + \
                "from best_orders.ba_price tia " + \
                "where split_part(tia.instkey, '_', 1) = CAST( " + \
                "(select id_instrument from trayport_instrument where instname = :mkt) AS CHAR(8))" + \
                "and split_part(tia.instkey, '_', 2) = :seqid1 " + \
                "and tia.firstsequenceitemid = :itemid1 " + \
                "and tia.secondsequenceitemid = :itemid2 " + \
                "and tia.datetime >= to_timestamp(:bT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "and tia.datetime  < to_timestamp(:eT, 'dd.mm.yyyy HH24:MI:SS')" + \
                "order by datetime ASC"
        return query

    @property
    def delete_best_order_query(self):
        query = "delete from best_orders.ba_price tia " + \
                "where tia.datetime >= to_timestamp(:bT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "and tia.datetime  < to_timestamp(:eT, 'dd.mm.yyyy HH24:MI:SS')"
        return query

    @property
    def trade_query(self):
        query = "select datetime, tradeid, price, volume, aggressoraction, " + \
                "aggressorbroker_id_ut, initiatorcompany_id_ut, aggressorcompany_id_ut, nanotime " + \
                "from ROVE_OD.TRAYPORT_VW_TRADES tvt " + \
                "where tvt.instname in ({placeholders})  " + \
                "and tvt.firstsequenceid = :seqid1 " + \
                "and tvt.firstsequenceitemid = :itemid1 " + \
                "and tvt.secondsequenceitemid = :itemid2 " + \
                "and tvt.datetime >= to_timestamp(:bT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "and tvt.datetime  < to_timestamp(:eT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "order by tvt.datetime ASC"
        return query
    
    #TSDB trade query
    @property
    def tsdb_trade_query(self):
        query = "select datetime, tradeid, price, volume, aggressoraction, " + \
                "aggressorbroker_id_ut, initiatorcompany_id_ut, aggressorcompany_id_ut, nanotime " + \
                "from public.trades tvt " + \
                "where tvt.instname in ({placeholders})  " + \
                "and tvt.firstsequenceid = :seqid1 " + \
                "and tvt.secondsequenceitemid = :itemid2 " + \
                "and tvt.firstsequenceitemid = :itemid1 " + \
                "and tvt.datetime >= to_timestamp(:bT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "and tvt.datetime  < to_timestamp(:eT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "order by tvt.datetime ASC"
        return query

    @property
    def trade_inst_query(self):
        query = "select datetime, tradeid, price, volume, aggressoraction, " + \
                "aggressorbroker_id_ut, initiatorcompany_id_ut, aggressorcompany_id_ut, " + \
                "firstsequenceid, firstsequenceitemid, secondsequenceitemid, nanotime " + \
                "from ROVE_OD.TRAYPORT_VW_TRADES tvt " + \
                "where tvt.instname in ({placeholders})  " + \
                "and tvt.datetime >= to_timestamp(:bT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "and tvt.datetime  < to_timestamp(:eT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "order by tvt.datetime ASC"
        return query

    @property
    def trade_inst_curt_query(self):
        query = "select datetime, price, volume, aggressoraction, " + \
                "aggressorbroker_id_ut, initiatorcompany_id_ut, aggressorcompany_id_ut, " + \
                "firstsequenceid, firstsequenceitemid, nanotime " + \
                "from ROVE_OD.TRAYPORT_VW_TRADES tvt " + \
                "where tvt.instname in ({placeholders})  " + \
                "and tvt.secondsequenceitemid = :itemid2 " + \
                "and tvt.datetime >= to_timestamp(:bT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "and tvt.datetime  < to_timestamp(:eT, 'dd.mm.yyyy HH24:MI:SS') " + \
                "order by tvt.datetime ASC"
        return query

    @staticmethod
    def prepare_data(data_raw, columns):
        data_dict = {k: [x[i] for x in data_raw] for i, k in enumerate(columns)}
        df_data = pd.DataFrame(data_dict)
        df_data.set_index('datetime', inplace=True)
        return df_data

    def create_connection(self, database, path_name=None):
        if path_name is None:
            self.db_connection = Database(database)
        else:
            self.db_connection = Database(database, path_name)

    def __calc_instname_spread(self, mkt_list, prod, venue):
        pass

    def orders_params(self, market, tenor, venue_list, prod,
                      start_date1, start_date2, bT, eT):
        params = {}
        params['mkt'] = self.get_instnames(market, prod, venue_list)
        params['seqid1'] = self.calc_seqid(market, tenor)
        params['itemid1'] = str(self.calc_itemid(tenor, start_date1))
        if start_date2 is None:
            params['itemid2'] = str(0)
        else:
            params['itemid2'] = str(self.calc_itemid(tenor, start_date2))
        params['bT'] = bT.strftime('%d.%m.%Y %H:%M:%S')
        params['eT'] = eT.strftime('%d.%m.%Y %H:%M:%S')
        return params

    def trades_params(self, market, tenor, venue_list, prod,
                      start_date1, start_date2, bT, eT):
        venue_list = [self.venue_check(self.com_dict[market], tenor, v) for v in venue_list]
        inst_names = self.get_instnames(market, prod, venue_list)
        params = {**{f"mkt_{i}": val for i, val in enumerate(inst_names)}}
        params['seqid1'] = self.calc_seqid(market, tenor)
        params['itemid1'] = str(self.calc_itemid(tenor, start_date1))
        if start_date2 is None:
            params['itemid2'] = str(0)
        else:
            params['itemid2'] = str(self.calc_itemid(tenor, start_date2))
        params['bT'] = bT.strftime('%d.%m.%Y %H:%M:%S')
        params['eT'] = eT.strftime('%d.%m.%Y %H:%M:%S')
        return params

    def trades_inst_params(self, market, venue_list, prod, spread_bool, bT, eT):
        venue_list = [self.venue_check(self.com_dict[market], None, v) for v in venue_list]
        inst_names = self.get_instnames(market, prod, venue_list)
        params = {**{f"mkt_{i}": val for i, val in enumerate(inst_names)}}
        if not spread_bool:
            params['itemid2'] = str(0)
        params['bT'] = bT.strftime('%d.%m.%Y %H:%M:%S')
        params['eT'] = eT.strftime('%d.%m.%Y %H:%M:%S')
        return params

    def get_orders_data(self, market, tenor, venue_list, start_date1, bT, eT,
                        prod='base', start_date2=None):
        params = self.orders_params(market, tenor, venue_list, prod,
                                    start_date1, start_date2, bT, eT)
        df_data = self.db_connection.execute(self.order_query, params)
        #df_data['price'] = (df_data['price'] * 10000).astype(int)
        #df_data = df_data.set_index('datetime')
        # df_data['allornone'] = df_data['allornone'].astype(bool)
        return df_data

    @staticmethod
    def mid_price_bo(df_data):
        return .5 * (df_data.loc[:, 'bidbestprice'] + df_data.loc[:, 'askbestprice'])

    def get_best_ob_data(self, market, tenor, venue_list, start_date1, bT, eT,
                         prod='base', start_date2=None, aonn=True):
        venue_list = ['eex']
        params = self.orders_params(market, tenor, venue_list, prod,
                                    start_date1, start_date2, bT, eT)
        df_data = self.db_connection.execute(self.best_order_query, params)
        df_data = df_data.set_index('datetime')
        if aonn:
            df_data = df_data.loc[:, ['bidbestprice', 'askbestprice']]
        else:
            df_data = df_data.loc[:, ['bidbestprice_aonn', 'askbestprice_aonn']]
            df_data.columns = ['bidbestprice', 'askbestprice']
        df_data = df_data.astype(float)
        return self.process_best_orders(df_data)

    def delete_best_ob_data(self, date):
        bT = datetime.combine(date, tm(0, 0, 0, 0))
        eT = datetime.combine(date, tm(23, 59, 59, 0))
        params = {}
        params['bT'] = bT.strftime('%d.%m.%Y %H:%M:%S')
        params['eT'] = eT.strftime('%d.%m.%Y %H:%M:%S')
        b = self.db_connection.execute_delete(self.delete_best_order_query, params)
        if b:
            print('Delete of day %s was SUCCESSFUL' % date.strftime('%d.%m.%Y'))
        else:
            print('Delete of day %s was FAILED' % date.strftime('%d.%m.%Y'))
        return b

    @staticmethod
    def process_trades(df_data):
        try:
            pd.set_option('future.no_silent_downcasting', True)
        except ValueError as e:
            print("Warning: 'future.no_silent_downcasting' option is not supported or available. ", e)
        cols_list = ['tradeid', 'price', 'volume', 'aggressoraction', 'aggressorbroker_id_ut', 'own_trades']
        dup_list = ['datetime', 'tradeid', 'price', 'aggressorbroker_id_ut', 'nanotime']
        df_data['price'] = df_data['price'].astype(float)
        # If venue is nan replace with 0
        df_data['aggressorbroker_id_ut'] = df_data['aggressorbroker_id_ut'].fillna(0)
        df_data['aggressorcompany_id_ut'] = df_data['aggressorcompany_id_ut'].fillna(0)
        df_data['aggressorbroker_id_ut'] = df_data['aggressorbroker_id_ut'].apply(broker_id_convertor)
        # Buy Sell attribute
        action_dict = {'Buy': 1, 'Sell': -1}
        df_data['aggressoraction'] = df_data['aggressoraction'].replace(action_dict)
        # Our trade
        own_ser = ((df_data['initiatorcompany_id_ut'] == 1) |
                   (df_data['aggressorcompany_id_ut'] == 1))
        idx = own_ser & (df_data['aggressorbroker_id_ut'] == 14)
        tag_ser = df_data.reset_index().loc[:, dup_list].duplicated(keep=False)
        tag_ser.index = df_data.index
        tag_ser[own_ser] = True
        tag_ser.name = 'own_trades'
        df_data.loc[df_data['aggressorbroker_id_ut'] == 14, 'aggressorbroker_id_ut'] = 1441
        df_data = pd.concat([df_data, tag_ser], axis=1)
        df_out = df_data.loc[~idx, cols_list]
        df_out.columns = ['tradeid', 'price', 'volume', 'action', 'broker_id', 'own_trades']
        # Incorporate nanoseconds
        df_data['nanotime'] = df_data['nanotime'].fillna(0)
        df_out.index = df_out.index + pd.to_timedelta(df_data.loc[~idx, 'nanotime'].astype(float), unit='ns')
        # Delete trades added by brokers afterwards
        df_out = df_out[(df_out.index.microsecond != 0) | (df_out['broker_id'] == 1441)]
        # Change types for columns
        type_dict = {'tradeid': 'str', 'price': 'float64', 'volume': 'int64', 'action': 'int64',
                     'broker_id': 'int64', 'own_trades': 'bool'}
        return df_out.astype(type_dict).sort_index()

    def get_trades(self, market, tenor, venue_list, start_date1, bT, eT,
                   prod='base', start_date2=None):
        placeholders = ",".join([f":mkt_{i}" for i in range(len(venue_list))])
        query = self.trade_query.replace("{placeholders}", placeholders)
        params = self.trades_params(market, tenor, venue_list, prod,
                                    start_date1, start_date2, bT, eT)
        df_data = self.db_connection.execute(query, params)
        df_data = df_data.set_index('datetime')
        return self.process_trades(df_data)
    
    # TODO: tsdb adjustment
    def get_trades_tsdb(self, market, tenor, venue_list, start_date1, bT, eT,
                prod='base', start_date2=None):
        placeholders = ",".join([f":mkt_{i}" for i in range(len(venue_list))])
        query = self.tsdb_trade_query.replace("{placeholders}", placeholders)
        params = self.trades_params(market, tenor, venue_list, prod,
                                    start_date1, start_date2, bT, eT)
        df_data = self.db_connection.execute(query, params)
        df_data = df_data.set_index('datetime')
        return self.process_trades(df_data)

    @staticmethod
    def process_trades_inst(df_data):
        try:
            pd.set_option('future.no_silent_downcasting', True)
        except pd.errors.OptionError:
            print("Warning: 'future.no_silent_downcasting' is not a valid pandas option in this version. The option has been ignored.")
        cols_list = ['price', 'volume', 'aggressoraction', 'aggressorbroker_id_ut',
                     'firstsequenceid', 'own_trades']
        dup_list = ['datetime', 'price', 'aggressorbroker_id_ut', 'nanotime']
        df_data['price'] = df_data['price'].astype(float)
        # If venue is nan replace with 0
        df_data['aggressorbroker_id_ut'] = df_data['aggressorbroker_id_ut'].fillna(0)
        df_data['aggressorcompany_id_ut'] = df_data['aggressorcompany_id_ut'].fillna(0)
        # Buy Sell attribute
        action_dict = {'Buy': 1, 'Sell': -1}
        df_data['aggressoraction'] = df_data['aggressoraction'].replace(action_dict)
        # Our trade
        own_ser = ((df_data['initiatorcompany_id_ut'] == 1) |
                   (df_data['aggressorcompany_id_ut'] == 1))
        idx = own_ser & (df_data['aggressorbroker_id_ut'] == 14)
        tag_ser = df_data.reset_index().loc[:, dup_list].duplicated(keep=False)
        tag_ser.index = df_data.index
        tag_ser[own_ser] = True
        tag_ser.name = 'own_trades'
        df_data.loc[df_data['aggressorbroker_id_ut'] == 14, 'aggressorbroker_id_ut'] = 1441
        df_data = pd.concat([df_data, tag_ser], axis=1)
        df_out = df_data.loc[~idx, cols_list]
        df_out.columns = ['price', 'volume', 'action', 'broker_id', 'sequid', 'own_trades']
        # Incorporate nanoseconds
        df_data['nanotime'] = df_data['nanotime'].fillna(0)
        df_out.index = df_out.index + pd.to_timedelta(df_data.loc[~idx, 'nanotime'], unit='ns')
        # Delete trades added by brokers afterwards
        df_out = df_out[(df_out.index.microsecond != 0) | (df_out['broker_id'] == 1441)]
        # Change types for columns
        type_dict = {'price': 'float64', 'volume': 'int64', 'action': 'int64',
                     'broker_id': 'int64', 'sequid': 'int64', 'own_trades': 'bool'}
        return df_out.astype(type_dict).sort_index()

    def get_trades_inst(self, market, venue_list, bT, eT, prod='base',
                        spread_bool=False):
        placeholders = ",".join([f":mkt_{i}" for i in range(len(venue_list))])
        if spread_bool:
            query = self.trade_inst_query.replace("{placeholders}", placeholders)
        else:
            query = self.trade_inst_curt_query.replace("{placeholders}", placeholders)
        params = self.trades_inst_params(market, venue_list, prod, spread_bool,
                                         bT, eT)
        df_data = self.db_connection.execute(query, params)
        df_data = df_data.set_index('datetime')
        return self.process_trades_inst(df_data)
    
    def get_trades_inst(self, market, venue_list, bT, eT, prod='base',
                        spread_bool=False):
        placeholders = ",".join([f":mkt_{i}" for i in range(len(venue_list))])
        if spread_bool:
            query = self.trade_inst_query.replace("{placeholders}", placeholders)
        else:
            query = self.trade_inst_curt_query.replace("{placeholders}", placeholders)
        params = self.trades_inst_params(market, venue_list, prod, spread_bool,
                                         bT, eT)
        df_data = self.db_connection.execute(query, params)
        df_data = df_data.set_index('datetime')
        return self.process_trades_inst(df_data)


class TPDataDa(TPDataTemplate):



    def __init__(self, user='martin', tz='CET'):
        self.db_connection = None
        self._user = user
        self._api_key = None
        self.tz = tz

    @property
    def user(self):
        return self._user

    def set_api_key(self):
        PATH = CONFIG_PATH()
        with open(PATH, 'r') as file:
            config = json.load(file)['DataAnalytics']

        self._api_key = config[self.user]

    @property
    def api_key(self):
        self.set_api_key()
        return self._api_key

    def get_market_name(self, mkt, prod):
        com = self.com_dict[mkt]
        if com == 'pwr':
            return self.mkt_dict[mkt] + ' ' + self.prod_dict[prod]
        elif com in ['gas', 'eua']:
            return self.mkt_dict[mkt]
        else:
            raise ValueError('Unknown commodity %s' % com)

    def get_marketId(self, mkt, prod):
        all_markets = self.get_df(self.url_composer('markets'))
        market_dict = all_markets[all_markets['name']==
                                  self.get_market_name(mkt, prod)].to_dict('records')[0]
        return market_dict['id']

    def get_instId(self, mkt, prod):
        all_insts = self.get_df(self.url_composer('instruments'))
        try:
            inst_dict = all_insts[all_insts['name'] ==
                                   self.get_market_name(mkt, prod) + ' EEX'].\
                to_dict('records')[0]
        except(IndexError):
            inst_dict = all_insts[all_insts['name'] ==
                                  'EEX ' + self.get_market_name(mkt, prod) + ' Anon'].\
                to_dict('records')[0]
        return inst_dict['id']

    def create_connection(self, database):
        pass

    @property
    def headers(self):
        return {'x-api-key': self.api_key}

    def get_df(self, url, params={}):
        def get(url, params, headers):
          start_time = time()
          r = requests.get(url, params, headers=headers)
          duration = time() - start_time
          print(r.request.url)
          print(f'Duration: {duration:.3f}s')
          if r.status_code != 200:
            if r.status_code == 429:
                last_user = self._user
                users = ['martin', 'marek', 'matej', 'andrej']
                self._user = [x for x in users if self._user != x][0]
                print('Changing user from', last_user, ' to', self._user)
                return get(url, params, self.headers)
            raise Exception(f'Status: {r.status_code}. {r.content.decode()}')
          return r.content

        content = get(url, params, self.headers)
        df = pd.read_json(io.BytesIO(content), convert_dates=['timestamp','fromTimestamp', 'toTimestamp'])
        if len(df) > 0:
          if 'timestamp' in df.columns:
            df.set_index('timestamp', inplace=True)
        return df

    def get_params(self, market, tenor, venue_list,
                   start_date1, bT, eT,
                   prod='base', start_date2=None, brokers=False):

        params = {}
        params['from'] = bT.strftime('%Y-%m-%dT%H:%M:%SZ')
        params['until'] = eT.strftime('%Y-%m-%dT%H:%M:%SZ')
        if venue_list[0] is None:
            params['marketId'] = self.get_marketId(market, prod)
        elif venue_list[0].upper() in ['EEX']:
            params['instrumentId'] = self.get_instId(market, prod)
        else:
            params['marketId'] = self.get_marketId(market, prod)

        params['sequenceId'] = self.calc_seqid(market, tenor)
        sequenceId_list = [str(self.calc_itemid(tenor, a)) for a in
                                    [start_date1, start_date2] if a is not None]
        params['sequenceItemId'] = sequenceId_list[0]
        params['ContractType'] = 'SinglePeriod'
        if len(sequenceId_list)==2:
            params['secondSequenceItemId'] = sequenceId_list[1]
            params['ContractType'] = 'Spread'
        if brokers:
            params['optionalFields'] = ['VenueCode']
        return params

    def process_trades(self, df):
        try:
            pd.set_option('future.no_silent_downcasting', True)
        except ValueError as e:
            print("Warning: 'future.no_silent_downcasting' option is not supported or available. ", e)
        tz = self.tz
        ts_utc = pd.to_datetime((df['dealDate']/1e9).to_list(), unit='s',
                                utc=True)
        timestamp = pd.DatetimeIndex(ts_utc.tz_convert(tz)).tz_localize(None)

        df['datetime'] = timestamp
        df.set_index(['datetime'],inplace=True)
        action_dict = {True: 1, False: -1}
        df['aggressorBuy'] = df['aggressorBuy'].replace(action_dict)
        df['venueCode'] = df['venueCode'].replace(self.broker_id_dict)
        df = df.rename(columns={
                                'tradeId': 'tradeid',
                                'venueCode': 'broker_id',
                                'quantity': 'volume',
                                'aggressorBuy': 'action'})
        df = df[['tradeid','price', 'volume', 'action', 'broker_id']].copy()
        df = df[(df.index.microsecond != 0) | (df['broker_id'] == 1441)]
        # Change types for columns
        type_dict = {'tradeid': 'str','price': 'float64', 'volume': 'int64', 'action': 'int64',
                     'broker_id': 'int64'}
        return df.astype(type_dict).sort_index()

    def get_trades(self, market, tenor, venue_list,
                   start_date1, bT, eT,
                   prod='base', start_date2=None):
        url = self.url_composer('trades')
        result_df = pd.DataFrame()
        tz_l = pytz.timezone(self.tz)
        bT = tz_l.localize(bT).astimezone(pytz.utc).replace(tzinfo=None)
        eT = tz_l.localize(eT).astimezone(pytz.utc).replace(tzinfo=None)
        bT_i = bT
        eT_i = eT
        delta: timedelta = eT - bT
        while delta > timedelta(days=32):
            eT_i = min(bT_i + timedelta(days=32), eT)
            params = self.get_params(market=market, tenor=tenor,
                                     venue_list=venue_list,
                                       start_date1=start_date1,
                                       bT=bT_i, eT=eT_i,
                                       start_date2=start_date2,
                                       prod='base')
            if result_df.empty:
                result_df = self.get_df(url,params)
            else:
                result_df = pd.concat([result_df, self.get_df(url, params)])
            bT_i += timedelta(days=32)
            delta = eT - bT_i
            

        # Fetch remaining days
        params = self.get_params(market=market, tenor=tenor,
                                 venue_list=venue_list,
                                   start_date1=start_date1,
                                   bT=bT_i, eT=eT,
                                   start_date2=start_date2,
                                   prod='base')
        df = self.get_df(url,params)

        if result_df.empty:
            result_df = df
        else:
            result_df = pd.concat([result_df, df])

        if df.shape == (0, 0):
            print('empty df', bT, eT)
            raise Exception('No Trades for criteria')
        else:
            return self.process_trades(result_df)

    def process_raw_best_orders(self, df):
        tz = self.tz
        df = df[['bidPrice', 'askPrice']].copy()
        df = df.rename(columns={'bidPrice': 'bidbestprice',
                                'askPrice': 'askbestprice'})
        ts = df.index.tz_localize('UTC').tz_convert(tz).tz_localize(None)
        df.index = ts
        return self.process_best_orders(df)

    def get_best_orders_data(self, market, tenor,
                             start_date1, bT, eT,
                             prod='base', start_date2=None):
        df_out = pd.DataFrame([])
        tz_l = pytz.timezone(self.tz)
        dates = pd.date_range(bT, eT, freq='B')
        s_t = bT.time()
        e_t = eT.time()
        for d in dates:
            bT_ = datetime.combine(d, s_t)
            eT_ = datetime.combine(d, e_t)
            bT_ = tz_l.localize(bT_).astimezone(pytz.utc).replace(tzinfo=None)
            eT_ = tz_l.localize(eT_).astimezone(pytz.utc).replace(tzinfo=None)
            params = self.get_params(market=market,tenor=tenor,
                                     venue_list=[None],
                           start_date1=start_date1, bT=bT_, eT=eT_,
                           prod='base', start_date2=start_date2)

            params['interval'] = str(1)
            params['intervalUnit'] = 'second'

            url = self.url_composer('best_orders')
            df = self.get_df(url,params)
            if df.empty:
                print("prazdny df", d)
                # raise Exception('No Trades for criteria')
                df = pd.DataFrame(columns=['bidbestprice', 'askbestprice'])
                df_out = pd.concat([df_out, df])
            else:
                df_out = pd.concat([df_out, self.process_raw_best_orders(df)])
        return df_out

    def process_order_book(self, df):
        tz = self.tz
        
        ts = df.index.tz_localize('UTC').tz_convert(tz).tz_localize(None)
        df.index = ts
        return df

    def proces_best_ob(self, df):
        ts = df.index
        bid_list = [np.nan if not x else x[0]['price'] for x in df['bids'].values]
        ask_list = [np.nan if not x else x[0]['price'] for x in df['asks'].values]
        data_dict = {'bidbestprice': bid_list, 'askbestprice': ask_list}
        return self.process_best_orders(pd.DataFrame(data_dict, index=ts))

    def get_orders_data(self, market, tenor, venue_list, start_date1, bT, eT,
                        prod, start_date2):
        df_out = pd.DataFrame([])
        tz_l = pytz.timezone(self.tz)
        dates = pd.date_range(bT, eT, freq='B')
        s_t = bT.time()
        e_t = eT.time()
        for d in dates:
            bT_ = datetime.combine(d, s_t)
            eT_ = datetime.combine(d, e_t)
            bT_ = tz_l.localize(bT_).astimezone(pytz.utc).replace(tzinfo=None)
            eT_ = tz_l.localize(eT_).astimezone(pytz.utc).replace(tzinfo=None)
            params = self.get_params(market=market,tenor=tenor,
                                     venue_list=venue_list,
                           start_date1=start_date1, bT=bT_, eT=eT_,
                           prod='base', start_date2=start_date2, brokers=True)

            params['interval'] = str(1)
            params['intervalUnit'] = 'second'

            url = self.url_composer('orders')
            df = self.get_df(url,params)
            if df.empty:
                continue
            df_out = pd.concat([df_out, self.process_order_book(df)])
        return df_out

    def get_best_ob_data(self, market, tenor, venue_list, start_date1, bT, eT,
                         prod, start_date2):
        df = self.get_orders_data(market, tenor, venue_list, start_date1,
                                  bT, eT, prod, start_date2)
        return self.proces_best_ob(df)


def broker_id_convertor(broker_id):
    my_dict = {}
    my_dict[134] = 3        # Griffin
    my_dict[144] = 1441     # EEXS
    my_dict[7] = 5          # SPEC
    my_dict[5] = 2          # GFI
    my_dict[6] = 6          # ICAP
    my_dict[3] = 8          # 42FS
    my_dict[14] = 1441      # EEX7
    my_dict[9] = 10         # BGC
    my_dict[4] = 7          # TFS
    try:
        return my_dict[broker_id]
    except(KeyError):
        return 0


class TPDataAssembly(TPDataTemplate):
    
    def __init__(self, source='trayport', user='matej'):
        self._source = source
        
            
    @property
    def inst_data(self):
        if hasattr(self, '_inst_data'):
            return self._inst_data
        else:
            self.set_data_source()
            return self._inst_data
    @property
    def source(self):
        return self._source
    
    def set_data_source(self, source):
        self._source = source
        if source == 'trayport':            
            print('Data source set to Trayport DataAnalytics')
        elif source == 'database':            
            print('Data source set to internal DB')
    
    def set_source_inst(self):
        if self.source == 'trayport':
            self._inst_data = TPDataDa(user='matej')            
        elif self.source == 'database':
            self._inst_data = TPData()
            
    
    def set_parameters(self, params_dict):
        self._mkt_list = params_dict['mkt_list']
        self._tenor_list = params_dict['tenor_list']
        self._tn1_list = params_dict['tn1_list']
        self._tn2_list = params_dict['tn2_list']
        self._prod = params_dict['prod']
        self._venue_list = params_dict['venue_list']
        self._start_date = params_dict['start_date']
        self._end_date = params_dict['end_date']
        self._ns = params_dict['ns']
        self._status_check = True
        
    @property
    def mkt_list(self):
        return self._mkt_list
    @property
    def tenor_list(self):
        return self._tenor_list
    @property
    def tn1_list(self):
        return self._tn1_list
    @property
    def tn2_list(self):
        return self._tn2_list
    @property
    def prod(self):
        return self._prod
    @property
    def venue_list(self):
        return self._venue_list
    @property
    def start_date(self):
        return self._start_date
    @property
    def end_date(self):
        return self._end_date
    @property
    def n_s(self):
        return self._ns
    @property
    def status_check(self):
        if hasattr(self,'_status_check'):            
            return self._status_check
        else:
            return False
    @property
    def dates(self):
        return pd.date_range(self.start_date, self.end_date, freq='B')
    
    @property
    def product_date1(self):
        return [self.dates.shift(1, freq='B') if t == 'da' else
                self.dates.shift(1, freq='D') if t == 'd' else
                self.dates.shift(tn, freq='W-MON') if t == 'w' else
                (self.dates + self.n_s * self.dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                (self.dates + self.n_s * self.dates.freq).shift(tn, freq='YS') if t in ['dec'] else
                (self.dates + self.n_s * self.dates.freq).shift(tn, freq=t.upper() + 'S')
                for t, tn in zip(self.tenor_list,
                                 self.tn1_list)]
    @property
    def product_date2(self):
        if not self.tn2_list:
            return [None] * len(self.product_date1)
        else:
            return [self.dates.shift(1, freq='B') if t == 'da' else
                    self.dates.shift(1, freq='D') if t == 'd' else
                    self.dates.shift(tn, freq='W-MON') if t == 'w' else
                    (self.dates + self.n_s * self.dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                    (self.dates + self.n_s * self.dates.freq).shift(tn, freq='YS') if t in ['dec'] else
                    (self.dates + self.n_s * self.dates.freq).shift(tn, freq=t.upper() + 'S')
                    for t, tn in zip(self.tenor_list,
                                     self.tn2_list)]
        
    @property
    def tn_list(self):
        if not self.tn2_list:
            return [str(t1) for t1 in self.tn1_list]
        else:
            return [str(t1) + '_' + str(t2) for (t1, t2) in zip(self.tn1_list,
                                                                self.tn2_list)]
    def set_start_end_time(self,start=[8,0,0],
                           end=[20,0,0]):
        self._start_time = tm(start[0], start[1], start[2])
        self._end_time = tm(end[0], end[1], end[2])
        
    @property
    def start_time(self):
        if hasattr(self, '_start_time'):
            return self._start_time
        else:
            self.set_start_end_time()
            return self._start_time
    @property
    def end_time(self):
        if hasattr(self, '_end_time'):
            return self._end_time
        else:
            self.set_start_end_time()
            return self._end_time
        
    def get_orders_data(self, market, tenor, venue_list, start_date1, bT, eT,
                        prod, start_date2):
        pass    
    def get_best_orders_data(self, market, tenor, start_date1, bT, eT,
                             prod, start_date2):
        pass    
    def get_trades(self, market, tenor, venue_list, start_date1, bT, eT,
                   prod, start_date2):
        pass
        
        
    def get_data(self, params_dict, target_data):
        # Set params from dict
        if self.status_check:
            pass
        else:
            self.set_parameters(params_dict)
            
        data_dict = {m + t + n: [] for m, t, n in zip(self.mkt_list,
                                                      self.tenor_list,
                                                      self.tn_list)}
            
        for m, t, n, p1_d, p2_d in zip(self.mkt_list, self.tenor_list,
                                       self.tn_list, self.product_date1,
                                       self.product_date2):
            
            data_df = pd.DataFrame([])
            if p2_d is None:
                df_prod_dates = pd.DataFrame([p1_d], columns=self.dates).T
            else:
                df_prod_dates = pd.DataFrame([p1_d, p2_d], columns=self.dates).T
            for p_d, ds in df_prod_dates.groupby(0).groups.items():
                bT = datetime.combine(ds[0], self.start_time)
                eT = datetime.combine(ds[-1], self.end_time)
                if p2_d is None:
                    pd_2 = None
                else:
                    pd_2 = df_prod_dates.loc[ds[0], 1]
                # Crete instance
                self.set_source_inst()
                data_class = self.inst_data
                
                if target_data in ['trades']:
                    if self.source in ['database']:
                        data_class.create_connection('OracleSQL')
                    try:
                        df_aux = data_class.get_trades(m, t, self.venue_list,
                                                       p_d, bT, eT, self.prod,
                                                                    pd_2)
                        df_aux = df_aux.between_time(self.start_time, self.end_time)
                    except Exception as e:
                        if str(e) == 'No Trades for criteria':
                            df_aux = pd.DataFrame(columns=['price', 'volume', 'action', 'broker_id'])
                        else:
                            print("Problem in code: ", e)
                    
                    #df_ba_aux = data_class.filter_data(df_ba_aux, df_ba_aux['bidbestprice'], 20)
                    data_df = pd.concat([data_df, df_aux])
                elif target_data in ['best_orders']:
                    if self.source in ['database']:
                        data_class.create_connection('PostgreSQL')
                    df_aux = data_class.get_best_ob_data(m, t, self.venue_list, p_d, bT, eT, self.prod,
                                                                pd_2)
                    df_aux = df_aux.between_time(self.start_time, self.end_time)
                    
                    #df_ba_aux = data_class.filter_data(df_ba_aux, df_ba_aux['bidbestprice'], 20)
                    data_df = pd.concat([data_df, df_aux])
                elif target_data in ['orders']:
                    if self.source in ['database']:
                        data_class.create_connection('PostgreSQL')
                    df_aux = data_class.get_orders_data(m, t, self.venue_list, p_d, bT, eT, self.prod,
                                                      pd_2)
                    if self.source in ['database']:
                        df_aux = df_aux.set_index('datetime')
                    df_aux = df_aux.between_time(self.start_time, self.end_time)
                    # df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
                    data_df = pd.concat([data_df, df_aux])
                    
            data_dict[m + t + str(n)] = data_df
        return data_dict


if __name__=='__main__':

    # assembler = TPDataAssembly(source='database')
    # params_dict = {}
    # params_dict['mkt_list'] = ['de']
    # params_dict['tenor_list'] = ['m']
    # params_dict['tn1_list'] = [1]
    # params_dict['tn2_list'] = []
    # params_dict['prod'] = 'base'
    # params_dict['venue_list'] = ['eex']
    # params_dict['start_date'] = datetime(2023, 12, 13)
    # params_dict['end_date'] = datetime(2023, 12, 13)
    # params_dict['ns'] = 2
    

    # assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])
    # test_df = assembler.get_data(params_dict, target_data='trades')

    
    mkt_list = ['de']
    tenor_list = ['m']
    tn1_list = [1]
    tn2_list = []
    prod = 'base'
    venue_list = ['eex']
    start_date = datetime(2025, 6, 9)
    end_date = datetime(2025, 6, 30)
    n_s = 2
    start_date1 = datetime(2025,7,1)
    # start_date2 = datetime(2024,10,7)
    start_date2 = None
    
    data_class = TPData()
    # data_class.create_connection('OracleSQL')


    # test_df = data_class.get_trades(mkt_list[0], tenor_list[0],venue_list,
    #                                 start_date1,
    #                                 start_date, end_date,
    #                                 'base', start_date2)
    # test_in = data_class.get_trades_inst(mkt_list[0], venue_list, start_date, end_date,
    #                                       prod='base', spread_bool=False)
    data_class.create_connection('PostgreSQL')
    test_ba = data_class.get_best_ob_data(mkt_list[0], tenor_list[0],venue_list,
                                    start_date1,
                                    start_date, end_date,
                                    'base', start_date2=None, aonn=True)
    # test_ob = data_class.get_orders_data(mkt_list[0], tenor_list[0],venue_list,
    #                                 start_date1,
    #                                 start_date, end_date,
    #                                 'base', start_date2)
    # test_ba1 = data_class.get_best_ob_data(mkt_list[0], tenor_list[0],venue_list,
    #                                 start_date1,
    #                                 start_date, end_date,
    #                                 'base', start_date2)
    # params = data_class.get_params(mkt_list[0], tenor_list[0],
    #                                 venue_list[0], start_date1,
    #                                 start_date, end_date,
    #                                 'base', start_date2)











