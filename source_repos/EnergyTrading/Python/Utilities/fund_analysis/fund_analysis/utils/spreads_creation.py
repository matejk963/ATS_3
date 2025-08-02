import pandas as pd
import numpy as np
from Database.DB_reader import Database
from itertools import combinations
import itertools
from scipy.stats import skewnorm
import logging

logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

def add_noise_to_df(df, mean=0, std=1):
    """
    Add random noise from a normal distribution to all values in a DataFrame.

    :param df: Pandas DataFrame with numerical values.
    :param mean: Mean of the normal distribution.
    :param std: Standard deviation of the normal distribution.
    :return: DataFrame with noise added.
    """
    noise = np.random.normal(loc=mean, scale=std, size=df.shape)
    return df + pd.DataFrame(noise,columns=df.columns,index=df.index)

db = Database()

# schema_name = 'zFCST_raw_de'
# table_name = 'stage_2024-03-20'

# df = pd.read_sql(f'SELECT * FROM "{schema_name}"."{table_name}"', con=db.connection_string)
# df2 = add_noise_to_df(df.set_index('index'))

# data_dict = {pd.Timestamp('2024-03-20'):{'de':df.set_index('index')}}
# data_dict_country = {pd.Timestamp('2024-03-20'):{'de':df.set_index('index'),
#                                                 'fr': df2}}

# base_products = ['M_1', 'M_2', 'Q_1', 'Q_2']

def base_peak_mask(df_index, del_type):
    if del_type.lower() in ['peak']:
        return (df_index.weekday < 5)\
            & (df_index.hour >= 9)\
                & (df_index.hour < 21)
    elif del_type.lower() in ['peak_whole_week']:
        return (df_index.hour >= 9)\
                & (df_index.hour < 21)
    elif del_type.lower() in ['weekend']:
        return (df_index.weekday < 5)
    else:
        return np.array([True for a in df_index])
    
def fit_skewnorm_from_percentiles(percentiles):
    """ Fit a skew-normal distribution given percentiles. """
    percentiles = np.array(percentiles)  # Ensure it's a NumPy array
    
    if np.any(np.isnan(percentiles)) or np.any(np.isinf(percentiles)):
        raise ValueError(f"Invalid values in percentiles: {percentiles}")

    mean_est = np.mean(percentiles)  # Estimate mean from percentiles
    std_est = (percentiles[-1] - percentiles[0]) / 2  # Approximate std from spread

    # Prevent division by zero
    if std_est == 0 or np.isnan(std_est) or np.isinf(std_est):
        raise ValueError(f"Standard deviation is zero or invalid: {std_est}")

    # Prevent division by zero in skewness calculation
    denominator = mean_est - percentiles[0]
    if denominator == 0:
        skewness = 0  # Assume no skew if there's no spread in the lower percentiles
    else:
        skewness = (percentiles[-1] - mean_est) / denominator

    # Fit skew-normal distribution
    try:
        params = skewnorm.fit(percentiles, loc=mean_est, scale=std_est)
    except Exception as e:
        raise ValueError(f"skewnorm.fit failed with error: {e}")

    return params


