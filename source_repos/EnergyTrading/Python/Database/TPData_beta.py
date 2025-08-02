# -*- coding: utf-8 -*-
"""
Created on Wed Aug 16 15:59:21 2023

@author: Marek
"""

import abc
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from time import time
from dateutil.relativedelta import relativedelta
from Database.DB_reader import Database
import requests
import json
import io


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
        my_dict['ttf'] = 'gas'
        my_dict['eua'] = 'eua'
        return my_dict

    @property
    def mkt_dict(self):
        my_dict = {}
        my_dict['de'] = 'Germany'
        my_dict['fr'] = 'France'
        my_dict['hu'] = 'Hungary'
        my_dict['ttf'] = 'TTF Hi Cal 51.6'
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
        my_dict['EEX'] = 14
        my_dict['GFI'] = 5
        my_dict['TFS'] = 4
        my_dict['42FS'] = 3
        my_dict['ICAP'] = 6
        my_dict['EEX7'] = 14
        my_dict['SPEC'] = 7
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
            idem_id = int((delta.months + 12 * delta.years) / 12) * 40 + 670
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
            inst_name += ' EEX'
        elif venue == 'pegas':
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


class TPData(TPDataTemplate):
    def __init__(self):
        self.db_connection = None

    @property
    def order_query(self):
        query = "select datetime, unique_id, action, price, volume, side, " + \
                "status, impliedtype, persistentorderid, companyid, brokerid " + \
                "from trayport_orders ord " + \
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
    def best_order_query(self):
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
    def trade_query(self):
        query = "select datetime, price, volume, aggressoraction,  " + \
                "aggressorbroker_id_ut, initiatorcompany_id_ut, aggressorcompany_id_ut " + \
                "from ROVE_OD.TRAYPORT_VW_TRADES tvt " + \
                "where tvt.instname in ({placeholders})  " + \
                "and tvt.firstsequenceid = :seqid1 " + \
                "and tvt.firstsequenceitemid = :itemid1 " + \
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

    def create_connection(self, database):
        self.db_connection = Database(database)

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

    def get_orders_data(self, market, tenor, venue_list, start_date1, bT, eT,
                        prod='base', start_date2=None):
        params = self.orders_params(market, tenor, venue_list, prod,
                                    start_date1, start_date2, bT, eT)
        df_data = self.db_connection.execute(self.order_query, params)
        #df_data['price'] = (df_data['price'] * 10000).astype(int)
        #df_data = df_data.set_index('datetime')
        return df_data

    @staticmethod
    def mid_price_bo(df_data):
        return .5 * (df_data.loc[:, 'bidbestprice'] + df_data.loc[:, 'askbestprice'])

    @staticmethod
    def process_best_orders(df_data):
        mid_ser = .5 * (df_data.loc[:, 'bidbestprice'] + df_data.loc[:, 'askbestprice'])
        return df_data[mid_ser != mid_ser.shift()]

    def get_best_orders_data(self, market, tenor, start_date1, bT, eT,
                             prod='base', start_date2=None):
        venue_list = ['eex', 'otc', 'ice']
        params = self.orders_params(market, tenor, venue_list, prod,
                                    start_date1, start_date2, bT, eT)
        df_data = self.db_connection.execute(self.best_order_query, params)
        df_data = df_data.set_index('datetime')
        df_data = df_data.astype(float)
        return self.process_best_orders(df_data)

    @staticmethod
    def process_trades(df_data):
        cols_list = ['price', 'volume', 'aggressoraction', 'aggressorbroker_id_ut']
        df_data['price'] = df_data['price'].astype(float)
        # Buy Sell attribute
        action_dict = {'Buy': 1, 'Sell': -1}
        df_data['aggressoraction'] = df_data['aggressoraction'].replace(action_dict)
        # Our trade
        own_ser = ((df_data['initiatorcompany_id_ut'] == 1) | 
                   (df_data['aggressorcompany_id_ut'] == 1))
        idx = own_ser & (df_data['aggressorbroker_id_ut'] == 14)
        df_out = df_data.loc[~idx, cols_list]
        df_out.columns = ['price', 'volume', 'action', 'broker_id']
        return df_out

    def get_trades(self, market, tenor, venue_list, start_date1, bT, eT,
                   prod='base', start_date2=None):
        placeholders = ",".join([f":mkt_{i}" for i in range(len(venue_list))])
        query = self.trade_query.replace("{placeholders}", placeholders)
        params = self.trades_params(market, tenor, venue_list, prod,
                                    start_date1, start_date2, bT, eT)
        df_data = self.db_connection.execute(query, params)
        df_data = df_data.set_index('datetime')
        return self.process_trades(df_data)

    @staticmethod
    def filter_data(df_data, price_series, factor, day_bool=True):
        if day_bool:
            idx = np.abs(np.diff(price_series.index.day)) > 0
            price_series.iloc[1:].iloc[idx] = np.nan
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


