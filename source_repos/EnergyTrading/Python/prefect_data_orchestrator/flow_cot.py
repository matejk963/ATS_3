
import pandas as pd
from sqlalchemy import create_engine, types
from io import BytesIO
import requests
from bs4 import BeautifulSoup
import json
from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact

from Database.DB_reader import Database
from Database.cot_db import transform_excel_to_sql

@flow(log_prints=True, retries=3, retry_delay_seconds=600, timeout_seconds=180)
def commitments_of_traders():
    URL = "https://public.eex-group.com/eex/mifid2/rts-21/"

    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')

    url_list = []

    for link in soup.select('table a[href]'):
        href = link['href']
        if href.startswith('WPR_') and href.endswith('.xlsx') and href != '..':
            url_list.append(URL + href)


    db = Database()
    for URL in url_list:
        # Process all Excel files
        response = requests.get(URL)
        b_xls = BytesIO(response.content)
        xls = pd.ExcelFile(b_xls)
        df = transform_excel_to_sql(xls)
        
        # Filter out null volumes
        df = df[df['volume'].notna()]
        
        print(URL, 'in process')
        # Generate SQL inserts
        df.to_sql(name='stage_cot_entries', schema='cot', con=db.connection_string, if_exists='replace', index=False,
                dtype={
                    'date': types.DATE,
                    'instrument': types.VARCHAR,
                    'direction': types.VARCHAR,
                    'actor': types.VARCHAR,
                    'risk_reducing': types.BOOLEAN,
                    'volume': types.INTEGER
                })
            
        rows = db.merge_from_staging_to_prod_enum('cot', 'cot_entries')
