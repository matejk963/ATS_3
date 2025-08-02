# Used to read data from the database
import platform
import oracledb
from sqlalchemy import create_engine, inspect, MetaData, Table, Column, DateTime, Float, text
from sqlalchemy.orm import sessionmaker
import sqlalchemy
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os


from Enums import DATABASE as DB_ENUM
from Common.config_load import get_config_path as CONFIG_PATH

# from Enums import DATABASE as DB_ENUM

class Database():
    _grid = [
        'DE', 'AT', 'FR', 'BE', 'NL',
        'DKW', 'DKE', 'FI', 'NO1',
        'N02', 'NO3', 'NO4', 'NO5',
        'PL', 'SE1', 'SE2', 'SE3', 'SE4',
        'SK','CZ', 'HU', 'RO', 'SI', 'BG', 'ES'
        ]

    def __init__(self, database='PostgreSQL', path_name=CONFIG_PATH(), verbose=False):
        self.connection_string = ''
        self.engine = None
        self.Session = None
        self.verbose = verbose
        self._load_config(database, path_name)
    
    def __enter__(self):
        """Context manager entry point - return self for use in 'with' statement"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point - ensure proper cleanup"""
        try:
            self._disconnect()
        except Exception as e:
            if self.verbose:
                print(f"Warning: Error during context manager cleanup: {e}")
        # Return False to propagate any exceptions that occurred in the with block
        return False

    @property
    def is_arm(self):
        return ('arm' in platform.machine().lower()) & (self._dbtype == 'oracle')

    @staticmethod
    def create_connection_string(config_dict):
        db_type = config_dict['dbtype']
        username = config_dict['user']
        password = config_dict['password']
        host = config_dict['host']
        port = config_dict['port']
        database = config_dict['database']
        if ('arm' in platform.machine().lower()) & (db_type == 'oracle'):
            connection_string = f"{username}/{password}" \
                f"@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))" \
                f"(CONNECT_DATA=(SERVER=DEDICATED)(SERVICE_NAME={database})))"
        elif db_type == 'oracle':
            connection_string = f"oracle+oracledb://{username}:{password}" \
                f"@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))" \
                f"(CONNECT_DATA=(SERVER=DEDICATED)(SERVICE_NAME={database})))"
        elif db_type == 'postgre':
            connection_string = f"{db_type}sql://{username}:{password}" \
                f"@{host}:{port}/{database}"
        elif db_type == 'tpda':
            connection_string = ''
        elif db_type == 'timescaledb':
            connection_string = f"postgresql://{username}:{password}" \
                f"@{host}:{port}/postgres"
        return connection_string

    def _load_config(self, database, path_name):
        with open(path_name, 'r') as file:
            config = json.load(file)[database]
        self._dbtype = config['dbtype']
        self.connection_string = self.create_connection_string(config)

    def _connect(self):
        try:
            if self.is_arm:
                self.Session = oracledb.connect(self.connection_string)
            else:
                self.engine = create_engine(self.connection_string, echo=self.verbose)
                Session = sessionmaker(bind=self.engine)
                self.Session = Session()
            print("Connected to the database %s" % self._dbtype)
        except Exception as e:
            print("Error:", e)

    def _disconnect(self):
        """Internal disconnect method with improved error handling"""
        try:
            if self.Session:
                self.Session.close()
                self.Session = None
                if self.verbose:
                    print("Session closed successfully")
        except Exception as e:
            if self.verbose:
                print(f"Warning: Error closing session: {e}")
        
        try:
            if self.engine:
                self.engine.dispose()
                self.engine = None
                if self.verbose:
                    print("Engine disposed successfully")
        except Exception as e:
            if self.verbose:
                print(f"Warning: Error disposing engine: {e}")
        
        if self.verbose:
            print("Disconnected from the database %s" % self._dbtype)
    
    def disconnect(self):
        """Public method for explicit disconnection - same as _disconnect but public"""
        self._disconnect()

    def execute(self, statement, params=None):
        """
        Execute a SQL statement and return the result
        Example:\n
        params = {
            "broker": 'Tradition'
        }
        smtm = "SELECT * FROM public.trayport_brokers WHERE broker = :broker"
        result = d.execute(smtm, params)
        """
        self._connect()
        result = None
        try:
            if self.is_arm:
                cursor = self.Session.cursor().execute(statement, params)
                self.Session.commit()
                column_names = [x[0].lower() for x in cursor.description]
                result = cursor.fetchall()
            else:
                cursor = self.Session.execute(text(statement), params)
                self.Session.commit()

                # Get column names from the Cursor object before fetching the result
                result = []
                column_names = cursor.keys()._keys
                result_list = cursor.fetchall()
                [result.append(res._data) for res in result_list]
            # Convert the result to a DataFrame
            result_df = pd.DataFrame(result, columns=column_names)
        except Exception as e:
            print("Query Error:", e)
        finally:
            self._disconnect()

        return result_df

    def execute_delete(self, statement, params=None):
        """
        Execute a SQL statement and return the result
        Example:\n
        params = {
            "broker": 'Tradition'
        }
        smtm = "SELECT * FROM public.trayport_brokers WHERE broker = :broker"
        result = d.execute(smtm, params)
        """
        self._connect()
        result = False
        try:
            if self.is_arm:
                self.Session.cursor().execute(statement, params)
                self.Session.commit()
                result = True
            else:
                self.Session.execute(text(statement), params)
                self.Session.commit()
                result = True
        except Exception as e:
            print("Query Error:", e)
        finally:
            self._disconnect()
        return result

    def execute_general_query(self, statement, params=None):
        """
        Execute a SQL statement and return the result
        Example:\n
        params = {
            "broker": 'Tradition'
        }
        smtm = "SELECT * FROM public.trayport_brokers WHERE broker = :broker"
        result = d.execute(smtm, params)
        """
        self._connect()
        result = None
        try:
            if self.is_arm:
                cursor = self.Session.cursor().execute(statement, params)
                self.Session.commit()
                status = cursor.context.cursor.statusmessage
                if 'INSERT' in status:
                    result = cursor.rowcount
                else:
                    column_names = [x[0].lower() for x in cursor.description]
                    result = cursor.fetchall()
            else:
                cursor = self.Session.execute(text(statement), params)
                self.Session.commit()
                status = cursor.context.cursor.statusmessage
                if 'INSERT' in status:
                    result = cursor.rowcount
                else:
                # Get column names from the Cursor object before fetching the result
                    result = []
                    column_names = cursor.keys()._keys
                    result_list = cursor.fetchall()
                    [result.append(res._data) for res in result_list]
            # Convert the result to a DataFrame
                    result = pd.DataFrame(result, columns=column_names)
        except Exception as e:
            print("Query Error:", e)
            result = None
        finally:
            self._disconnect()
            return result

        return result

    def upsert_df(self, df: pd.DataFrame, table_object):
        if df.empty:
            return -1
        table_name = 'stage_' + table_object.table
        try:
            rows_inserted = df.to_sql(table_name, schema=table_object.schema,
                                    con=self.connection_string, if_exists='replace')
        except Exception as e:
            return -1
        else:
            return rows_inserted
    
    def create_tables_from_df(self, empty_df: pd.DataFrame, table_object):
        empty_df.to_sql(table_object.table, schema=table_object.schema,
                                    con=self.connection_string, if_exists='replace')
        
        
        

    def select(self, table, cols='*', range=365, _from=None, _to=None, desc=False):
        """
        Select data from a table based on the parameters provided.
        Example: select('at_spot', _from='2023-05-10', _to='2023-05-01')

        parameters:
            table: use TABLES_ class to select a table
            cols: string that represents the columns to select (default: all columns)
            range: select a range of data in days (default: 365) 
            _from: start date of the range (default: today - range)
            _to: end date of the range (default: today)
            desc: order the result in descending order (default: False)
        returns:
            result: the result of the query
        """
        # date range check
        if not _to:
            _to = (datetime.now() + timedelta(days=1)
                   ).replace(hour=23, minute=59, second=0, microsecond=0)
        else:
            try:
                _to = datetime.strptime(_to, '%Y-%m-%d').replace(
                    hour=23, minute=59, second=0, microsecond=0)
            except Exception as e:
                print("Error:", e)
                return None
        if not _from:
            _from = (_to - timedelta(days=range)
                     ).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            try:
                _from = datetime.strptime(_from, '%Y-%m-%d')
            except Exception as e:
                print("Error:", e)
                return None

        stmt = f"SELECT {cols} FROM {table}"
        stmt += f" WHERE datetime BETWEEN '{_from}' AND '{_to}'"
        if desc:
            stmt += " ORDER BY datetime DESC"
        else:
            stmt += " ORDER BY datetime ASC"
   
        print("Statement '" + stmt + "' executed")
        return pd.read_sql(stmt, self.connection_string)

    def getSpotPriceData(self, listOfMarkets, range=365, _from=None, _to=None, desc=False):
        """
        Get spot price data for a list of markets\n
        Example:\n
            db = Database()\n
            db.getSpotPriceData(['de', 'at'], 365])\n
            db.getSpotPriceData(['de', 'at'], _from='2023-05-10', _to='2023-06-01'])\n
            db.getSpotPriceData(['de', 'at'], range=365, _to='2023-06-01', desc=True])\n
        parameters:
            listOfMarkets: list of markets to get data for
            range: select a range of data in days (default: 365)
            _from: optional: use with _to to select specific range
            _to: default is day ahead
            desc: order the result in descending order (default: False)
        """
        result_df = pd.DataFrame(columns=['datetime'])
        result_df.set_index('datetime', inplace=True)

        # check if list or value is provided
        if not isinstance(listOfMarkets, list):
            listOfMarkets = [listOfMarkets]
            
        for market in listOfMarkets:
            try:
                curr_df = self.select("spot." + market, cols='datetime,price',
                                  range=range, _from=_from, _to=_to)
                curr_df.set_index('datetime', inplace=True)
                curr_df.rename(columns={'price': market}, inplace=True)
                result_df = curr_df.join(result_df, how='outer')
            except Exception as e:
                print("Error for market = '", market, "'\n", e)
                continue
        return result_df.sort_index()
    
    def _create_tableRes(self):
        """
        Create a table in the database
        """
        self._connect()
        try:
            if not inspect(self.engine).has_table('residual'):
                # Table does not exist, so we create it
                metadata = MetaData()
                table = Table('residual', metadata,
                              Column('forecast_date', DateTime),
                              Column('value_date', DateTime),
                              Column('dem_ens', Float),
                              Column('dem_op', Float),
                              Column('wind_ens', Float),
                              Column('wind_op', Float),
                              Column('solar_ens', Float),
                              Column('solar_op', Float))

                result = table.create(self.engine)
        except Exception as e:
            print("Error:", e)
        finally:
            self._disconnect()
            return result
        
    def createTable(self):
        """
        Create a table in the database
        """
        self._connect()
        try:
            if not inspect(self.engine).has_table('normals'):
                # Table does not exist, so we create it
                metadata = MetaData()
                table = Table('normals', metadata,
                              Column('value_date', DateTime, unique=True),
                              Column('solar', Float),
                              Column('wind', Float),
                              Column('con', Float))
                result = table.create(self.engine)
        except Exception as e:
            print("Error:", e)
        finally:
            self._disconnect()
            return result

    # def merge_from_staging_to_prod(self, schema, table):
    #     self._connect()
    #     table_dict = DB_ENUM['postgre']
    #     with self.engine.connect() as conn:
    #         columns = table_dict[schema]['columns']
    #         tables = table_dict[schema]['tables']
    #         table_position = tables.index(table)
    #         columns = columns[table_position]
    #         keys = table_dict[schema]['primary_key']
    #         on_columns, update_set, insert_columns, values_columns = f"", f"", f"", f""

    #         for x in keys:
    #             on_columns += f"tgt.{x} = src.{x} AND "

    #         for i in range(len(columns)):
    #             update_set += f""""{columns[i]}"= CASE WHEN src."{columns[i]}" IS NOT NULL THEN src."{columns[i]}" ELSE tgt."{columns[i]}" END,\n"""
    #             insert_columns += f""""{columns[i]}", """
    #             values_columns += f"""src."{columns[i]}", """
            
    #         merge_query = text(f"""
    #             MERGE INTO "{schema}"."{table}" AS tgt
    #             USING "{schema}"."{'stage_'+ table}" AS src
    #             ON ({on_columns[:-5]})
    #             WHEN MATCHED 
    #             THEN UPDATE SET
    #             {update_set[:-2]}
    #             WHEN NOT MATCHED
    #             THEN INSERT ({insert_columns[:-2]})
    #             VALUES ({values_columns[:-2]});
    #         """)

    #         print(merge_query)
    #         result = conn.execute(merge_query)
    #         conn.commit()
    #         self._disconnect()
    #         return result


    def merge_from_staging_to_prod_enum(self, schema, table):
        self._connect()
        table_dict = DB_ENUM['postgre']
        with self.engine.connect() as conn:
            # Check if the table exists
            check_query = f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = '{schema}' AND table_name = '{table}');"
            table_exists = conn.execute(text(check_query)).scalar()
    
            if not table_exists:
                # If table does not exist, create it using the structure of the staging table
                create_query = f"CREATE TABLE \"{schema}\".\"{table}\" AS SELECT * FROM \"{schema}\".\"stage_{table}\" WHERE 1=0;"
                conn.execute(text(create_query))
                conn.commit()
                print(f"Table '{table}' created in schema '{schema}'.")
            
            # Proceed with merging or inserting data
            columns = table_dict[schema]['columns']
            tables = table_dict[schema]['tables']
            table_position = tables.index(table)
            columns = columns[table_position]
            keys = table_dict[schema]['primary_key']
            on_columns, update_set, insert_columns, values_columns = "", "", "", ""
    
            for x in keys:
                on_columns += f"tgt.{x} = src.{x} AND "
    
            for i in range(len(columns)):
                update_set += f""""{columns[i]}" = CASE WHEN src."{columns[i]}" IS NOT NULL THEN src."{columns[i]}" ELSE tgt."{columns[i]}" END,\n"""
                insert_columns += f""""{columns[i]}", """
                values_columns += f"""src."{columns[i]}", """
            
            merge_query = text(f"""
                MERGE INTO "{schema}"."{table}" AS tgt
                USING "{schema}"."{'stage_'+table}" AS src
                ON ({on_columns[:-5]})
                WHEN MATCHED THEN UPDATE SET
                {update_set[:-2]}
                WHEN NOT MATCHED THEN INSERT ({insert_columns[:-2]})
                VALUES ({values_columns[:-2]});
            """)

            print(merge_query)
            result = conn.execute(merge_query)
            conn.commit()
            self._disconnect()
            print('Result row count', result.rowcount)
            return result.rowcount
        
    def merge_from_staging_to_prod(self, schema, table):
        self._connect()
        with self.engine.connect() as conn:
            # Check if the table exists
            check_query = f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = '{schema}' AND table_name = '{table}'
                );
            """
            table_exists = conn.execute(text(check_query)).scalar()
    
            if not table_exists:
                # If table does not exist, create it using the structure of the staging table
                create_query = f"""
                    CREATE TABLE "{schema}"."{table}" AS 
                    SELECT * FROM "{schema}"."stage_{table}" WHERE 1=0;
                """
                conn.execute(text(create_query))
                conn.commit()
                print(f"Table '{table}' created in schema '{schema}'.")
    
            # Retrieve column names from the staging table
            get_columns_query = f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = '{schema}' AND table_name = 'stage_{table}';
            """

            get_primary_keys_query = f"""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = '{schema}'
                AND tc.table_name = '{table}'
                AND tc.constraint_type = 'PRIMARY KEY';
            """
            # Identify colu
            columns = [row[0] for row in conn.execute(text(get_columns_query)).fetchall()]
    
            keys = [col for col in columns if 'date' in col.lower()]

            if not keys:
                raise ValueError("No primary key columns found with 'date' in their name.")
    
            # Build the dynamic parts of the query
            on_columns = " AND ".join([f"tgt.{x} = src.{x}" for x in keys])
            update_set = ",\n".join(
                [f'"{col}" = CASE WHEN src."{col}" IS NOT NULL THEN src."{col}" ELSE tgt."{col}" END' for col in columns]
            )
            insert_columns = ", ".join([f'"{col}"' for col in columns])
            values_columns = ", ".join([f'src."{col}"' for col in columns])
    
            # Construct and execute the merge query
            merge_query = text(f"""
                MERGE INTO "{schema}"."{table}" AS tgt
                USING "{schema}"."stage_{table}" AS src
                ON ({on_columns})
                WHEN MATCHED THEN UPDATE SET
                {update_set}
                WHEN NOT MATCHED THEN INSERT ({insert_columns})
                VALUES ({values_columns});
            """)
    
            print(merge_query)
            result = conn.execute(merge_query)
            conn.commit()
            self._disconnect()
            return result



    def merge_from_staging_to_prod_multiple_keys(self, schema, table, comparison_columns,
                                                 datetime_cols_to_add=[]):
        """
        Merges data from the staging table into the production table, ensuring the structure aligns before merging.
        """
        self._connect()

        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            try:
                # Step 1: Transform datetime columns in staging table
                get_staging_column_types_query = text(f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = '{schema}' AND table_name = 'stage_{table}';
                """)
                staging_column_types = {row[0]: row[1] for row in conn.execute(get_staging_column_types_query).fetchall()}

                datetime_columns = [col for col, dtype in staging_column_types.items()
                                    if "date" in col.lower() or "time" in col.lower() or "datetime" in col.lower()]
                datetime_columns += datetime_cols_to_add
                
                for col in datetime_columns:
                    conn.execute(text(f"""
                        ALTER TABLE "{schema}"."stage_{table}" 
                        ALTER COLUMN "{col}" TYPE TIMESTAMP USING "{col}"::TIMESTAMP;
                    """))

                # Step 2: Check if the target table exists
                check_table_exists = text(f"""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema = '{schema}' AND table_name = '{table}';
                """)
                table_exists = conn.execute(check_table_exists).scalar() > 0
                
                if not table_exists:
                    conn.execute(text(f"""
                        CREATE TABLE "{schema}"."{table}" AS TABLE "{schema}"."stage_{table}" WITH NO DATA;
                    """))
                    print(f"✅ Created target table {table} from staging.")

                # Step 3: Ensure structures match
                get_target_column_types_query = text(f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = '{schema}' AND table_name = '{table}';
                """)
                target_column_types = {row[0]: row[1] for row in conn.execute(get_target_column_types_query).fetchall()}

                target_columns = set(target_column_types.keys())
                staging_columns = set(staging_column_types.keys())

                missing_in_target = staging_columns - target_columns
                for col in missing_in_target:
                    conn.execute(text(f"""
                        ALTER TABLE "{schema}"."{table}" ADD COLUMN "{col}" {staging_column_types[col]};
                    """))
                    print(f"✅ Added missing column {col} to {table}.")

                missing_in_staging = target_columns - staging_columns
                for col in missing_in_staging:
                    conn.execute(text(f"""
                        ALTER TABLE "{schema}"."stage_{table}" ADD COLUMN "{col}" {target_column_types[col]};
                    """))
                    print(f"✅ Added missing column {col} to stage_{table}.")

            except Exception as e:
                print(f"❌ Error: {e}")
                return False

        # Step 4: Check if comparison columns have a unique constraint
        with self.engine.connect() as conn:
            check_unique_constraint = text(f"""
                SELECT COUNT(*) FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = '{schema}'
                AND tc.table_name = '{table}'
                AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
                AND kcu.column_name IN ({', '.join(f"'{col}'" for col in comparison_columns)});
            """)
            has_unique_constraint = conn.execute(check_unique_constraint).scalar() > 0
        
        with self.engine.connect() as conn:
            with conn.begin():  # Use transaction
                try:
                    existing_columns = target_columns & staging_columns
                    where_conditions = [
                        f'tgt."{col}" = stage."{col}"' for col in comparison_columns if col in existing_columns
                    ]
                    where_condition = " AND ".join(where_conditions)

                    if where_condition:
                        delete_query = text(f"""
                            DELETE FROM "{schema}"."{table}" AS tgt
                            USING "{schema}"."stage_{table}" AS stage
                            WHERE {where_condition};
                        """)
                        conn.execute(delete_query)
                        print("✅ Deleted matching rows from target table.")

                    # Step 5: Insert new data from staging to target
                    insert_columns = ", ".join([f'"{col}"' for col in existing_columns])
                    if has_unique_constraint:
                        on_conflict_cols = ", ".join([f'"{col}"' for col in comparison_columns if col in existing_columns])
                        update_set_clause = ", ".join([f'"{col}" = EXCLUDED."{col}"' 
                                                        for col in existing_columns if col not in comparison_columns])
                        insert_query = text(f"""
                            INSERT INTO "{schema}"."{table}" ({insert_columns})
                            SELECT {insert_columns} FROM "{schema}"."stage_{table}"
                            ON CONFLICT ({on_conflict_cols})
                            DO UPDATE SET {update_set_clause};
                        """)
                    else:
                        insert_query = text(f"""
                            INSERT INTO "{schema}"."{table}" ({insert_columns})
                            SELECT {insert_columns} FROM "{schema}"."stage_{table}";
                        """)
                    result = conn.execute(insert_query)
                    print(f"✅ Inserted/Updated rows: {result.rowcount}")

                except Exception as e:
                    print(f"❌ Error: {e}")
                    return False

        self._disconnect()
        return True


    
    def create_and_load_staging_table(self, df, schema, table_name):
        """
        Creates a staging table with a unique constraint and loads data into it.

        :param df: Pandas DataFrame to be loaded into the staging table
        :param schema: Database schema name
        :param table_name: Table name (without 'stage_' prefix)
        """

        self._connect()  # Use the same connection method

        with self.engine.connect() as conn:
            # Check if the staging table exists
            check_query = f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = '{schema}' AND table_name = 'stage_{table_name}'
                );
            """
            table_exists = conn.execute(text(check_query)).scalar()

            if not table_exists:
                # Create table with unique constraint
                create_query = f"""
                    CREATE TABLE "{schema}"."stage_{table_name}" (
                        rel_product TEXT,
                        fcst_date TEXT,
                        market TEXT,
                        market_2 TEXT,
                        scenario_type TEXT,
                        del_type TEXT,
                        delivery_start TEXT,
                        delivery_end TEXT,
                        delivery_start_2 TEXT,
                        delivery_end_2 TEXT,
                        mean TEXT,
                        CONSTRAINT stage_{table_name}_unique_constraint UNIQUE (
                            rel_product, fcst_date, market, market_2, scenario_type, 
                            del_type, delivery_start, delivery_end, delivery_start_2, delivery_end_2
                        )
                    );
                """
                conn.execute(text(create_query))
                conn.commit()
                print(f"Table 'stage_{table_name}' created in schema '{schema}'.")

        # Load data into the staging table
        df.to_sql(
            name=f"stage_{table_name}",
            schema=schema,
            con=self.engine,  # Use existing engine connection
            if_exists='append',  # Append new data, keeping existing structure
            index=False
        )

        print(f"Data successfully loaded into 'stage_{table_name}'.")
        
        self._disconnect()  # Disconnect after operation


# if __name__=='__main__':
    # db = Database()
    # db.merge_from_staging_to_prod_multiple_keys('MODEL_forecast_prices',
    #                                     'xgboost_mean',
    #                                     ['rel_product', 'fcst_date', 'market', 'market_2',
    #                                     'scenario_type', 'del_type', 'delivery_start', 'delivery_end',
    #                                     'delivery_start_2', 'delivery_end_2'])