class TPDataDa(TPDataTemplate):
    
        
    
    def __init__(self, user='matus'):
        self.db_connection = None
        self._user = user
        self._api_key = None
        
        
    @property
    def user(self):
        return self._user
        
    def set_api_key(self):
        PATH = '//etc-dc2k19/net/Algo/Database/configDB.json'
        with open(PATH, 'r') as file:
            config = json.load(file)['DataAnalytics']
            
        self._api_key = config[self.user]
        
    @property
    def api_key(self):
        self.set_api_key()
        return self._api_key
    
        
    def get_market_name(self, mkt, prod):
        return self.mkt_dict[mkt] + ' ' + self.prod_dict[prod]
        
    
    def get_marketId(self, mkt, prod):
        all_markets = self.get_df(self.url_composer('markets'))
        market_dict = all_markets[all_markets['name']==
                                  self.get_market_name(mkt, prod)].to_dict('records')[0]
        return market_dict['id']
            
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
                   prod='base', start_date2=None):
        
        params = {}
        params['from'] = bT.strftime('%Y-%m-%dT%H:%M:%SZ')
        params['until'] = eT.strftime('%Y-%m-%dT%H:%M:%SZ')
        params['marketId'] = self.get_marketId(market, prod)
        params['sequenceId'] = self.calc_seqid(market, tenor)
        params['sequenceItemId'] = [str(self.calc_itemid(tenor, a)) for a in
                                    [start_date1, start_date2] if a is not None]
        params['ContractType'] = 'SinglePeriod'
        
        return params
    
    
    def process_trades(self, df):
        df['datetime'] = pd.to_datetime('01-01-1970') + \
            pd.to_timedelta(df['dealDate']/1e9, unit='S')
            
        df.set_index(['datetime'],inplace=True)
        action_dict = {True: 1, False: -1}
        df['aggressorBuy'] = df['aggressorBuy'].replace(action_dict)
        df['venueCode'] = df['venueCode'].replace(self.broker_id_dict)
        df = df.rename(columns={'venueCode': 'broker_id',
                                'quantity': 'volume',
                                'aggressorBuy': 'action'})
        df = df[['price', 'volume', 'action', 'broker_id']].copy()
        return df
        
    
    def get_trades(self, market, tenor, venue_list,
                   start_date1, bT, eT,
                   prod='base', start_date2=None):
        url = self.url_composer('trades')
        result_df = pd.DataFrame()
        bT_i = bT
        eT_i = eT
        delta: timedelta = eT - bT
        while delta > timedelta(days=31):
            eT_i = eT - timedelta(days=(delta.days//31 * (delta.days%31)))
            params = self.get_params(market, tenor, venue_list,
                        start_date1, bT_i, eT_i,
                        prod='base', start_date2=None)
            
            if result_df.empty:
                result_df = self.get_df(url,params)
            else:
                result_df = pd.concat([result_df, self.get_df(url, params)])

            bT_i += timedelta(days=32)
            delta = eT - bT_i
        
        # Fetch remaining days
        params = self.get_params(market, tenor, venue_list,
            start_date1, bT_i, eT,
            prod='base', start_date2=None)
        df = self.get_df(url,params)

        if result_df.empty:
            result_df = df
        else:
            result_df = pd.concat([result_df, df])

        return self.process_trades(result_df)
    
    def get_best_orders_data(self, market, tenor,
                             start_date1, bT, eT,
                             prod='base', start_date2=None):
        params = self.get_params(market, tenor, venue_list,
                       start_date1, bT, eT,
                       prod='base', start_date2=None)
        
        params['interval'] = str(1)
        params['intervalUnit'] = 'second'
        
        url = self.url_composer('best_orders')
        df = self.get_df(url,params)
        return df
    

            
    
if __name__=='__main__':
    
    data_class = TPDataDa()
    mkt_list = ['de']
    tenor_list = ['w']
    tn1_list = [1]
    tn2_list = []
    prod = 'base'
    venue_list = ['eex']
    start_date = datetime(2023, 11, 17)
    end_date = datetime(2023, 11, 17)
    n_s = 2
    start_date1 = datetime(2023,11,20)
    
    test_df = data_class.get_best_orders_data(mkt_list[0], tenor_list[0],
                                     start_date1,
                                    start_date, end_date+timedelta(hours=10))
    params = data_class.get_params(mkt_list[0], tenor_list[0],
                                    venue_list[0], start_date1,
                                    start_date, end_date+timedelta(hours=10))                                    

    
    
        
        
        
        
        
        
        
    
        