import pandas as pd
from copy import deepcopy
from Database.DB_reader import Database

from . import ENUMS



def get_raw_prices(markets: dict = None):
    if markets is None:
        markets = deepcopy(ENUMS.MARKETS)
    
    # Load markets (default is all markets and ttf as default gas)
    markets_raw_dict = {}
    schema_name = 'futures'
    db = Database()
    if not markets:
        markets = [market for sublist in ENUMS.MARKETS.values() for market in sublist]
    else:
        markets = [a.lower() for a in markets]
    for market in  markets:
        
        table_name = market.lower()
        markets_raw_dict[market] = pd.read_sql(f'SELECT * FROM "{schema_name}"."{table_name}"', con=db.connection_string).sort_values('datetime')
        # markets_raw_dict[market]['settlement_price'] = pd.to_numeric(markets_raw_dict[market]['settlement_price'].str.replace(',','.'),
        #                                                   errors='coerce')
        if market in ['eua']:
            continue
        elif market in ['ttf']:
            try:
                ps_data = pd.read_sql(f'SELECT * FROM "projected_settle"."{table_name}"', con=db.connection_string)
                # ps_data = ps_data.loc[ps_data['product_type'] == 'Month'].copy()
                if ps_data.empty:
                    raise ValueError(f"No data with product_type 'Month' present in table {table_name}.")
                markets_raw_dict[market] = pd.concat([markets_raw_dict[market], ps_data]).sort_values(['datetime']).drop_duplicates()
            except Exception as e:
                print('Trying to load ttf projected settlement when no ttf projected settlement has been saved')
        else:
            try:
                ps_data = pd.read_sql(f'SELECT * FROM "projected_settle"."{table_name}"', con=db.connection_string)
                # ps_data = ps_data.loc[ps_data['product_type'] == 'Month'].copy()
                if ps_data.empty:
                    raise ValueError(f"No data with product_type 'Month' present in table {table_name}.")
                markets_raw_dict[market] = pd.concat([markets_raw_dict[market], ps_data]).sort_values(['datetime']).drop_duplicates()
            except Exception as e:
                raise ValueError("Error loading ttf projected settlement data; ensure data is present.") from e

    
    return markets_raw_dict

def get_raw_spot_prices():
    markets_raw_dict = {}
    schema_name = 'spot'
    db = Database()
    for market in  [market for sublist in ENUMS.MARKETS.values() for market in sublist]:
        
        table_name = market.lower()
        markets_raw_dict[market] = pd.read_sql(f'SELECT * FROM "{schema_name}"."{table_name}"', con=db.connection_string)

    return markets_raw_dict

    
if __name__ == '__main__':
    test_dict = get_raw_prices()