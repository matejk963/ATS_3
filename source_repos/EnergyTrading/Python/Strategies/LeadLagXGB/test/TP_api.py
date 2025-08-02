from environment import TP_CRED
import time
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
import numpy as np
import enumerate as ENUM

class TP_api():
    def __init__(self, env='test'):
        self.token = None
        self.headers = None
        if env == 'prod':
            self.url = TP_CRED.PROD_URL
            self.credentials = {
                'login': TP_CRED.USER,
                'password': TP_CRED.PASSWORD_PROD
            }
        else:
            self.url = TP_CRED.TEST_URL
            self.credentials = {
                'login': TP_CRED.USER,
                'password': TP_CRED.PASSWORD
            }
        self._set_token()

    def _set_token(self):
        # Endpoint for obtaining the token
        auth_url =self.url +'/users/login'

        # Make the authentication request
        response = requests.post(auth_url, json=self.credentials)

        # Extract the token from the response
        self.token = response.json()['token']
        self.headers = {'token': self.token}

    def active_strategies(self):
        response = requests.get(self.url+'/strategies', headers=self.headers).json()
        return [x['trading_portfolio'] for x in response if x['active']]
    
    def steering(self, algo_id, steering_list):
        json = {
            "steering_call": steering_list
        }
        response = requests.post(self.url+f"/strategies/steering/{algo_id}",
                                headers=self.headers,
                                json=json)
        return self._process_response(response)
    
    
    def get_monitoring_ts(self, algo_id):
        # Prepare the datetime strings
        today = datetime.now() - timedelta(days=15)
        tomorrow = today + timedelta(days=30)
        utc_iso_from = datetime(today.year, today.month, today.day, 0, 0, 0,
                                 tzinfo=timezone.utc).isoformat(timespec='milliseconds')
        utc_iso_until = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0,
                                  tzinfo=timezone.utc).isoformat(timespec='milliseconds')

        # Remove timezone info if not needed
        utc_iso_from = utc_iso_from.replace('+00:00', '') + 'Z'
        utc_iso_until = utc_iso_until.replace('+00:00', '') + 'Z'

        parameters = {
            'values_from': utc_iso_from,
            'values_until': utc_iso_until,
            'trading_portfolio': algo_id,
            'timeseries_name': 'stats'
        }
        print(parameters)
        response = requests.get(self.url+f"/timeseries",
                                headers=self.headers,
                                params=parameters,)
        return self._process_response(response)

    def set_limits(self, data_dict, algo_id):
        url = self.url + '/strategies/limits/' + algo_id
        response = requests.put(url=url, headers=self.headers, json=data_dict)
        return self._process_response(response)
    
    def get_strategies(self):
        url = self.url + '/strategies'
        response = requests.get(url=url, headers=self.headers)
        return self._process_response(response)
    
    def create_strategy(self, data_dict):
        url = self.url + '/strategies'
        response = requests.post(url=url, headers=self.headers, json=data_dict)
        return self._process_response(response)
    
    def delete_strategy(self, algo_id):
        url = self.url + '/strategies/' + algo_id
        response = requests.delete(url=url, headers=self.headers)
        return self._process_response(response)

    def activate_strategy(self, algo_id):
        url = self.url + '/strategies/' + algo_id
        response = requests.put(url=url, headers=self.headers, json={"active": 'true'})
        return self._process_response(response)

    def deactivate_strategy(self, algo_id):
        url = self.url + '/strategies/' + algo_id
        response = requests.put(url=url, headers=self.headers, json={"active": 'false'})
        return self._process_response(response)
    
    def info_packages(self):
        url = self.url + '/packages'
        response = requests.get(url=url, headers=self.headers)
        return self._process_response(response)
    
    def upload_packages(self, file_path):
        file_name = file_path.split('\\')[-1][:-4]
        url = self.url + '/packages'
        
        # Open the file in binary mode
        with open(file_path, 'rb') as f:
            files = {
                'package_zip': (file_path, f, 'application/zip')
            }
            data = {
                'package_name': file_name
            }
            
            # Send the POST request with both the file and the data
            response = requests.post(url=url, headers=self.headers, data=data, files=files)
        
        return self._process_response(response)
    
    def delete_package(self, package_name):
        url = self.url + '/packages/' + package_name
        response = requests.delete(url=url, headers=self.headers)
        return self._process_response(response)
    
    def get_own_trades(self, ts_after):
        url = self.url + '/own_trades'
        parameters = {
            'exchange': 'TRAYPORT',
            'execution_after': ts_after
        }
        response = requests.get(url,
                                headers=self.headers,
                                params=parameters,)
        return self._process_response(response)
    
    @staticmethod
    def _process_response(response):
        if response.content == b'':
            return response
        elif response.status_code >= 400:
            return response.json()
        else:
            try:
                json = response.json()
                if json == {}:
                    return response
            
                if 'timeseries' in response.url:
                    return response
                if 'packages' in response.url:
                    return [{'package_name': x['package_name'],
                             'last_updated': x['last_updated_utc']} for x in json]
                if isinstance(json, dict):
                    message = json.get('message', None)
                else:
                    message = None

                if message != None:
                    return message
                else:
                    return json
            except Exception as e:
                return response
    
    def get_current_pnl(self, day=None):
        today = datetime.now()
        if day:
            ts_utc = datetime(today.year, today.month, day, 0, 0, 0).isoformat(timespec='milliseconds')
        else:
            ts_utc = datetime(today.year, today.month, today.day, 0, 0, 0).isoformat(timespec='milliseconds')
        print(ts_utc)
        result_dict = self.get_own_trades(ts_utc)

        broker_fee_map = {
            ENUM.Broker._42FS: .025,
            ENUM.Broker._TFS: .025,
            ENUM.Broker._SPEC: .035,
            ENUM.Broker._EEX: .015,
            ENUM.Broker._GFI: .025,
            ENUM.Broker._ICAP: .025,
            ENUM.Broker._GRFN: .025
        }
        is_lapyear = lambda year: year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        month_day_map = {
            1: 31,
            2: 29 if is_lapyear(today.year) else 28,
            3: 31,
            4: 30,
            5: 31,
            6: 30,
            7: 31,
            8: 31,
            9: 30,
            10: 31,
            11: 30,
            12: 31
        }

        pnl_product_map = {
            ENUM.SequenceID.W: 720/4.0,
            ENUM.SequenceID.M: 720,
            ENUM.SequenceID.Q: 2160,
            ENUM.SequenceID.Y: 8640,
        }

        columns = ['execution_time', 'product_id', 'aggressor_broker_id', 'sell_delivery_area', 'buy_delivery_area', 'price', 'quantity', 'trader_name']

        trades = {k: [] for k in columns}
        direction = lambda x: 1 if x['buy_delivery_area'] == '' else -1
        fee = lambda x: broker_fee_map[x['aggressor_broker_id']]*x['quantity']

        for trade in result_dict:
            for c in columns:
                trades[c].append(trade[c])

        df = pd.DataFrame(trades)
        df['fee'] = df.apply(fee, axis=1)
        df['direction'] = df.apply(direction, axis=1)
        df['price'] = df['price'] * df['quantity']
        df['delivery_area'] = df.apply(lambda x: x['buy_delivery_area'] if x['buy_delivery_area'] else x['sell_delivery_area'], axis=1)
        df['product_id'] = df['product_id'] + '_' + df['delivery_area']
        df = df[(df['trader_name'] == '220_ETC-autotrader') | (df['trader_name'] == 'Matej Krajcovic')]
        # df = df[df['trader_name'] == '220_ETC-autotrader']
        df.reset_index(inplace=True)

        product_ids = df['product_id'].unique()
        mask = [True] * len(df)
        for p in product_ids:
            aux_df = df[df['product_id'] == p].copy()
            aux_df['volume'] = aux_df['quantity']*aux_df['direction']
            if round(aux_df['volume'].sum()) != 0:
                volume_off = aux_df['volume'].sum()
                for row in reversed(aux_df.to_dict(orient='records')):
                    if np.sign(volume_off) != np.sign(row['volume']):
                        continue
                    mask[aux_df.iloc[row['index']].name] = False
                    volume_off -= row['volume']
                    if volume_off == 0:
                        break
                    
        df = df[mask]

        series_pnl = df.groupby('product_id').apply(
            lambda x:
            x[x['direction'] > 0]['price'].sum() - x[x['direction'] < 0]['price'].sum() - x['fee'].sum())

        month_item_id_to_month = lambda x: (x-241)%12+1
        q_item_id_to_q = lambda x: (x-81)%4+1
        y_item_id_to_year = lambda x: (x-22)+2025
        # Function to get the mapping value based on substring
        def get_mapping_value(product):
            for key, value in pnl_product_map.items():
                if key in product:
                    if key == ENUM.SequenceID.M:
                        month_number = month_item_id_to_month(int(product.split('_')[-1]))
                        return month_day_map[month_number]*24
                    if key == ENUM.SequenceID.Q:
                        q_number = q_item_id_to_q(int(product.split('_')[-1]))
                        days = sum([month_day_map[q_number*i] for i in range(1,4)])
                        return days*24
                    if key == ENUM.SequenceID.Y:
                        y_number = y_item_id_to_year(int(product.split('_')[-1]))
                        return 366*24 if is_lapyear(y_number) else 365*24

                    return value
            return None

        # Apply the mapping function to each element of the index
        mapped_values = series_pnl.index.to_series().apply(get_mapping_value)

        # Create a DataFrame to hold the values and the mapped values
        df = pd.DataFrame({
            'product': series_pnl.index,
            'value': series_pnl,
            'mapped_value': mapped_values
        })

        # Apply the mapping to the 'value' column, ensuring we only apply where a mapping exists
        df['pnl'] = df.apply(
            lambda row: row['value'] * row['mapped_value'] if row['mapped_value'] is not None else row['value'], 
            axis=1
        )
        df.drop(columns=['mapped_value', 'product', 'value'], inplace=True)
        return df
