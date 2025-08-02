from datetime import timedelta, datetime
import pandas as pd

from Loaders.fund_fetch import fetch_fund_ftp
from Loaders.fut_eua_price_fetch import insert_files_to_db as eua_fetch
from Loaders.fut_gas_price_fetch import insert_files_to_db as gas_fetch
from Loaders.fut_price_fetch import insert_files_to_db as fut_fetch


if __name__ == "__main__":

    countries=['at','de', 'fr', 'fr', 'hu','hu',
                'cz', 'cz', 'sk', 'sk', 'it', 'it',
                'at', 'at', 'nl','nl', 'be', 'be',
                'ro', 'ro', 'ro']
    for country in countries:
        fut_fetch(country=country,
                    base_date=datetime(2019,1,1))
    countries=['ttf']*3
    for country in countries:
        gas_fetch(country=country,
                    base_date=datetime(2019,1,1))
    countries=['eua']*3
    for country in countries:
        eua_fetch(country=country,
                    base_date=datetime(2019,1,1))
    fetch_fund_ftp(fund_list= ['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
            grid_list= ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
            hour= '00')
    fetch_fund_ftp(fund_list= ['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
            grid_list= ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
            hour= '12')
    fetch_fund_ftp(fund_list= ['Temp_mnd', 'Wind_mnd', 'Solar_mnd', 'CON_mnd'],
            grid_list= ['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
            hour= '00')
    fetch_fund_ftp(fund_list= ['AvailCap'],
            grid_list= ['DEU', 'FRA'],
            hour= '00')
    fetch_fund_ftp(fund_list=[f"ResidualDemand_{a}th" for a in [10,25,75,90]],
                        grid_list=['DEU', 'FRA', 'BEL', 'NLD', 'ESP'],
                        hour='00')
    
    