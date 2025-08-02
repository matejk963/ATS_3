# -*- coding: utf-8 -*-
"""
Created on Thu Aug  3 11:01:41 2023

@author: krajcovic
"""
import sys,os
sys.path.append(r'C:/data/EnergyTrading/Python/')
import pandas as pd
import psycopg2
import datetime as dt
import logging
from dateutil.relativedelta import relativedelta

from sqlalchemy import create_engine, text, exc, MetaData, Table, Column, DateTime, Float, inspect, types

# Set up logger
logger = logging.getLogger(__name__)
from Loaders.data_scraper import scrapeEpex,\
    scrapeHu,\
        scrapeOkte, scrapeOte, scrapeSi, scrapeRo,\
            scrapeBg
from Database.DB_reader import Database
from Common.config_load import get_config_path as CONFIG_PATH

try:
    from Loaders.EikonSpot_class import EikonSpot as ES
except ModuleNotFoundError:
    pass

class db_writer(Database):
    def __init__(self, database='PostgreSQL', path_name=CONFIG_PATH()):
        self.connection_string = ''
        self.engine = None
        self.Session = None
        super()._load_config(database, path_name)

    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.cleanup_connections()
    
    def cleanup_connections(self):
        """Properly cleanup database connections and resources"""
        try:
            if self.Session:
                self.Session.close()
                self.Session = None
            if self.engine:
                self.engine.dispose()
                self.engine = None
        except Exception as e:
            print(f"Warning: Error during connection cleanup: {e}")
        
    def history_fetch(self,grid,
                      start,end):
        start = pd.to_datetime(start)
        end = pd.to_datetime(end)
        
        if ((grid.upper() == 'DE')or
            (grid.upper() == 'AT')) and\
            (pd.to_datetime(start)<pd.to_datetime('20181001')):
            spot1 = ES(grid,start,end)
            df1 = spot1.spot_data()
            spot2 = ES('deat',start,end)
            df2 = spot2.spot_data()
            
            df = df2.fillna(df1)
        elif grid.upper() == 'SK':
            df = pd.DataFrame()
            for date in pd.date_range(start=start,
                                              end=end\
                                                  +relativedelta(years=1),
                                                  freq='Y'):
                start_date = date\
                    +relativedelta(years=-1)\
                        -dt.timedelta(days=-1)
                delta = (date-start_date).days
                temp = scrapeOkte(delta=delta, end=date)
                if df.empty:
                    df = temp.copy()
                else:
                    df = pd.concat([df,temp])
        else:
            spot = ES(grid,start,end)
            df = spot.spot_data()
            if grid.upper() == 'BG':
                df['price'] = df['price']*0.51129188
        
        
        df.loc[:,df.columns!='price'] =\
            round(df.loc[:,df.columns!='price'],0)
        return df
    
    def db_conn(self):
        conn = psycopg2.connect(
            database=self.database,
            user=self.username,
            password=self.password,
            host=self.host,
            port=self.port)
        return conn
    
    def check_table_data(self, table_name, conn):
        try:
            table_name = table_name
            # Connect to the PostgreSQL database
            conn = conn
            cursor = conn.cursor()
    
            # Execute a query to count the number of rows in the table
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            count = cursor.fetchone()[0]
    
            # Close the cursor and connection
            cursor.close()
            conn.close()
    
            # Return True if there are data in the table, otherwise False
            return count > 0
    
        except (Exception, psycopg2.DatabaseError) as error:
            print("Error:", error)
            return False
        
    def create_table(self, table_name, df):
        self._connect()
        metadata = MetaData(self.connection_string)
        try:
            if not inspect(self.engine).has_table(table_name):
                # Table does not exist, so we create it
                table = Table(table_name, metadata,
                              Column('datetime', DateTime, primary_key=True),
                              Column('b_volume', Float),
                              Column('s_volume', Float),
                              Column('volume', Float),
                              Column('price', Float))
                metadata.create_all(self.engine)
                
                # Insert the records from the DataFrame
                df.to_sql(table_name, self.engine, index=False, if_exists='append')
                return True
            else:
                return False
        except Exception as e:
            print("Error:", e)
            logger.error("Error: %s", e)
        finally:
            self._disconnect()

    def spot_write(self, country, delta=5):
        """Enhanced spot_write with better error handling and resource management"""
        grid = country.upper()
        df = None
        
        try:
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
            else:
                return 2
            
            if not isinstance(df, pd.DataFrame):
                print(f'Scrape result for {grid} is not a dataframe')
                return -2
            
            dtypes = {
                'datetime': types.TIMESTAMP,
                'b_volume': types.FLOAT,
                's_volume': types.FLOAT,
                'volume': types.FLOAT,
                'price': types.FLOAT
            }
            
            # Ensure DataFrame is clean and properly formatted
            df = df.reset_index(names='datetime').drop_duplicates(subset=['datetime']).set_index('datetime')
            
            # Use with statement to ensure connection cleanup
            try:
                df.to_sql(name="stage_" + country.lower(), schema='spot', 
                         con=self.connection_string, if_exists='replace', dtype=dtypes)
            except Exception as db_error:
                print(f"Database write error for {country}: {db_error}")
                return -2
            
            if df['price'].isnull().values.any():
                return -1
            else:
                return 1
                
        except Exception as e:
            print(f"Error in spot_write for {country}: {e}")
            return -2
        finally:
            # Clean up DataFrame to free memory
            if df is not None:
                del df
            import gc
            gc.collect()

    def database_write(self,grid,
                      start=None,end=None,
                      history=False):
        table_name = grid.lower() + '_spot'
        if history == True:
            df = self.history_fetch(grid,
                              start,end)
        else:
            grid = grid.upper()
            if grid in ['DE', 'AT', 'FR', 'BE', 'NL',
                                'DKW', 'DKE', 'FI', 'NO1',
                                'N02', 'NO3', 'NO4', 'NO5',
                                'PL', 'SE1', 'SE2', 'SE3', 'SE4']:
                df = scrapeEpex(grid)
            elif grid == 'HU':
                df = scrapeHu()
            elif grid == 'CZ':
                df = scrapeOte()
            elif grid == 'SK':
                df = scrapeOkte()
            elif grid == 'SI':
                df = scrapeSi()
            elif grid == 'RO':
                df = scrapeRo()
            elif grid == 'BG':
                df = scrapeBg()

        # Convert NaN values to None
        df = df.where(pd.notnull(df), None)
    
        # Convert the DataFrame index into a column named 'datetime'
        df_temp = df.reset_index().rename(columns={'index': 'datetime'})

        created = self.create_table(table_name, df_temp)

        if created:
            # Check if the unique constraint already exists
            result = self.execute_general_query(f"""
                SELECT 1 FROM information_schema.table_constraints 
                WHERE constraint_name='unique_datetime' AND table_name='{table_name}';
            """).values.tolist()[0]
            # If the unique constraint does not exist, attempt to add it
            if not result:
                try:
                    self.execute_general_query(f"ALTER TABLE {table_name} ADD CONSTRAINT unique_datetime UNIQUE(datetime)")
                except exc.ProgrammingError as e:
                    # Catch the specific error when constraint already exists
                    if "relation \"unique_datetime\" already exists" in str(e):
                        pass
                    else:
                        error_message = str(e)
                        logger.error("Error: %s", error_message)
                        raise e
                except exc.IntegrityError as e:
                    error_message = str(e)
                    logger.error("Error: %s", error_message)
                    print("Error while adding unique constraint:", e)
                except Exception as e:
                    error_message = str(e)
                    logger.error("Error: %s", error_message)
                    print("Error while adding unique constraint:", e)
        else:
            # Upsert data from DataFrame into the database
            insertedRows = [0,0]
            for row in df_temp.to_dict('index').values():
                insertedRows[0] += 1
                stmt = f"""
                INSERT INTO {table_name} (datetime, b_volume, s_volume, volume, price)
                VALUES (:datetime, :b_volume, :s_volume, :volume, :price)
                ON CONFLICT (datetime)
                DO UPDATE SET b_volume=excluded.b_volume, s_volume=excluded.s_volume, volume=excluded.volume, price=excluded.price;
                """
                try:
                    params = {
                        "datetime": row['datetime'],
                        "b_volume": row['b_volume'],
                        "s_volume": row['s_volume'],
                        "volume": row['volume'],
                        "price": row['price']
                    }
                    result = self.execute_general_query(stmt, params)
                    print(table_name, result, row['datetime'])
                    insertedRows[1] += result

                except Exception as e:
                    error_message = str(e)
                    logger.error("Error: %s", error_message)
            logger.info(f"Inserted {insertedRows[1]} rows out of {insertedRows[0]} rows in {table_name} table.")