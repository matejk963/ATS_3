import pandas as pd
import numpy as np
import datetime as dt

from Utilities.tech_analysis.tech_analysis_manager import TechAnalysis_manager
from Utilities.trading_tools import screener
from Database.DB_reader import Database


def get_fetch_dates(db, market, base_start_date=dt.datetime(2019, 1, 1)):
    """
    Determine the start and end dates for fetching data.

    Args:
        db (Database): Database connection instance.
        market (str): Market identifier used in the query.
        base_start_date (datetime): Default start date if database is empty.

    Returns:
        Tuple[datetime, Timestamp]: Start date from the DB and the most recent business day as end date.
    """
    schema_name = "projected_settle"
    query = f"""
        SELECT MAX(datetime) AS latest_date
        FROM "{schema_name}"."{market}";
    """
    try:
        result = db.execute(query)
        # Assuming result is a DataFrame with a datetime column; use its first value as start date.
        start_date = result.iloc[0].dt.date.values[0]
    except Exception as e:
        print(e, "Empty database. Using default start_date.")
        start_date = base_start_date

    end_date = pd.bdate_range(end=pd.Timestamp.today(), periods=1)[0]
    return start_date, end_date


def fetch_futures_data(db, market, start_date, end_date):
    """
    Fetch futures data for the given market and date range.

    Args:
        db (Database): Database connection instance.
        market (str): Market identifier.
        start_date (datetime): Start date of the data.
        end_date (datetime): End date of the data.

    Returns:
        DataFrame: Futures data read from the database.
    """
    query = f"""
        SELECT datetime, delivery_start, delivery_end, settlement_price, delivery, product_type
        FROM "futures"."{market}"
        WHERE datetime BETWEEN '{start_date.strftime('%Y-%m-%d')}' AND '{end_date.strftime('%Y-%m-%d')}'
          AND product_type in ('Month', 'Quarter', 'Year');
    """
    data = pd.read_sql(query, con=db.connection_string).sort_values('datetime').drop_duplicates()
    return data


def prepare_contract_data(data, market):
    """
    Prepare contract metadata and create full contract names.

    Args:
        data (DataFrame): Futures data.
        market (str): Market identifier.

    Returns:
        DataFrame: Updated DataFrame with contract names.
    """
    # For non-ttf markets, filter out the 'Month' product types.
    if market not in ['ttf']:
        data = data.loc[data['product_type'] != 'Month'].copy()
    
    contract_data = data[['delivery_start', 'delivery', 'product_type']].drop_duplicates()
    contract_data['market'] = market
    contract_data = contract_data[['market', 'delivery', 'delivery_start', 'product_type']].copy()
    
    # Create full contract name using the screener tool.
    contract_data['contract'] = contract_data.apply(
        lambda row: screener.FundScreener.create_spread_leg_full_name(
            market=row['market'],
            deltype=row['delivery'],
            sd=row['delivery_start'],
            prod=row['product_type']
        ),
        axis=1
    )
    return contract_data.drop(['market'], axis=1)


def compute_projected_settlement(data, market, ta_inst):
    """
    Compute the projected settlement prices.

    Args:
        data (DataFrame): Futures data.
        market (str): Market identifier.
        ta_inst (TechAnalysis_manager): Technical analysis manager instance.

    Returns:
        DataFrame: Melted DataFrame containing computed settlement prices and related metadata.
    """
    # Merge contract metadata with the futures data.
    contract_data = prepare_contract_data(data, market)
    data = data.merge(contract_data, on=['delivery_start', 'delivery', 'product_type'], how='left')
    
    # Pivot the data so that each contract becomes a column.
    fut_data = pd.pivot_table(
        data.dropna()[['datetime', 'settlement_price', 'contract']],
        index='datetime',
        columns='contract',
        values='settlement_price'
    )
    
    contract_legs = []
    # Process each contract to compute projected settlement.
    for contract in fut_data.columns:
        df_contract = fut_data[[contract]].dropna()
        contract_temp = ta_inst._compute_projected_settlement(df_contract, do_it=True)
        # Use the latest datetime in the original data for the contract as the starting point.
        test_date = data.loc[data['contract'] == contract]['datetime'].max()
        # Filter computed data from test_date onwards (inclusive), even if test_date is not in index
        contract_temp = contract_temp.drop_duplicates().dropna()
        # contract_temp = contract_temp[contract_temp.index >= test_date].copy()
        contract_legs.append(contract_temp)
    
    # Combine all computed contract legs into one DataFrame.
    ps_data = pd.concat(contract_legs)
    if 'datetime' not in ps_data.columns:
        ps_data = ps_data.reset_index()
        ps_data.rename(columns={'index': 'datetime'}, inplace=True)
    ps_data = ps_data.reset_index().melt(
        id_vars='datetime',
        var_name='contract',
        value_name='settlement_price'
    ).sort_values('datetime')
    
    ps_data = ps_data.dropna(subset=['settlement_price']).reset_index(drop=True)
    
    # Merge the computed settlement data with additional futures information.
    ps_data = ps_data.merge(
        data[['contract', 'delivery_start', 'delivery_end', 'delivery', 'product_type']].drop_duplicates(),
        on=['contract'], how='left'
    )
    # Only keep records where the settlement date is before the delivery end.
    ps_data = ps_data.loc[ps_data['delivery_end'] >= ps_data['datetime']].copy()
    ps_data.drop(['contract'], axis=1, inplace=True)
    
    return ps_data


