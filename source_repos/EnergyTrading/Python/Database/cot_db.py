# -*- coding: utf-8 -*-
"""
Created on Fri Feb 28 13:57:20 2025

@author: scasny
"""
import pandas as pd
from sqlalchemy import create_engine, types
from io import BytesIO
import requests
from bs4 import BeautifulSoup

from Database.DB_reader import Database
    

def transform_excel_to_sql(xls):
    # Define mapping configuration
    ACTOR_MAP = {
        'Investment Firms or credit institutions': 'CreditInst',
        'Investment Funds': 'InvFunds',
        'Other Financial Institutions': 'OtherIns',
        'Commercial Undertakings': 'Commer',
        'Operators with compliance obligations under Directive 2003/87/EC': 'Operators'
    }

    
    # Process each relevant sheet (current report and historical)
    all_records = []
    
    
    for sheet_name in xls.sheet_names:
        if 'Weekly_Report' not in sheet_name:
            continue
            
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        df.loc[:, 0] = df.loc[:, 0].ffill()
        
        # Extract report date from row 2 (0-based index)
        date_str = df[df[0].str.contains('Date to which', na=False)].iloc[0,1]
        instrument = df[df[0].str.contains('product', na=False)].iloc[0,1]
        report_date = pd.to_datetime(date_str).date()
        
        # Find data headers row (contains 'Long')
        header_row_idx = df[df.apply(lambda row: 'Long' in row.values, axis=1)].index[0]
        headers = df.iloc[header_row_idx-1:header_row_idx+1].fillna(method='ffill', axis=1)
        headers = headers.apply(lambda x: x.ffill().astype(str) if x.notnull().any() else x)
        
        # Process multi-level headers
        actor_columns = {}
        for col_idx in range(3, len(headers.columns)):
            actor = headers.iloc[0, col_idx].strip()
            direction = headers.iloc[1, col_idx].strip()
            if actor in ACTOR_MAP:
                actor_columns[(actor, direction)] = col_idx
                
        # Process data rows
        for row_idx in range(header_row_idx+1, len(df)):
            row = df.iloc[row_idx]
            if not isinstance(row[0], str):
                continue
            
            if "Number of positions" in row[0]:
                if pd.isna(row[2]) or row[2] not in ['Risk reducing directly related to commercial activities', 'Other']:
                    continue
                    
                risk_reducing = row[2] == 'Risk reducing directly related to commercial activities'
                
                # Handle different value types
                def convert_value(val):
                    try:
                        if pd.isna(val) or val == '.':
                            return 0
                        return int(float(val))
                    except:
                        return None
                        
                # Process each actor column pair
                for (actor, direction), col_idx in actor_columns.items():
                    value = convert_value(row[col_idx])
                    if value is not None:
                        all_records.append({
                            'date': report_date,
                            'instrument': instrument,
                            'direction': direction.lower(),
                            'actor': ACTOR_MAP[actor],
                            'risk_reducing': risk_reducing,
                            'volume': value
                        })
    
    return pd.DataFrame(all_records)

def get_archive_files(year_q:str='2021Q1'):
    URL = f"https://public.eex-group.com/eex/mifid2/rts-21/archive/{year_q}/"
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    file_list = []
    
    for link in soup.select('table a[href]'):
        href = link['href']
        if href.startswith('WPR_') and href.endswith('.xlsx') and href != '..':
            file_list.append(URL + href)
    return file_list
    
    
    
# Example usage
if __name__ == "__main__":
    db = Database()
    urls = [get_archive_files(year_q) for year_q in ['2021Q1', '2021Q2', '2021Q3', '2021Q4', '2022Q1', '2022Q2', '2022Q3', '2022Q4', '2023Q1', '2023Q2', '2023Q3', '2023Q4', '2024Q1', '2024Q2', '2024Q3', '2024Q4', '2025Q1']]
    urls = sum(urls, [])
    for URL in urls:
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

