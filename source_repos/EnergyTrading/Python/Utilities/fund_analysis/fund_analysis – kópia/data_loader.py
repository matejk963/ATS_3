"""

Loading raw data from sources

Sources:
    database
    Eikon
    internal files/folders

"""
# Imports
#General
import pandas as pd
import datetime as dt
import os
from sqlalchemy import create_engine, text

import pdb

# Own
from fund_analysis.utils import ENUMS as enums
from Database.DB_reader import Database  as DB
from Loaders.EikonFut_class import EikonFut as EK





class DataLoader():
    
    
    
    def __init__(self, params_dict, source='db',
                    config=r"Z:\EnergyTrading\configDB.json"):
        self._sD = params_dict['sD']
        self._eD = params_dict['eD']
        self._source = source
        self._config = config
        if self._config:
            self._db_inst = DB(path_name=self._config)
        else:
            self._db_inst = DB()
        
        
    @property
    def sD(self):
        return self._sD
    
    @property
    def eD(self):
        return self._eD
    
    @property
    def source(self):
        return self._source
    
    @property
    def db_inst(self):
        return self._db_inst
    
    def update_date_range(self, sD, eD):
        self._sD = sD
        self._eD = eD
        
    def get_data_db(self, schema_name, table_name,
                            sD_fcst=None, eD_fcst=None,
                            datetime_col='forecast_date'):
        """
        Raw residual forecast data fetch
            Method to fetch FORECASTED data for Residual demand calculation (Consumption, Wind, Solar) where
        the output is dataframe where for each value from date_range(sD_fcst-eD_fcst) the full
        EC forecast is fetched from database.
            Resulting shape is thus (n*fcst_lenght, m) where
        n = no. of forecast dates in date_range(sD_fcst-eD_fcst)
        fcst_lenght = no. of hours the forecast (EC_ens00) provide
        m = columns ['forecast_date', 'value_date', 'con', 'wind', 'solar']

        ec_type : int, specifies the type of EC forecast (0,6,12,18)/default=0
        country : str, specifies the country to fetch the data for/default='de'
        sD_fcst/eD_fcst : datetime.datetime, default values are assigned with __init__
        """

        db_obj = self.db_inst
        con = db_obj.connection_string
        engine = create_engine(con)


        if sD_fcst is None:
            sD_fcst = self.sD
        if eD_fcst is None:
            eD_fcst = self.eD

        # Ensure sD_fcst and eD_fcst are not None and are properly formatted dates (as strings)
        if sD_fcst is None or eD_fcst is None:
            raise ValueError("Start date and end date must be provided.")
            
        # Date range: modify these dates to your requirements
        start_date = sD_fcst  # Start date
        end_date = eD_fcst + dt.timedelta(seconds=24*60*60-1)  # End date
        
        # Example table and schema names
        # schema_name = "FUND_ResidualDemand"
        # table_name = "DEU_00"
        
        # Prepare the query using placeholders without injecting variables directly
        # Note the use of double quotes to preserve the exact case of identifiers
        if 'normal' in [a.lower() for a in ['normal', 'ntc', 'syn']] and 'normal' in schema_name.lower():
            # Query for 'normal' case: select from start_date to the last available date (no end_date condition)
            query = text(f"""
            SELECT * FROM "{schema_name}"."{table_name}"
            WHERE value_date >= :start_date;
            """)
        elif any(a.lower() in schema_name.lower() for a in ['ntc', 'syn']):
            # Query for 'ntc' and 'syn' cases: select between start_date and end_date
            query = text(f"""
            SELECT * FROM "{schema_name}"."{table_name}"
            WHERE {datetime_col} BETWEEN :start_date AND :end_date;
            """)
        else:
            # Fallback or other cases can be handled here if necessary
            query = text(f"""
            SELECT * FROM "{schema_name}"."{table_name}"
            WHERE {datetime_col} BETWEEN :start_date AND :end_date;
            """)

        
        # Use pandas to read the SQL query into a DataFrame
        try:
            df = pd.read_sql(query, engine, params={'start_date': start_date, 'end_date': end_date})
        except:
            df = pd.DataFrame()

        return df
    
    
    def get_eikon_data(self, params_dict, cont):
        return EK(params_dict=params_dict, 
                    cont=cont).fwd_df(self.sD, self.eD)
        
    def get_futures_from_db(self):
        pass
    
    def get_fund_raw_data(self, fcst_type, fund,
                        ec_type,
                        market='de', source='db'):
        country = enums.from_own_name(market)
        if source in ['db']:
            schema_name = 'FUND_' + fund + '_' + fcst_type
            schema_name = schema_name.replace('_mid','')
            if not fcst_type in ['normal']:
                table_name = country + '_' + (ec_type)
            else:
                table_name = country
            # table_name = table_name.replace('_ ', '')
            df = self.get_data_db(schema_name, table_name)
            if fcst_type.lower() in ['normal']:
                df.columns = ['value_date', fund]
            return df
        elif source in ['local']:
            if fcst_type in ['normal']:
                file_name = country + '_' + fund + '_norm.csv'
                folder_path = '//192.168.10.91/d/data/Data/Normals/Normals'
                file_path = os.path.join(folder_path, file_name)
                df = pd.read_csv(file_path,
                                        parse_dates=['datetime'])
                df.columns = ['value_date', fund]
                df = df.loc[~df['value_date'].duplicated()].copy()
                return df