def process_and_save(db, market, filtered_data, stage_suffix, ta_inst):
    """
    Process the filtered data and save the resulting dataset to a staging table, then merge it to production.
    
    Args:
        db (Database): Database connection instance.
        market (str): Market identifier.
        filtered_data (DataFrame): The data filtered by product_type.
        stage_suffix (str): Suffix for staging table name (e.g. "_month" or "_non_month").
        ta_inst (TechAnalysis_manager): Technical analysis manager instance.
    """
    ps_data = compute_projected_settlement(filtered_data, market, ta_inst)
    staging_table = "stage_" + market
    ps_data.to_sql(
        name=staging_table,
        schema="projected_settle",
        con=db.connection_string,
        if_exists='replace',
        index=False
    )
    # Merge the staged data into production. Assuming the merge function supports the staging table naming.
    db.merge_from_staging_to_prod_multiple_keys("projected_settle", market, ['datetime', 'delivery_start', 'delivery_end',
                                                                             'delivery', 'product_type'])
    print(f"{market.upper()} run {stage_suffix} processed and merged.")


def process_market(db, market, base_start_date, ta_inst):
    """
    Process data for a single market.

    Args:
        db (Database): Database connection instance.
        market (str): Market identifier.
        base_start_date (datetime): Default start date.
        ta_inst (TechAnalysis_manager): Technical analysis manager instance.
    """
    # Retrieve fetch dates.
    start_date, end_date = get_fetch_dates(db, market, base_start_date)
    
    # Fetch raw futures data from the database.
    raw_data = fetch_futures_data(db, market, start_date, end_date)
    
    if market == 'ttf':
        # Process "Month" records and immediately save and merge.
        data_month = raw_data[raw_data['product_type'] == 'Month'].copy()
        if not data_month.empty:
            process_and_save(db, market, data_month, "_month", ta_inst)
        else:
            print("No 'Month' records found for ttf.")
        
        # Process non-"Month" records and then save and merge.
        data_non_month = raw_data[raw_data['product_type'] != 'Month'].copy()
        # Empty raw data to load monthly projected settlements
        ta_inst._raw_data = None
        if not data_non_month.empty:
            process_and_save(db, market, data_non_month, "_non_month", ta_inst)
        else:
            print("No non-'Month' records found for ttf.")
    else:
        # For non-ttf markets, process normally (filtering out 'Month').
        ps_data = compute_projected_settlement(raw_data, market, ta_inst)
        staging_table = "stage_" + market
        ps_data.to_sql(
            name=staging_table,
            schema="projected_settle",
            con=db.connection_string,
            if_exists='replace',
            index=False
        )
        db.merge_from_staging_to_prod_multiple_keys("projected_settle", market,['datetime', 'delivery_start', 'delivery_end',
                                                                             'delivery', 'product_type'])
        print(f"Market {market} processed successfully.")


def main():
    """
    Main routine to process futures data for all specified markets.
    """
    base_start_date = dt.datetime(2019, 1, 1)
    markets = ['at', 'be', 'cz', 'de', 'es', 'fr',
               'hu', 'it', 'nl', 'ro', 'sk', 'ttf']  # Include ttf among the markets.
    
    # Initialize the Database and Technical Analysis manager.
    db = Database()
    ta_inst = TechAnalysis_manager(markets=markets)
    
    for market in markets:
        print(f"Starting processing for market: {market}")
        process_market(db, market, base_start_date, ta_inst)
        print(f"Completed processing for market: {market}")


if __name__ == "__main__":
    main()
