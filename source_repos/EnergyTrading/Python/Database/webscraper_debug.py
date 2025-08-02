import sys,os
import traceback
import pandas as pd
from sqlalchemy import types
sys.path.append(r'C:/data/EnergyTrading/Python/')

from Database.DB_writer import db_writer
from Database.DB_reader import Database
from Loaders.data_scraper import scrapeEpex,\
    scrapeHu,\
        scrapeOkte, scrapeOte, scrapeSi, scrapeRo,\
            scrapeBg

if __name__ == "__main__":
    db_r = Database()
    delta = 3 # number of days into history

    for grid in ['CZ']:
        if grid in ['DE', 'AT', 'FR', 'BE', 'NL',
                    'DKW', 'DKE', 'FI', 'NO1',
                    'N02', 'NO3', 'NO4', 'NO5',
                    'PL', 'SE1', 'SE2', 'SE3', 'SE4']:
            df = scrapeEpex(grid)
        elif grid == 'HU':
            df = scrapeHu(delta=delta)
        elif grid == 'CZ':
            df = scrapeOte(delta=delta)
        elif grid == 'SK':
            df = scrapeOkte(delta=delta)
        elif grid == 'SI':
            df = scrapeSi(delta=delta)
        elif grid == 'RO':
            df = scrapeRo(delta=delta)
        elif grid == 'BG':
            df = scrapeBg(delta=delta)
        dtypes = {
            'datetime': types.TIMESTAMP,
            'b_volume': types.FLOAT,
            's_volume': types.FLOAT,
            'volume': types.FLOAT,
            'price': types.FLOAT
        }
        df = df.reset_index(names='datetime').drop_duplicates(subset=['datetime']).set_index('datetime')
        df.to_sql(name="stage_" + grid.lower(), schema='spot', con=db_r.connection_string, if_exists='replace', dtype=dtypes)
        
        db_r.merge_from_staging_to_prod(schema='spot', table=grid.lower())