def get_product_period(fcst_date, product):
        """Helper function to calculate the start and end dates for a given product."""
        if product.startswith("W_"):
            week_offset = int(product.split("_")[1])
            start_date = fcst_date + pd.DateOffset(days=(7 * week_offset) - fcst_date.weekday())
            end_date = start_date + pd.DateOffset(weeks=1) - pd.Timedelta(seconds=1)
        elif product.startswith("M_"):
            month_offset = int(product.split("_")[1])
            start_date = pd.Timestamp(fcst_date.year, fcst_date.month, 1) + pd.DateOffset(months=month_offset)
            end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(seconds=1)
        elif product.startswith("Q_"):
            quarter_offset = int(product.split("_")[1])
            quarter_month = ((fcst_date.month - 1) // 3) * 3 + 1
            start_date = pd.Timestamp(fcst_date.year, quarter_month, 1) + pd.DateOffset(months=3 * quarter_offset)
            end_date = start_date + pd.DateOffset(months=3) - pd.Timedelta(seconds=1)
        elif product.startswith("Y_"):
            year_offset = int(product.split("_")[1])
            start_date = pd.Timestamp(fcst_date.year, 1, 1) + pd.DateOffset(years=year_offset)
            end_date = start_date + pd.DateOffset(years=1) - pd.Timedelta(seconds=1)
        elif product.startswith("Wknd_"):
            weekend_offset = int(product.split("_")[1])
            saturday = fcst_date + pd.DateOffset(days=(5 - fcst_date.weekday() + 7 * weekend_offset))
            start_date = saturday
            end_date = start_date + pd.Timedelta(days=1) + pd.Timedelta(seconds=86399)  # Include Sunday
        elif product.startswith("D_"):
            day_offset = int(product.split("_")[1])
            start_date = fcst_date + pd.DateOffset(days=day_offset)
            end_date = start_date + pd.Timedelta(seconds=86399)  # End of the day
        else:
            raise ValueError(f"Unknown product type: {product}")
    
        return start_date, end_date

def get_abs_product_period(product):
    """Helper function to calculate the start and end dates for a given product."""
    parts = product.split("_")
    period_type = parts[2]  # M, Q, Y, W, Wknd
    period_num = int(parts[3])
    year = int("20" + parts[4])  # Extract year from last part

    if period_type == "M":
        start_date = pd.Timestamp(year, period_num, 1)
        end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(seconds=1)
    elif period_type == "Q":
        start_date = pd.Timestamp(year, 1 + (period_num - 1) * 3, 1)
        end_date = start_date + pd.DateOffset(months=3) - pd.Timedelta(seconds=1)
    elif period_type == "Y":
        start_date = pd.Timestamp(year, 1, 1)
        end_date = start_date + pd.DateOffset(years=1) - pd.Timedelta(seconds=1)
    elif period_type == "W":
        start_date = pd.Timestamp(year, 1, 1) + pd.DateOffset(weeks=period_num - 1)
        start_date -= pd.DateOffset(days=start_date.weekday())  # Move to Monday
        end_date = start_date + pd.DateOffset(days=6, seconds=86399)  # End of Sunday
    elif period_type == "Wknd":
        start_date = pd.Timestamp(year, 1, 1) + pd.DateOffset(weeks=period_num - 1)
        start_date += pd.DateOffset(days=(5 - start_date.weekday()))  # Move to Saturday
        end_date = start_date + pd.DateOffset(days=1, seconds=86399)  # End of Sunday
    else:
        raise ValueError(f"Unknown product type: {product}")

    return start_date, end_date
            
def get_columns(df_columns):
    columns_dict = {
            'base_col': ['base'],
            'base_sim': [f'ExtDataSim_{int(a)}' for a in range(1, 101)],
            'mean_av_cap' : ['mean'],
            'base_sim_mean_av_cap': [a for a in df_columns if ('ExtDataSim' in a and 'mean' in a)],
            # 'base_mcr': ['mcr_-1_std', 'mcr_1_std'],
            # 'base_avcap': ['AvailableCapacityData_10th', 'AvailableCapacityData_mean', 'AvailableCapacityData_90th'],
            # 'mcr_lower_sim': [a for a in df_columns if ('ExtDataSim' in a and 'mcr_-1_std' in a)],
            # 'mcr_upper_sim': [a for a in df_columns if ('ExtDataSim' in a and 'mcr_1_std' in a)],
            # 'avcap_lower_sim': [a for a in df_columns if ('ExtDataSim' in a and 'AvailableCapacityData_10th' in a)],
            # 'avcap_mean_sim': [a for a in df_columns if ('ExtDataSim' in a and 'AvailableCapacityData_mean' in a)],
            # 'avcap_upper_sim': [a for a in df_columns if ('ExtDataSim' in a and 'AvailableCapacityData_90th' in a)],
            'perc_col': [a for a in df_columns if '_perc' in a and '_perc_' not in a]
        }
    return columns_dict



def get_outright_prices(
    data_dict,
    base_products
    ):

    out_dfs_list = []
    for fcst_date, fcst_date_dict in data_dict.items():
        for market, market_df in fcst_date_dict.items():
            for scenario_type, selected_columns in get_columns(market_df.columns).items():
                scen_df = market_df[selected_columns].copy()
                for del_type in ['base', 'peak']:
                    del_df = scen_df.loc[base_peak_mask(scen_df.index,
                                                        del_type)].copy()
                    for product in base_products:
                        start_date, end_date = get_product_period(fcst_date,
                                                                    product)
                        prod_df = del_df.loc[start_date:end_date].copy()
                        if '_sim' in scenario_type:
                            df = pd.DataFrame.from_dict({'value':{
                                "mean": prod_df.mean(axis=1).mean(),
                                "10th": prod_df.quantile(0.1, axis=1).mean(),
                                "25th": prod_df.quantile(0.25, axis=1).mean(),
                                "50th": prod_df.quantile(0.5, axis=1).mean(),
                                "75th": prod_df.quantile(0.75, axis=1).mean(),
                                "90th": prod_df.quantile(0.9, axis=1).mean()
                            }}, orient='columns')
                            df.index.name = 'value_type'
                            df.reset_index(inplace=True)
                            df.index = [product for a in range(len(df.index))]
                        else:
                            df = prod_df.mean(axis=0).to_frame()
                            df.columns = ['value']
                            df.index.name = 'value_type'
                            df.reset_index(inplace=True)
                            df.index = [product for a in range(len(df.index))]
                        # for id_col, id_value in zip(['fcst_type', 'fcst_date', 'market',' market_2', 'scenario_type', 'del_type',
                        #                             'delivery_start', 'delivery_end', 'delivery_start_2', 'delivery_end_2'],
                        #                             ['outright_price', fcst_date, market, None,  scenario_type, del_type,
                        #                             start_date, end_date, None, None]):
                        #     df[id_col] = id_value
                        for id_col, id_value in zip(['fcst_type', 'fcst_date', 'market', 'scenario_type', 'del_type',
                                                    'delivery_start', 'delivery_end'],
                                                    ['outright_price', fcst_date, market,  scenario_type, del_type,
                                                    start_date, end_date]):
                            df[id_col] = id_value
                        
                        out_dfs_list.append(df)
    out_df = pd.concat(out_dfs_list)
    out_df.index.name = 'rel_product'
    out_df.reset_index(inplace=True)
    return out_df

def get_outright_prices_old(
    data_dict,
    base_products
    ):
    
    out_dfs_list = []
    for fcst_date, fcst_date_dict in data_dict.items():
        for market, market_df in fcst_date_dict.items():
            for scenario_type, selected_columns in get_columns(market_df.columns).items():
                scen_df = market_df[selected_columns].copy()
                for del_type in ['base', 'peak']:
                    del_df = scen_df.loc[base_peak_mask(scen_df.index,
                                                        del_type)].copy()
                    for product in base_products:
                        start_date, end_date = get_product_period(fcst_date,
                                                                    product)
                        prod_df = del_df.loc[start_date:end_date].copy()
                        if '_sim' in scenario_type:
                            df = pd.DataFrame.from_dict({product:{
                                "mean": prod_df.mean(axis=1).mean(),
                                "10th": prod_df.quantile(0.1, axis=1).mean(),
                                "25th": prod_df.quantile(0.25, axis=1).mean(),
                                "50th": prod_df.quantile(0.5, axis=1).mean(),
                                "75th": prod_df.quantile(0.75, axis=1).mean(),
                                "90th": prod_df.quantile(0.9, axis=1).mean()
                            }}, orient='index')
                        else:
                            df = prod_df.mean(axis=0).to_frame().T
                            df.index = [product]
                        for id_col, id_value in zip(['fcst_type', 'fcst_date', 'market',' market_2', 'scenario_type', 'del_type',
                                                    'delivery_start', 'delivery_end', 'delivery_start_2', 'delivery_end_2'],
                                                    ['outright_price', fcst_date, market, None,  scenario_type, del_type,
                                                    start_date, end_date, None, None]):
                            df[id_col] = id_value
                        
                        out_dfs_list.append(df)
    out_df = pd.concat(out_dfs_list)
    out_df.index.name = 'rel_product'
    out_df.reset_index(inplace=True)
    return out_df

def get_country_spreads(data_dict, base_products):
    out_dfs_list = []
    
    for fcst_date, countries_data in data_dict.items():
        country_keys = list(countries_data.keys())
        country_pairs = list(itertools.combinations(country_keys, 2))  # Get all unique pairs of countries
        
        for (country_1, country_2) in country_pairs:
            df_1 = countries_data[country_1]
            df_2 = countries_data[country_2]
            spread_df = df_1 - df_2
            for scenario_type, columns in get_columns(spread_df.columns).items():
                scen_df = spread_df[columns].copy()                
                for del_type in ['base', 'peak']:
                    del_df = scen_df.loc[base_peak_mask(scen_df.index,
                                                        del_type)].copy()
                    
                    for product in base_products:
                        start_date, end_date = get_product_period(fcst_date,
                                                                    product)
                        prod_df = del_df.loc[start_date:end_date].copy()
                        
                        if '_sim' in scenario_type:
                            df = pd.DataFrame.from_dict({product: {
                                "mean": prod_df.mean(axis=1).mean(),
                                "10th": prod_df.quantile(0.1, axis=1).mean(),
                                "25th": prod_df.quantile(0.25, axis=1).mean(),
                                "50th": prod_df.quantile(0.5, axis=1).mean(),
                                "75th": prod_df.quantile(0.75, axis=1).mean(),
                                "90th": prod_df.quantile(0.9, axis=1).mean()
                            }}, orient='index')
                        else:
                            df = prod_df.mean(axis=0).to_frame().T
                            df.index = [product]
                        
                        for id_col, id_value in zip(['fcst_type', 'fcst_date', 'market', 'market_2', 'scenario_type', 'del_type',
                                                    'delivery_start', 'delivery_end', 'delivery_start_2', 'delivery_end_2'],
                                                    ['country_spread', fcst_date, country_1, country_2, scenario_type, del_type,
                                                    start_date, end_date, None, None]):
                            df[id_col] = id_value
                        
                        out_dfs_list.append(df)
    
    out_df = pd.concat(out_dfs_list)
    out_df.index.name = 'rel_product'
    out_df.reset_index(inplace=True)
    return out_df

def get_capa_spreads(data_dict, base_products):
    out_dfs_list = []
    
    for fcst_date, countries_data in data_dict.items():
        country_keys = list(countries_data.keys())
        country_pairs = list(itertools.permutations(country_keys, 2))  # Get all unique pairs of countries
        
        for (country_1, country_2) in country_pairs:
            df_1 = countries_data[country_1]
            df_2 = countries_data[country_2]
            spread_df = pd.DataFrame(np.where(df_1 - df_2 < 0, 0, df_1 - df_2),
                                    columns=df_1.columns, index=df_1.index)
            for scenario_type, columns in get_columns(spread_df.columns).items():
                scen_df = spread_df[columns].copy()                
                for del_type in ['base', 'peak']:
                    del_df = scen_df.loc[base_peak_mask(scen_df.index,
                                                        del_type)].copy()
                    
                    for product in base_products:
                        start_date, end_date = get_product_period(fcst_date,
                                                                    product)
                        prod_df = del_df.loc[start_date:end_date].copy()
                        
                        if '_sim' in scenario_type:
                            df = pd.DataFrame.from_dict({product: {
                                "mean": prod_df.mean(axis=1).mean(),
                                "10th": prod_df.quantile(0.1, axis=1).mean(),
                                "25th": prod_df.quantile(0.25, axis=1).mean(),
                                "50th": prod_df.quantile(0.5, axis=1).mean(),
                                "75th": prod_df.quantile(0.75, axis=1).mean(),
                                "90th": prod_df.quantile(0.9, axis=1).mean()
                            }}, orient='index')
                        else:
                            df = prod_df.mean(axis=0).to_frame().T
                            df.index = [product]
                        
                        for id_col, id_value in zip(['fcst_type', 'fcst_date', 'market', 'market_2', 'scenario_type', 'del_type',
                                                    'delivery_start', 'delivery_end', 'delivery_start_2', 'delivery_end_2'],
                                                    ['capa_spread', fcst_date, country_1, country_2, scenario_type, del_type,
                                                    start_date, end_date, None, None]):
                            df[id_col] = id_value
                        
                        out_dfs_list.append(df)
    
    out_df = pd.concat(out_dfs_list)
    out_df.index.name = 'rel_product'
    out_df.reset_index(inplace=True)
    return out_df

def get_period_spreads(data_dict, base_products):
    
    def infer_period_type(start, end, del_type):
        """Determine the period type (Day, Week, Month, Quarter, Year) based on the difference."""
        start, end = pd.to_datetime(start), pd.to_datetime(end)
        
        delta_days = (end - start).days + 1  # Inclusive difference
        
        if delta_days == 1:
            return 'D'  # Day
        elif delta_days == 2:
            return 'Wknd'
        elif delta_days <= 7:
            return 'W'  # Week
        elif delta_days < 32:  # Monthly assumption
            return 'M'
        elif delta_days < 92:  # Quarterly assumption
            return 'Q'
        elif delta_days < 370:  # Yearly assumption
            return 'Y'
        
        return 'Unknown'  # Fallback case

    def is_valid_pair(prod1_start, prod1_end, prod2_start, prod2_end, del_type):
        """Check if (prod1_start, prod1_end) and (prod2_start, prod2_end) form a valid pair."""
        
        prod1_start, prod1_end = pd.to_datetime(prod1_start), pd.to_datetime(prod1_end)
        prod2_start, prod2_end = pd.to_datetime(prod2_start), pd.to_datetime(prod2_end)
        
        # Determine the period type
        period_type = infer_period_type(prod1_start, prod1_end, del_type)
        
        # 1. Same period
        if (prod1_start == prod2_start) and (prod1_end == prod2_end):
            return True

        # 2. Consecutive periods based on period type
        if del_type == 'peak':  
            # Use business days
            next_period_start = prod1_start + pd.offsets.BDay((prod1_end - prod1_start).days + 1)
        else:
            # Use calendar days
            if period_type == 'D':
                next_period_start = prod1_start + pd.Timedelta(days=1)
            elif period_type == 'W':
                next_period_start = prod1_start + pd.Timedelta(weeks=1)
            elif period_type == 'M':
                next_period_start = prod1_start + pd.DateOffset(months=1)
            elif period_type == 'Q':
                next_period_start = prod1_start + pd.DateOffset(months=3)
            elif period_type == 'Y':
                next_period_start = prod1_start + pd.DateOffset(years=1)
            else:
                next_period_start = None

        if next_period_start and next_period_start == prod2_start:
            return True

        # 3. One period fully within another
        if (prod1_start >= prod2_start and prod1_end <= prod2_end) or (prod2_start >= prod1_start and prod2_end <= prod1_end):
            return True

        # 4. Week-based conditions
        if period_type == 'W':
            # If prod1 is a week, then prod2 should be front month (M_1) or second front month (M_2)
            prod2_month = prod2_start.to_period("M")
            front_month = prod1_start.to_period("M")
            second_front_month = front_month + 1
            
            if prod2_month in [front_month, second_front_month]:
                return True

        return False  # If none of the conditions match, it's invalid

    out_dfs_list = []
    
    for fcst_date, countries_data in data_dict.items():
        for country, country_df in countries_data.items():
            for scenario_type, columns in get_columns(country_df.columns).items():
                scen_df = country_df[columns].copy()
                
                for del_type in ['base', 'peak']:
                    scen_df = scen_df.loc[base_peak_mask(scen_df.index, del_type)]
                    
                    for i, product1 in enumerate(base_products):
                        for product2 in base_products[i + 1:]:
                            prod1_start, prod1_end = get_product_period(fcst_date,
                                                                    product1)
                            prod2_start, prod2_end = get_product_period(fcst_date,
                                                                    product2)
                            if not is_valid_pair(prod1_start, prod1_end, prod2_start, prod2_end, del_type):
                                continue
                            prod1_df = scen_df.loc[prod1_start:prod1_end].copy()
                            prod2_df = scen_df.loc[prod2_start:prod2_end].copy()
                            spread_name = f"{product1}_{product2}"
                            
                            if '_sim' in scenario_type:
                                # Compute percentiles from 1% to 99% for each product
                                perc_list = []
                                for temp in [prod1_df, prod2_df]:
                                    df_list = [temp.quantile(percentile / 100, axis=1).mean() for percentile in range(1, 100)]
                                    perc_list.append(df_list)

                                # Create a 100x100 matrix of spreads (subtractions)
                                spread_matrix = np.subtract.outer(perc_list[0], perc_list[1]).flatten()

                                # Compute requested statistics from the spread distribution
                                spread_statistics = {spread_name:{
                                    "mean": np.mean(spread_matrix),
                                    "10th": np.percentile(spread_matrix, 10),
                                    "25th": np.percentile(spread_matrix, 25),
                                    "50th": np.percentile(spread_matrix, 50),
                                    "75th": np.percentile(spread_matrix, 75),
                                    "90th": np.percentile(spread_matrix, 90),
                                }}

                                # Convert to DataFrame for easy handling
                                df = pd.DataFrame.from_dict(spread_statistics,orient='index')
                            elif scenario_type in ['perc_col']:
                                prod1_mean = prod1_df.mean().values
                                prod2_mean = prod2_df.mean().values
                                # Check if you have data
                                prod_nan_check = check_prod_means(prod1_mean, prod2_mean, country, product1, product2, scenario_type)
                                if prod_nan_check:
                                    logging.warning(prod_nan_check)
                                    continue
                                # Fit skew-normal distributions
                                prod1_params = fit_skewnorm_from_percentiles(prod1_mean)
                                prod2_params = fit_skewnorm_from_percentiles(prod2_mean)

                                # Generate synthetic samples from fitted distributions
                                num_samples = 100000
                                prod1_samples = skewnorm.rvs(*prod1_params, size=num_samples)
                                prod2_samples = skewnorm.rvs(*prod2_params, size=num_samples)

                                # Compute the spread (difference of the two distributions)
                                spread_samples = prod1_samples - prod2_samples

                                # Compute percentiles from the spread distribution
                                spread_statistics = {spread_name:{
                                    "mean": np.mean(spread_samples),
                                    "10th": np.percentile(spread_samples, 10),
                                    "25th": np.percentile(spread_samples, 25),
                                    "50th": np.percentile(spread_samples, 50),  # Median
                                    "75th": np.percentile(spread_samples, 75),
                                    "90th": np.percentile(spread_samples, 90),
                                }}
                                
                                df = pd.DataFrame.from_dict(spread_statistics,orient='index')

                            else:
                                df = (prod1_df.mean() - prod2_df.mean()).to_frame().T
                                df.index = [spread_name]
                            
                            for id_col, id_value in zip(['fcst_type', 'fcst_date', 'market', 'market_2', 'scenario_type', 'del_type',
                                                            'delivery_start', 'delivery_end', 'delivery_start_2', 'delivery_end_2'],
                                                        ['calendar_spread', fcst_date, country, None, scenario_type, del_type,
                                                        prod1_start, prod1_end, prod2_start, prod2_end]):
                                df[id_col] = id_value
                            
                            out_dfs_list.append(df)
    
    out_df = pd.concat(out_dfs_list)
    out_df.index.name = 'rel_product'
    out_df.reset_index(inplace=True)
    return out_df

def get_base_peak_spreads(
    data_dict,
    base_products
    ):
    
    out_dfs_list = []
    for fcst_date, fcst_date_dict in data_dict.items():
        for market, market_df in fcst_date_dict.items():
            for scenario_type, selected_columns in get_columns(market_df.columns).items():
                scen_df = market_df[selected_columns].copy()
                for product in base_products:
                    start_date, end_date = get_product_period(fcst_date,
                                                                product)
                    prod1_df = scen_df.loc[base_peak_mask(scen_df.index,
                                                            'base')].loc[start_date:end_date].copy()
                    prod2_df = scen_df.loc[base_peak_mask(scen_df.index,
                                                            'peak')].loc[start_date:end_date].copy()
                    spread_name = product
                    
                    if '_sim' in scenario_type:
                        # Compute percentiles from 1% to 99% for each product
                        perc_list = []
                        for temp in [prod1_df, prod2_df]:
                            df_list = [temp.quantile(percentile / 100, axis=1).mean() for percentile in range(1, 100)]
                            perc_list.append(df_list)

                        # Create a 100x100 matrix of spreads (subtractions)
                        spread_matrix = np.subtract.outer(perc_list[0], perc_list[1]).flatten()

                        # Compute requested statistics from the spread distribution
                        spread_statistics = {spread_name:{
                            "mean": np.mean(spread_matrix),
                            "10th": np.percentile(spread_matrix, 10),
                            "25th": np.percentile(spread_matrix, 25),
                            "50th": np.percentile(spread_matrix, 50),
                            "75th": np.percentile(spread_matrix, 75),
                            "90th": np.percentile(spread_matrix, 90),
                        }}

                        # Convert to DataFrame for easy handling
                        df = pd.DataFrame.from_dict(spread_statistics,orient='index')
                    elif scenario_type in ['perc_col']:
                        prod1_mean = prod1_df.mean()
                        prod2_mean = prod2_df.mean()
                        prod_nan_check = check_prod_means(prod1_mean, prod2_mean, market, f"{product}_base", f"{product}_peak", scenario_type)
                        if prod_nan_check:
                            logging.warning(prod_nan_check)
                            continue
                        # Fit skew-normal distributions
                        prod1_params = fit_skewnorm_from_percentiles(prod1_mean)
                        prod2_params = fit_skewnorm_from_percentiles(prod2_mean)

                        # Generate synthetic samples from fitted distributions
                        num_samples = 100000
                        prod1_samples = skewnorm.rvs(*prod1_params, size=num_samples)
                        prod2_samples = skewnorm.rvs(*prod2_params, size=num_samples)

                        # Compute the spread (difference of the two distributions)
                        spread_samples = prod1_samples - prod2_samples

                        # Compute percentiles from the spread distribution
                        spread_statistics = {spread_name:{
                            "mean": np.mean(spread_samples),
                            "10th": np.percentile(spread_samples, 10),
                            "25th": np.percentile(spread_samples, 25),
                            "50th": np.percentile(spread_samples, 50),  # Median
                            "75th": np.percentile(spread_samples, 75),
                            "90th": np.percentile(spread_samples, 90),
                        }}                        
                        df = pd.DataFrame.from_dict(spread_statistics,orient='index')
                    else:
                        df = pd.DataFrame([(prod1_df.mean() - prod2_df.mean())]).rename_axis(index=spread_name)
                    
                    for id_col, id_value in zip(['fcst_type', 'fcst_date', 'market', 'market_2', 'scenario_type', 'del_type',
                                                    'delivery_start', 'delivery_end', 'delivery_start_2', 'delivery_end_2'],
                                                ['b_p_spread', fcst_date, market, None, scenario_type, 'base_peak',
                                                start_date, end_date, None, None]):
                        df[id_col] = id_value
                    
                    out_dfs_list.append(df)
    out_df = pd.concat(out_dfs_list)
    out_df.index.name = 'rel_product'
    out_df.reset_index(inplace=True)
    return out_df

def check_prod_means(prod1_mean, prod2_mean, country, product1, product2, scenario_type):
    """Check if prod1_mean or prod2_mean contains NaN or inf values and return a formatted message."""
    issues = []
    
    if np.any(np.isnan(prod1_mean)):
        issues.append(f"{country}_{product1} in {scenario_type} has NaN values")
    if np.any(np.isinf(prod1_mean)):
        issues.append(f"{country}_{product1} in {scenario_type} has Inf values")
    
    if np.any(np.isnan(prod2_mean)):
        issues.append(f"{country}_{product2} in {scenario_type} has NaN values")
    if np.any(np.isinf(prod2_mean)):
        issues.append(f"{country}_{product2} in {scenario_type} has Inf values")
    
    if issues:
        return " | ".join(issues)
    
    return None  # Return None if no issues
    
def create_spreads(prediction_dict,
                base_products,
                table_name: str,
                spread_type_list: list = None):
    db = Database()
    method_mapping = {
            "country_spreads": {
                "method": get_country_spreads,
                "params": ["curve_pred", "base_products", "columns_dict"],
            },
            "calendar_spreads": {
                "method": get_period_spreads,
                "params": ["curve_pred", "base_products", "columns_dict"],
            },
            "b_p_spreads": {
                "method": get_base_peak_spreads,
                "params": ["curve_pred", "base_products", "columns_dict"],
            },
            "capa_spreads": {
                "method": get_capa_spreads,
                "params": ["curve_pred", "base_products", "columns_dict"],
            },
            "outright_prices": {
                "method": get_outright_prices,
                "params": ["curve_pred", "base_products", "columns_dict"],
            }
            
        }
    if spread_type_list is None:
        spread_type_list = list(method_mapping.keys())
    params = [prediction_dict, base_products]
    schema_name = 'MODEL_forecast_prices'
    for spread_type, spread_config in method_mapping.items():
        if spread_type in spread_type_list:
            df = spread_config['method'](*params)
            df.to_sql(name=f"stage_{table_name}",
                                schema=schema_name,
                                con=db.connection_string,
                                if_exists='replace', index=False)
            db.merge_from_staging_to_prod_multiple_keys(schema_name,
                                        table_name,
                                        ['rel_product', 'fcst_date', 'market',
                                          'del_type', 'delivery_start', 'delivery_end'])
            # db.merge_from_staging_to_prod(schema_name,
            #                             table_name)
            
    