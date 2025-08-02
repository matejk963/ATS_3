import update_coal_prices, update_eua_prices, update_ttf_prices

import datetime as dt

update_ttf_prices.gas_data_to_db(base_date=dt.datetime(2019,1,1), fut_periods=60)
update_ttf_prices.gas_da_df(base_date=dt.datetime(2019,1,1))
update_eua_prices.eua_data_to_db(base_date=dt.datetime(2019,1,1), fut_periods=60)
update_coal_prices.coal_data_to_db(base_date=dt.datetime(2019,1,1), fut_periods=60)

