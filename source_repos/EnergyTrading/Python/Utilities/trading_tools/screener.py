import sys
import os

# Get the absolute path of the "fund_analysis" package in your current branch
package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')

# Add it to sys.path
sys.path.insert(0, package_path)
import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
from concurrent.futures import ProcessPoolExecutor, as_completed

from Database.DB_reader import Database
from Utilities.fund_analysis.fund_analysis import input_data
from Utilities.trading_tools.screener_spread_maker import build_spreads_for_screener
from Utilities.tech_analysis.tech_analysis_manager import TechAnalysis_manager

import pandas as pd
from openpyxl import load_workbook
from openpyxl.worksheet.datavalidation import DataValidation

class FundScreener:
    def __init__(self, db: Database, base_products: list, market_list: list, delivery_dict: list, 
                 eD: dt.datetime, fcst_date: str = None, sD: dt.datetime = dt.datetime(2020, 1, 1), 
                 ns: int = 2, cont: bool = False):
        """
        Initialize FundScreener with a database connection, base products, market list, delivery options,
        and the end date (eD). Optionally, a forecast date (fcst_date) can be provided; if omitted, fcst_date
        is set equal to eD.
        """
        self.db = db
        self.eD = eD
        # If fcst_date is not provided, default to eD (formatted as a string for SQL queries)
        if fcst_date is None:
            fcst_date = eD.strftime("%Y-%m-%d")
        self.fcst_date = fcst_date
        self.futures_date = None

        self._market_list = market_list
        
        # Generate combinations for parameters
        products, markets, delivery = [], [], []
        for product in base_products:
            for market in market_list:
                for del_opt in delivery_dict:
                    products.append(product)
                    markets.append(market)
                    delivery.append(del_opt)
                    
        self.params_dict = {
            'product_list': products,
            'market_list': markets,
            'delivery_list': delivery,
            'year_list': [None] * len(markets),
            'sD': sD,
            'eD': eD,
            'ns': ns,
            'cont': cont
        }
        
        # Create forecast data instances for Gas and EUA
        self.gas_inst = input_data.Gas(self.params_dict)
        self.eua_inst = input_data.Eua(self.params_dict)
        self.tam_inst = TechAnalysis_manager(markets=market_list)
        
        # Build the product data DataFrame from the forecast instance
        self.product_data = self._create_product_data()
        
        # Placeholders for dataframes to be built later
        self.forecast_df = None
        self.futures_df = None
        self.combined_df = None
        self.settle_date = None

    @property
    def market_list(self):
        return self._market_list

    def _create_product_data(self) -> pd.DataFrame:
        """
        Build a DataFrame holding the combinations of products, markets, and delivery types.
        """
        data = {
            'product': self.gas_inst.original_params_dict['product_list'],
            'market': self.gas_inst.params_dict['market_list'],
            'del_type': self.gas_inst.params_dict['delivery_list'],
            'delivery_start': self.gas_inst.start_date_list,
            'delivery_end': self.gas_inst.end_date_list,
        }
        product_df = pd.DataFrame(data)
        product_df['delivery_start'] = pd.to_datetime(product_df['delivery_start'])
        # Adjust delivery_end by adding 1 hour and subtracting 1 second
        product_df['delivery_end'] = pd.to_datetime(product_df['delivery_end']) + dt.timedelta(hours=1, seconds=-1)
        return product_df

    @staticmethod
    def create_query(df: pd.DataFrame, query_cols=None, table='schema.table', additional_condition="") -> str:
        """
        Create an SQL query based on a DataFrame of parameters.
        """
        if query_cols is None:
            if table.split('.')[0] == 'futures':
                query_cols = ['delivery', 'delivery_start', 'delivery_end']
            else:
                query_cols = ['market', 'del_type', 'delivery_start', 'delivery_end']
        unique_rows = df[query_cols].drop_duplicates()
        values_list = [
            "(" + ", ".join(f"'{row[col]}'" for col in query_cols) + ")"
            for _, row in unique_rows.iterrows()
        ]
        values_str = ", ".join(values_list)
        columns_str = ", ".join(query_cols)
        query = f"SELECT * FROM {table} WHERE ({columns_str}) IN ({values_str})"
        if additional_condition:
            query += f" AND {additional_condition}"
        query += ";"
        return query

    @staticmethod
    def get_average_values(price_curve: pd.Series, start_dates, end_dates) -> list:
        """
        Calculate the average value from a price curve for each start/end date period.
        """
        start_dates = pd.to_datetime(start_dates)
        end_dates = pd.to_datetime(end_dates)
        averages = []
        for start, end in zip(start_dates, end_dates):
            subset = price_curve.loc[start:end]
            avg_value = round(subset.mean().iloc[0], 2)
            averages.append(avg_value)
        return averages

    @staticmethod
    def get_pivot_table(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
        """
        Create a pivot table from the given dataframe for the specified column.
        """
        pivot_df = df.pivot_table(
            index=['rel_product', 'delivery_start', 'delivery_end'],
            columns=['market', 'del_type'],
            values=value_col,
            aggfunc='first'
        )
        # Flatten the MultiIndex columns (e.g. 'de_base', 'fr_peak')
        pivot_df.columns = [f"{market}_{del_type}" for market, del_type in pivot_df.columns]
        pivot_df = pivot_df.reset_index()
        pivot_df['duration'] = (pivot_df['delivery_end'] - pivot_df['delivery_start']).dt.days
        pivot_df = pivot_df.sort_values(by=['duration', 'delivery_start']).reset_index(drop=True)
        pivot_df = pivot_df.drop(columns=['duration'])
        return pivot_df

    def load_forecast_data(self, table_name: str = 'xgboost_mean'):
        """
        Load forecast data from the database using the product_data parameters.
        """
        table_name = f'"MODEL_forecast_prices".{table_name}'
        additional_cond = f"scenario_type IN ('base_sim') AND fcst_date = '{self.fcst_date}' AND value_type = 'mean'"
        query = self.create_query(self.product_data, table=table_name, additional_condition=additional_cond)
        self.forecast_df = pd.read_sql(query, con=self.db.connection_string)
        self.forecast_df['delivery_end'] = self.forecast_df['delivery_end'].dt.normalize()
        return self.forecast_df
    
    def set_futures_date(self, futures_date):
        if not self.futures_date:  # If not set (or is falsy, e.g. None)
            self.futures_date = futures_date
        elif self.futures_date != futures_date:
            raise ValueError('Futures market date mismatch')

        
    def load_futures_data(self):
        """
        Load futures data from the database for each market in the forecast data.
        """
        if self.forecast_df is None:
            raise ValueError("Forecast data not loaded. Call load_forecast_data() first.")
        futures_list = []
        for market in self.market_list:
            # temp = self.forecast_df[self.forecast_df['market'] == market].copy()
            temp = self.forecast_df.copy()
            temp.rename(columns={'del_type': 'delivery'}, inplace=True)
            temp['delivery'] = temp['delivery'].str.capitalize()
            table_name = f"futures.{market}"
            additional_cond = f"datetime < '{self.fcst_date}'"
            query_temp = self.create_query(
                temp,
                query_cols=['delivery', 'delivery_start', 'delivery_end'],
                table=table_name,
                additional_condition=additional_cond
            )
            temp_df = pd.read_sql(query_temp, con=self.db.connection_string)
            temp_df = temp_df[['datetime', 'delivery_start', 'delivery_end', 'settlement_price', 'delivery']].copy()
            self.set_futures_date(temp_df['datetime'].max())
            temp_df = temp_df.loc[temp_df['datetime'] == self.futures_date].copy()
            temp_df['market'] = market
            futures_list.append(temp_df)
        self.futures_df = pd.concat(futures_list, axis=0)
        self.settle_date = self.futures_df['datetime'].unique()[0]
        # Rename settlement_price column to the settle date and adjust delivery naming
        self.futures_df.rename(columns={'settlement_price': self.settle_date,
                                        'delivery': 'del_type'}, inplace=True)
        self.futures_df.drop(['datetime'], axis=1, inplace=True)
        self.futures_df['del_type'] = self.futures_df['del_type'].str.lower()
        return self.futures_df
    
    @staticmethod
    # Helper function for spread leg full name
    def create_spread_leg_full_name(market, deltype, sd, prod):
        if prod.lower() in ['week']:
            tenor = sd.isocalendar().week
        elif prod.lower() in ['quarter']:
            tenor = (sd.month - 1)//3 + 1
        else:
            tenor = sd.month
        year = sd.year
        
        name_out = f"{market.upper()}_{deltype.upper()[0]}_{prod.upper()[0]}_{str(tenor)}_{str(year)[-2:]}"

        return name_out
    

    # At module level (not inside any class):
    def process_spread(self, args):
        # Unpack arguments. We pass self, spread, nominal, and n_samples.
        self, spread, nominal, n_samples = args
        market1, deltype1, sd1, ed1, prod1 = spread[0]
        market2, deltype2, sd2, ed2, prod2 = spread[1]
        l1_full_name = self.create_spread_leg_full_name(market1, deltype1, sd1, prod1)
        l2_full_name = self.create_spread_leg_full_name(market2, deltype2, sd2, prod2)
        ttf1_full_name = '_'.join(['TTF', l1_full_name.split('_', 1)[1]]).replace('_P_', '_B_')
        ttf2_full_name = '_'.join(['TTF', l2_full_name.split('_', 1)[1]]).replace('_P_', '_B_')
        eua1_full_name = '_'.join(['EUA_B_Y_1', str(sd1.year)[-2:]])
        eua2_full_name = '_'.join(['EUA_B_Y_1', str(sd2.year)[-2:]])
        
        # Retrieve spread data either by full retrieval or via sampling.
        if sd1 == sd2 and ed1 == ed2:
            spread_legs = [l1_full_name, ttf1_full_name, eua1_full_name,
                        l2_full_name, ttf2_full_name, eua2_full_name]
            if nominal:
                leg_weights = [1, -2, -0.4, -1, 2, 0.4]
                spread_df = self.tam_inst.get_historical_spot(
                                spread_legs=spread_legs,
                                leg_weights=leg_weights)
            else:
                spread_df = self.tam_inst.get_historical_spot(
                                spread_legs=spread_legs,
                                spread_operator=self.tam_inst.ghr_spread_operator)
        else:
            spread_legs1 = [l1_full_name, ttf1_full_name, eua1_full_name]
            spread_legs2 = [l2_full_name, ttf2_full_name, eua2_full_name]
            if nominal:
                leg_weights = [1, -2, -0.4]
                leg1_df = self.tam_inst.get_historical_spot(
                                spread_legs=spread_legs1,
                                leg_weights=leg_weights)
                leg2_df = self.tam_inst.get_historical_spot(
                                spread_legs=spread_legs2,
                                leg_weights=leg_weights)
            else:
                leg1_df = self.tam_inst.get_historical_spot(
                                spread_legs=spread_legs1,
                                spread_operator=self.tam_inst.ghr_operator)
                leg2_df = self.tam_inst.get_historical_spot(
                                spread_legs=spread_legs2,
                                spread_operator=self.tam_inst.ghr_operator)
            overall_samples1 = np.random.choice(leg1_df.values.flatten(), size=n_samples, replace=True)
            overall_samples2 = np.random.choice(leg2_df.values.flatten(), size=n_samples, replace=True)
            overall_spread = overall_samples1 - overall_samples2
            spread_df = pd.DataFrame({'spread_value': overall_spread})
        
        # Compute overall statistics from the "spread_value" column.
        overall_mean = spread_df['spread_value'].mean().item()
        fixed_result = [l1_full_name, l2_full_name, overall_mean]
        for percentile in [10, 25, 50, 75, 90]:
            fixed_result.append(spread_df['spread_value'].quantile(percentile / 100))
        
        # Compute per-year means.
        year_means = {}
        if sd1 == sd2 and ed1 == ed2:
            if isinstance(spread_df.index, pd.DatetimeIndex):
                unique_years = sorted(spread_df.index.year.unique())
                for y in unique_years:
                    subset = spread_df.loc[spread_df.index.year == y, 'spread_value']
                    year_means[y] = subset.mean().item() if not subset.empty else np.nan
        else:
            if isinstance(leg1_df.index, pd.DatetimeIndex):
                unique_years = sorted(leg1_df.index.year.unique())
                for y in unique_years:
                    try:
                        subset1 = leg1_df.loc[leg1_df.index.year == y].values.flatten()
                        subset2 = leg2_df.loc[leg2_df.index.year == y].values.flatten()
                    except Exception:
                        subset1 = np.array([])
                        subset2 = np.array([])
                    if len(subset1) == 0 or len(subset2) == 0:
                        year_means[y] = np.nan
                    else:
                        samples1 = np.random.choice(subset1, size=n_samples, replace=True)
                        samples2 = np.random.choice(subset2, size=n_samples, replace=True)
                        year_means[y] = (samples1 - samples2).mean()
        # Return a tuple: fixed_result and the dictionary of per-year means.
        return (fixed_result, year_means)
    
    def get_delivery_spot(self, spreads, nominal=False, n_samples=int(10e3)):
        # Load the spot data before parallelization.
        self.tam_inst.load_spot_data()

        all_results = []
        with ProcessPoolExecutor() as executor:
            args_list = [(self, spread, nominal, n_samples) for spread in spreads]
            futures = [executor.submit(self.process_spread, args) for args in args_list]
            for future in as_completed(futures):
                all_results.append(future.result())
        
        # Separate fixed statistics and per-year dictionaries.
        fixed_list = [res[0] for res in all_results]
        year_dicts = [res[1] for res in all_results]
        
        # Determine the union of all years encountered.
        all_years = set()
        for d in year_dicts:
            all_years.update(d.keys())
        sorted_years = sorted(all_years, reverse=True)
        
        # Build final rows: fixed stats plus per-year means (in sorted order).
        final_rows = []
        for fixed, year_dict in zip(fixed_list, year_dicts):
            extra = [year_dict.get(y, np.nan) for y in sorted_years]
            final_rows.append(fixed + extra)
        
        # Define column names.
        fixed_cols = ['leg1', 'leg2', 'del_mean', 'del_10th_perc', 
                    'del_25th_perc', 'del_50th_perc', 'del_75th_perc', 'del_90th_perc']
        extra_cols = [f'mean_{y}' for y in sorted_years]
        columns = fixed_cols + extra_cols
        
        all_spreads_df = round(pd.DataFrame(final_rows, columns=columns),2)
        return all_spreads_df




        

    def build_curves_and_merge(self):
        """
        Build fuel curves (Gas and EUA), merge them with futures data, calculate metrics,
        and then merge the result with forecast data.
        """
        if self.futures_df is None:
            raise ValueError("Futures data not loaded. Call load_futures_data() first.")
        
        # Build EUA curve
        self.eua_inst.set_pivot_date(self.settle_date)
        self.eua_inst.get_curve(date_shift=0)
        eua_list = self.get_average_values(
            self.eua_inst.data_curve['eua'],
            self.gas_inst.start_date_list,
            self.gas_inst.end_date_list
        )
        eua_df = pd.DataFrame({
            'delivery_start': self.gas_inst.start_date_list,
            'delivery_end': self.gas_inst.end_date_list,
            'eua': eua_list
        })
        eua_df['delivery_start'] = pd.to_datetime(eua_df['delivery_start'])
        eua_df['delivery_end'] = pd.to_datetime(eua_df['delivery_end']).dt.normalize()

        # Build Gas curve
        self.gas_inst.set_pivot_date(self.settle_date)
        self.gas_inst.get_curve(date_shift=0)
        gas_list = self.get_average_values(
            self.gas_inst.data_curve['ttf'],
            self.gas_inst.start_date_list,
            self.gas_inst.end_date_list
        )
        gas_df = pd.DataFrame({
            'delivery_start': self.gas_inst.start_date_list,
            'delivery_end': self.gas_inst.end_date_list,
            'gas': gas_list
        })
        gas_df['delivery_start'] = pd.to_datetime(gas_df['delivery_start'])
        gas_df['delivery_end'] = pd.to_datetime(gas_df['delivery_end']).dt.normalize()

        merged_futures = self.futures_df.merge(gas_df, on=['delivery_start', 'delivery_end'], how='left')
        merged_futures = merged_futures.merge(eua_df, on=['delivery_start', 'delivery_end'], how='left')
        merged_futures['ghr'] = merged_futures[self.settle_date] / (merged_futures['gas'] + merged_futures['eua'] * 0.2)
        merged_futures['css'] = merged_futures[self.settle_date] - (merged_futures['gas'] * 2 + merged_futures['eua'] * 0.4)
        
        self.combined_df = merged_futures.merge(
            self.forecast_df,
            on=['delivery_start', 'delivery_end', 'del_type', 'market'],
            how='left'
        )
        self.transform_rel_product()
        return self.combined_df
    
    def transform_rel_product(self):
        product = self.combined_df['rel_product'].str.split('_').str[0]
        new_tenor_month = np.where(product.isin(['M', 'Y']), self.combined_df['delivery_start'].dt.month,
                             np.where(product == 'Q', (self.combined_df['delivery_start'].dt.month-1)//3 + 1, None))
        new_tenor_year = self.combined_df['delivery_start'].dt.year
        # Convert new_tenor to a Series (to align indices) and cast to string.
        new_tenor_month_series = pd.Series(new_tenor_month, index=self.combined_df.index).astype(str)
        new_tenor_year_series = pd.Series(new_tenor_year, index=self.combined_df.index).astype(str).str[-2:]
        # Combine 'product' and 'new_tenor_series' using vectorized string concatenation.
        new_rel_product = product + '.' + new_tenor_month_series + new_tenor_year_series
        # Optionally, assign it back to the DataFrame:
        self.combined_df['rel_product'] = new_rel_product

    def get_pivot(self, value_col: str) -> pd.DataFrame:
        """
        Unified method to create and return a pivot table based on the specified column.
        """
        if self.combined_df is None:
            raise ValueError("Combined data not available. Call build_curves_and_merge() first.")
        pivot = self.get_pivot_table(self.combined_df, value_col)
        pivot = pivot.set_index(['rel_product', 'delivery_start', 'delivery_end'])
        return pivot
    

    def create_same_period_spreads(self, df, spread_on='delivery'):
        """
        Compute spreads (differences) between columns in df based on a matching criterion,
        then reassign a two-level MultiIndex to the resulting columns.
        
        Parameters:
        df: DataFrame with MultiIndex columns.
            Level 0: contract identifiers in the form "country_delivery" (e.g. "de_base", "fr_peak", etc.)
            Level 1: metric names (e.g. "fcst_ghr", "market_ghr", etc.)
        match_on: 
            - 'delivery': compute spreads between columns that have the same delivery part but different countries.
                        (e.g. "de_base" - "fr_base")
            - 'country': compute spreads between columns that have the same country but different delivery.
                        (e.g. "de_base" - "de_peak")
        
        Returns:
        A DataFrame of computed differences whose columns have a MultiIndex where:
            level0 is obtained by splitting the original computed column name at the first underscore,
            and level1 is the remainder.
        The columns are sorted by level0.
        """
        spread_dict = {}
        
        # Loop over all pairs of columns.
        for col1 in df.columns:
            contract1, metric1 = col1
            try:
                country1, delivery1 = contract1.split('_')
            except Exception:
                continue
            for col2 in df.columns:
                contract2, metric2 = col2
                if metric1 != metric2:
                    continue
                try:
                    country2, delivery2 = contract2.split('_')
                except Exception:
                    continue
                if spread_on == 'country':
                    # Only consider columns with the same delivery but different country.
                    if delivery1 == delivery2 and country1 < country2:
                        # Create a column name like "de-fr_base_fcst_ghr"
                        new_col = f"{country1}-{country2}_{delivery1}_{metric1}"
                        spread_dict[new_col] = df[col1] - df[col2]
                elif spread_on == 'delivery':
                    # Only consider columns with the same country but different delivery.
                    if country1 == country2 and delivery1 != delivery2:
                        # Order the deliveries so the subtraction is consistent.
                        if delivery1 < delivery2:
                            new_col = f"{country1}_{delivery1}-{delivery2}_{metric1}"
                            spread_dict[new_col] = df[col1] - df[col2]
                        else:
                            new_col = f"{country1}_{delivery2}-{delivery1}_{metric1}"
                            spread_dict[new_col] = df[col2] - df[col1]
        
        spread_df = pd.DataFrame(spread_dict)
        
        # Now convert the resulting column names into a MultiIndex.
        # We assume each column name can be split at the first underscore.
        new_columns = []
        for col in spread_df.columns:
            parts = col.split('_', 2)  # split into at most 3 parts
            if len(parts) == 3:
                level0 = parts[0] + '_' + parts[1]
                level1 = parts[2]
            else:
                # If not enough parts, fallback to the entire string as level0 and an empty level1.
                level0 = col
                level1 = ''
            new_columns.append((level0, level1))
        
        spread_df.columns = pd.MultiIndex.from_tuples(new_columns, names=['spread', 'values'])
        # Sort the columns by level0.
        spread_df = spread_df.sort_index(axis=1, level='spread')
        spread_df.reset_index(inplace=True)
        spread_df['duration'] = (spread_df['delivery_start'] - spread_df['delivery_end']).dt.days.apply(self.period_lenght_index)
        spread_df = spread_df.sort_values(['duration', 'delivery_start'], ascending=True)
        for col in ['delivery_start', 'delivery_end']:
            spread_df[col] = spread_df[col].dt.strftime('%Y-%m')
        spread_df.set_index(['rel_product', 'delivery_start', 'delivery_end'], inplace=True)        
        spread_df = spread_df.drop(['duration'], axis=1)
        spread_df = self.custom_sort_columns(spread_df, ['diff', 'market', 'fcst'])

        return spread_df
    
    def create_time_spreads(self, original_df):
        """
        Given an original DataFrame whose index is a MultiIndex with levels:
        'rel_product' (e.g. "M_1", "M_2", "Q_1", "Y_1", etc.),
        'delivery_start', and 'delivery_end',
        and which contains numeric columns (e.g. de_base, fr_base, etc.),
        build a spreads table where each row represents a pair of rows (leg1, leg2) 
        from the original DataFrame.
        
        Two kinds of pairs are produced:
        (a) Consecutive pairs within the same frequency group.
        (b) Cross-frequency pairs where a smaller frequency row is fully contained
            within a larger frequency row.
        """
        # Reset the index so that the MultiIndex levels become columns.
        df = original_df.reset_index()

        # Helper: parse rel_product (e.g. "M_1") into (freq, idx)
        def parse_rel_product(rp):
            rp = str(rp)
            parts = rp.split(".")
            if len(parts) < 2:
                raise ValueError(f"Cannot parse rel_product: {rp}")
            freq = parts[0]  # e.g., "M", "Q", "Y"
            idx = int(parts[1])
            return freq, idx

        # Build a list of row dictionaries.
        row_list = []
        # Identify numeric columns (exclude the known columns).
        numeric_cols = [c for c in df.columns if not set(c).intersection({"rel_product", "delivery_start", "delivery_end"})]
        for _, row in df.iterrows():
            rp = row["rel_product"].item()
            freq, idx = parse_rel_product(rp)
            row_list.append({
                "rel_product": rp,
                "freq": freq,
                "idx": idx,
                "delivery_start": row["delivery_start"].item(),
                "delivery_end": row["delivery_end"].item(),
                # Convert numeric columns to float
                "numeric": {c: float(row[c]) for c in numeric_cols}
            })

        # Compute a period label for each row based on frequency.
        for r in row_list:
            if r["freq"] == "M":
                r["period_label"] = r["delivery_start"].strftime('%Y-%m')
            elif r["freq"] == "Q":
                # Calculate quarter: e.g. months 1-3 -> Q1, etc.
                quarter = (r["delivery_start"].month - 1) // 3 + 1
                r["period_label"] = f"{r['delivery_start'].year}-Q{quarter}"
            elif r["freq"] == "Y":
                r["period_label"] = r["delivery_start"].strftime('%Y')
            else:
                r["period_label"] = r["delivery_start"].strftime('%Y-%m')  # fallback

        # Group rows by frequency.
        freq_map = {}
        for r in row_list:
            freq_map.setdefault(r["freq"], []).append(r)
        # Sort each group by the period label and then by delivery_start.
        for f, arr in freq_map.items():
            arr.sort(key=lambda x: (x["period_label"], x["delivery_start"]))

        spread_rows = []

        # (a) Consecutive pairs within each frequency group.
        for f, arr in freq_map.items():
            for i in range(len(arr) - 1):
                r1 = arr[i]
                r2 = arr[i+1]
                spread_rp = f"{r1['rel_product']}_{r2['rel_product']}"
                diff_values = {c: r1["numeric"].get(c, 0) - r2["numeric"].get(c, 0) for c in numeric_cols}
                spread_rows.append({
                    "rel_product": spread_rp,
                    "delivery_start_leg1": r1["delivery_start"],
                    "delivery_end_leg1": r1["delivery_end"],
                    "delivery_start_leg2": r2["delivery_start"],
                    "delivery_end_leg2": r2["delivery_end"],
                    **diff_values
                })

        # (b) Cross-frequency pairs: for each smaller frequency and larger frequency,
        # where the smaller row's period is fully contained in the larger row's period.
        def fully_contained(small, large):
            return (large["delivery_start"] <= small["delivery_start"]) and (large["delivery_end"] >= small["delivery_end"])

        # Define ordering for frequencies: assume "M" < "Q" < "Y"
        freq_order = {"M": 1, "Q": 2, "Y": 3}
        freq_list = sorted(freq_map.keys(), key=lambda x: freq_order.get(x.upper(), 99))
        for i in range(len(freq_list)):
            for j in range(i+1, len(freq_list)):
                small_f = freq_list[i]
                large_f = freq_list[j]
                for r_small in freq_map[small_f]:
                    for r_large in freq_map[large_f]:
                        if fully_contained(r_small, r_large):
                            spread_rp = f"{r_small['rel_product']}_{r_large['rel_product']}"
                            diff_values = {c: r_small["numeric"].get(c, 0) - r_large["numeric"].get(c, 0) for c in numeric_cols}
                            spread_rows.append({
                                "rel_product": spread_rp,
                                "delivery_start_leg1": r_small["delivery_start"],
                                "delivery_end_leg1": r_small["delivery_end"],
                                "delivery_start_leg2": r_large["delivery_start"],
                                "delivery_end_leg2": r_large["delivery_end"],
                                **diff_values
                            })

        # Convert the list of spread rows into a DataFrame.
        spread_df = pd.DataFrame(spread_rows)
        # Optionally, sort the DataFrame by the combined rel_product.
        spread_df['duration'] = (spread_df['delivery_start_leg1'] - spread_df['delivery_end_leg1']).dt.days.apply(self.period_lenght_index)
        spread_df = spread_df.sort_values(['duration', 'delivery_start_leg1'], ascending=True)
        for col in ['delivery_start_leg1', 'delivery_end_leg1', 'delivery_start_leg2', 'delivery_end_leg2']:
            spread_df[col] = spread_df[col].dt.strftime('%Y-%m')
        spread_df.set_index(['rel_product', 'delivery_start_leg1', 'delivery_end_leg1',
                            'delivery_start_leg2', 'delivery_end_leg2'], inplace=True)
        spread_df = spread_df.drop(['duration'], axis=1)
        spread_df.columns = pd.MultiIndex.from_tuples(spread_df.columns, names=['spread', 'value'])
        spread_df = self.custom_sort_columns(spread_df, ['diff', 'market', 'fcst'])

        return spread_df

    
    # Helper for assigning period by lenght for later sorting
    @staticmethod
    def period_lenght_index(period_lenght):
        period_lenght = abs(period_lenght)
        if period_lenght <= 7:
            return 1
        elif period_lenght <=31:
            return 2
        elif period_lenght <= 92:
            return 3
        elif period_lenght <= 366:
            return 4
    
    @staticmethod
    def create_screener_spreadsheet(master_dict,
                                template_file=r'C:\Users\krajcovic\Documents\temp\screener_template.xlsm',
                                output_file=r'C:\Users\krajcovic\Documents\temp\screener_test.xlsm',
                                extra_dfs=None,
                                extra_names=None):
        """
        Create a screener spreadsheet from a dictionary of dictionaries.
        
        master_dict: dict
            Structure: { outer_key: { inner_key: DataFrame, ... }, ... }
            For each outer_key:
            - A dynamic sheet (named outer_key) is created.
            - Its dropdown (cell A1) is populated with the inner keys only.
            - Each inner_key/DataFrame pair is saved to a hidden sheet with the name
                'outer_key_inner_key'.
            The VBA macro (pre-inserted in the template's dynamic sheet code module) should:
            - Read the dynamic sheet’s name and the dropdown (A1) value,
            - Build the target sheet name as "outer_key_inner_key", and
            - Copy data from that hidden sheet into the dynamic sheet.
            Also, if a sheet named "Dynamic" exists, it is deleted.
        
        extra_dfs: list of DataFrame, optional
            Additional DataFrames to be inserted into individual (visible) sheets.
        extra_names: list of str, optional
            Names corresponding to each extra DataFrame; each DataFrame is saved to its own sheet.
        """
        import pandas as pd
        from openpyxl import load_workbook
        from openpyxl.worksheet.datavalidation import DataValidation

        # Load the macro-enabled template, preserving the VBA project.
        wb = load_workbook(template_file, keep_vba=True)
        
        # Delete the sheet named "Dynamic", if it exists.
        if "Dynamic" in wb.sheetnames:
            wb.remove(wb["Dynamic"])
        
        # Use the openpyxl engine with keep_vba=True.
        with pd.ExcelWriter(
                output_file, 
                engine='openpyxl', 
                mode='a', 
                if_sheet_exists='overlay', 
                engine_kwargs={'keep_vba': True}
            ) as writer:
            # Workaround: assign the loaded workbook to the protected attribute _book.
            writer._book = wb

            # Process each outer group from master_dict.
            for outer_key, inner_dict in master_dict.items():
                inner_keys = ['None']  # For the dropdown, list only inner keys.
                
                # Write each inner DataFrame to a unique hidden sheet.
                for inner_key, df in inner_dict.items():
                    # Create a unique hidden sheet name: "outer_key_inner_key"
                    sheet_name = f"{outer_key}_{inner_key}"
                    inner_keys.append(inner_key)
                    df.to_excel(writer, sheet_name=sheet_name, index=True)
                    # Hide the sheet.
                    writer.book[sheet_name].sheet_state = 'hidden'
                
                # Create (or retrieve) a dynamic sheet for this outer group.
                # The dynamic sheet is named exactly as the outer key.
                dynamic_sheet_name = outer_key
                if dynamic_sheet_name in writer.book.sheetnames:
                    dynamic_sheet = writer.book[dynamic_sheet_name]
                else:
                    dynamic_sheet = writer.book.create_sheet(dynamic_sheet_name)
                
                # Add a dropdown in cell A1 listing only the inner keys.
                dv = DataValidation(
                    type="list",
                    formula1=f'"{",".join(inner_keys)}"',
                    allow_blank=True
                )
                dynamic_sheet.add_data_validation(dv)
                dv.add(dynamic_sheet["A1"])
                if inner_keys:
                    dynamic_sheet["A1"] = inner_keys[0]
                
                # Write instructions in cell A3.
                dynamic_sheet["A3"] = "Data will appear here based on dropdown selection."
                
                # IMPORTANT:
                # The VBA macro must be inserted into the code module for each dynamic sheet.
                # The macro should read the active sheet's name and the value in A1,
                # then build the target sheet name as: active sheet name & "_" & dropdown value.
                # It would then copy the contiguous data from that hidden sheet into the display area.
                # (openpyxl does not modify VBA code; ensure your template has the correct code.)
            
            # --------------------------------------------------
            # Now insert extra sheets based on extra_dfs and extra_names.
            if extra_dfs is not None and extra_names is not None:
                if len(extra_dfs) != len(extra_names):
                    raise ValueError("Length of extra_dfs and extra_names must be the same.")
                for df, sheet_name in zip(extra_dfs, extra_names):
                    # If a sheet with this name already exists, remove it.
                    if sheet_name in writer.book.sheetnames:
                        writer.book.remove(writer.book[sheet_name])
                    df.to_excel(writer, sheet_name=sheet_name, index=True)
                    # Ensure the sheet is visible.
                    writer.book[sheet_name].sheet_state = 'visible'
            
        # Save the workbook with macros intact.
        wb.save(output_file)


    @staticmethod
    def custom_sort_columns(df, order_list):
        """
        Sorts a DataFrame's MultiIndex columns by:
        1. Keeping level 0 order as they originally appear.
        2. Sorting level 1 based on a provided order_list of substrings.
            The function checks if each level 1 label contains a substring from the list.
            If a label doesn't contain any substring, it is placed at the end.
            
        Parameters:
            df (pd.DataFrame): DataFrame with MultiIndex columns.
            order_list (list): List of substrings defining the sort order for level1.
            
        Returns:
            pd.DataFrame: DataFrame with columns sorted by the custom order.
        """
        # Determine the order of appearance for level 0 keys.
        unique_level0 = []
        for col in df.columns:
            if col[0] not in unique_level0:
                unique_level0.append(col[0])
        
        sorted_cols = []
        # Process each level 0 in the order they originally appear.
        for lvl0 in unique_level0:
            # Select columns corresponding to this level 0.
            subset = [col for col in df.columns if col[0] == lvl0]
            # Sort the subset by level 1 based on whether the level1 label contains a substring from order_list.
            subset_sorted = sorted(
                subset,
                key=lambda col: next(
                    (i for i, substring in enumerate(order_list) if substring in col[1]),
                    len(order_list)
                )
            )
            sorted_cols.extend(subset_sorted)
            
        return df[sorted_cols]


    

# Example usage:
if __name__ == "__main__":
    # Set up package path if necessary
    package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')
    sys.path.insert(0, package_path)
    
    # Initialize the database connection
    db = Database()
    
    # Define the required inputs
    base_products = ['M_1', 'M_2', 'M_3', 'M_4', 'M_5','M_6',
                     'Q_1', 'Q_2', 'Q_3', 'Q_4', 'Q_5', 'Q_6', 'Q_7',
                     'Y_1', 'Y_2']
    market_list = ['de', 'fr', 'at', 'hu', 'cz']
    delivery_list = ['base', 'peak']
    eD = dt.datetime(2025, 7, 11)
    
    # Optionally specify fcst_date; if omitted, fcst_date will default to eD
    fcst_date = None
    
    # Create an instance of FundScreener
    screener = FundScreener(db, base_products, market_list, delivery_list, eD, fcst_date)
    
    # Build spreads
    spreads = build_spreads_for_screener(screener.gas_inst.start_date_list,
                                         screener.gas_inst.end_date_list,
                                         market_list,
                                         delivery_list)
    
    # Load forecast and futures data, build curves, and merge them
    screener.load_forecast_data()
    screener.load_futures_data()
    screener.build_curves_and_merge()
    
    # Get forecasted ghr values
    value_df = round(screener.get_pivot('value'),2)
    # Get market power fut, gas, eua, ghr and css values
    power_df = round(screener.get_pivot(screener.futures_date), 2)
    gas_df = round(screener.get_pivot('gas'), 2)
    eua_df = round(screener.get_pivot('eua'), 2)
    ghr_df = round(screener.get_pivot('ghr'), 2)
    css_df = round(screener.get_pivot('css'), 2)
    
    # Load forecast and futures data, build curves, and merge them
    screener.load_forecast_data(table_name='xgboost_mean_nominal')
    screener.build_curves_and_merge()
    
    # Get df for nominal difference of model from actual price
    nom_value_df = round(screener.get_pivot('value'), 2)

    # Create df for forecasted css
    value_css_df = round(nom_value_df - 2 * gas_df - 0.4 * eua_df, 2)

    # Helper function to create spread based on selected
    def get_spread_from_data(df, sd1, sd2, ed1, ed2, l1_name, l2_name, decimals=2):
        if not l1_name in df or not l2_name in df:
            return np.nan
        elif not (sd1, ed1) in df.index or not (sd2, ed2) in df.index:
            return np.nan
        else:
            return round(df.loc[(sd1,ed1), l1_name] - df.loc[(sd2, ed2), l2_name],decimals)
    

    # Assemble spreads of expected return
    total_list = []
    for spread in spreads:
        spread_list = []
        l1_raw, l2_raw = spread
        market1, deltype1, sd1, ed1, prod1 = l1_raw
        market2, deltype2, sd2, ed2, prod2 = l2_raw
        l1_name = f"{market1}_{deltype1}"
        l2_name = f"{market2}_{deltype2}"
        l1_full_name = screener.create_spread_leg_full_name(market1, deltype1, sd1, prod1)
        l2_full_name = screener.create_spread_leg_full_name(market2, deltype2, sd2, prod2)
        spread_list.extend([l1_full_name, l2_full_name])
        for df in [ghr_df, value_df, 
                   css_df, value_css_df, 
                   power_df, nom_value_df]:
            spread_list.append(get_spread_from_data(df.reset_index(level='rel_product', drop=True),
                                                    sd1, sd2, ed1, ed2, l1_name, l2_name))
        spread_list.extend([market1, market2, deltype1, deltype2,
                            prod1, prod2, sd1.year, sd2.year,
                            "_".join(l1_full_name.split('_')[2:]),
                            "_".join(l2_full_name.split('_')[2:])])
        total_list.append(spread_list)

    delivery_spot = screener.get_delivery_spot(spreads)

    columns = ['leg1', 'leg2',
               'market_ghr', 'fcst_ghr',
               'market_css','fcst_css', 
               'market_nom', 'fcst_nom',
               'market1', 'market2','deltype1', 'deltype2',
               'prod1', 'prod2', 'year1', 'year2', 'tenor1', 'tenor2']
    
    all_spreads_df = pd.DataFrame(total_list,
                             columns=columns)
    
    screen_df = all_spreads_df.merge(delivery_spot, on=['leg1', 'leg2'], how='left')

    # Compute differences
    screen_df['ghr_diff'] = round(screen_df['market_ghr'] - screen_df['fcst_ghr'], 2)
    screen_df['css_diff'] = round(screen_df['market_css'] - screen_df['fcst_css'], 2)
    screen_df['nom_diff'] = round(screen_df['market_nom'] - screen_df['fcst_nom'], 2)
    screen_df['del_diff'] = round(screen_df['market_ghr'] - screen_df['del_mean'], 2)

    # Group: Contracts
    contracts = ['leg1', 'leg2']

    # Group: Forecasts
    forecasts = [
        'ghr_diff', 'market_ghr', 'fcst_ghr',
        'css_diff', 'market_css', 'fcst_css',
        'nom_diff', 'market_nom', 'fcst_nom'
    ]

    # Group: Delivery
    delivery = ['del_diff', 'del_mean']
    # Append columns containing 'mean_20' and 'th_perc'
    delivery += [col for col in screen_df.columns if 'mean_20' in col]
    delivery += [col for col in screen_df.columns if 'th_perc' in col]

    # Group: Descriptive
    descriptive = [
        'market1', 'market2', 'year1', 'year2',
        'deltype1', 'deltype2', 'tenor1', 'tenor2',
        'prod1', 'prod2'
    ]

    # Combined ordered list of columns
    ordered_columns = contracts + forecasts + delivery + descriptive

    # Reorder DataFrame columns based on the new order
    screen_df = screen_df[ordered_columns]

    # -------------------------------
    # 2. Create MultiIndex for the columns
    # -------------------------------

    # Build the two-level tuples: (Group, Original Column)
    multi_index_tuples = (
        [( 'Contracts', col) for col in contracts] +
        [( 'Forecasts', col) for col in forecasts] +
        [( 'Delivery', col) for col in delivery] +
        [( 'Descriptive', col) for col in descriptive]
    )

    # Create a MultiIndex from the tuples and assign it to the DataFrame
    screen_df.columns = pd.MultiIndex.from_tuples(multi_index_tuples)

    # Put together outrights ghr/css/nominal market v forecast
    outright_dict = {}
    # Ghr
    ghr_df.columns = pd.MultiIndex.from_product([ghr_df.columns, ['market_ghr']])
    value_df.columns = pd.MultiIndex.from_product([value_df.columns, ['fcst_ghr']])
    ghr_data = pd.concat([ghr_df, value_df], axis=1)
    unique_level0 = ghr_data.columns.get_level_values(0).unique()
    ghr_data[pd.MultiIndex.from_product([unique_level0, ['diff']])] = (ghr_data.loc[:, ghr_data.columns.get_level_values(1).str.startswith('market_')].values
                                                                 - ghr_data.loc[:, ghr_data.columns.get_level_values(1).str.startswith('fcst_')])
    ghr_data = screener.custom_sort_columns(ghr_data, ['diff', 'market', 'fcst'])
    outright_dict['ghr'] = ghr_data
    # Css
    css_df.columns = pd.MultiIndex.from_product([css_df.columns, ['market_css']])
    value_css_df.columns = pd.MultiIndex.from_product([value_css_df.columns, ['fcst_css']])
    css_data = pd.concat([css_df, value_css_df], axis=1)
    unique_level0 = css_data.columns.get_level_values(0).unique()
    css_data[pd.MultiIndex.from_product([unique_level0, ['diff']])] = (css_data.loc[:, css_data.columns.get_level_values(1).str.startswith('market_')].values
                                                                 - css_data.loc[:, css_data.columns.get_level_values(1).str.startswith('fcst_')])
    css_data = screener.custom_sort_columns(css_data, ['diff', 'market', 'fcst'])
    outright_dict['css'] = css_data
    # Nom
    power_df.columns = pd.MultiIndex.from_product([power_df.columns, ['market_nom']])
    nom_value_df.columns = pd.MultiIndex.from_product([nom_value_df.columns, ['fcst_nom']])
    nom_data = pd.concat([power_df, nom_value_df], axis=1)
    unique_level0 = nom_data.columns.get_level_values(0).unique()
    nom_data[pd.MultiIndex.from_product([unique_level0, ['diff']])] = (nom_data.loc[:, nom_data.columns.get_level_values(1).str.startswith('market_')].values
                                                                 - nom_data.loc[:, nom_data.columns.get_level_values(1).str.startswith('fcst_')])    
    nom_data = screener.custom_sort_columns(nom_data, ['diff', 'market', 'fcst'])
    outright_dict['nominal'] = nom_data

    # # Put together basic spreads time/calendar/base_peak
    
    # Base_peak, country and time spreads defined dicts
    base_peak_spread_dict = {}
    country_spread_dict = {}
    time_spread_dict = {}
    for label, df in zip(['ghr', 'css', 'nom'],
                         [ghr_data, css_data, nom_data]):
        base_peak_spread_dict[label] = screener.create_same_period_spreads(df, spread_on='delivery')
        country_spread_dict[label] = screener.create_same_period_spreads(df, spread_on='country')
        time_spread_dict[label] = screener.create_time_spreads(df)

    master_dict = {}
    master_dict['outright_contracts'] = outright_dict
    master_dict['time_spread'] = time_spread_dict
    master_dict['country_spread'] = country_spread_dict
    master_dict['base_peak_spread'] = base_peak_spread_dict
    

    screener.create_screener_spreadsheet(master_dict=master_dict, extra_dfs=[screen_df],extra_names=['all_spreads'])
    

        
        


