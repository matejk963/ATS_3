from prefect import flow
import datetime as dt
import pandas as pd
from Loaders.EikonSpot_class import EikonSpot
from Database.DB_reader import Database


@flow(timeout_seconds=600, retries=3, retry_delay_seconds=300, log_prints=True)
def eikon_spot_fetch(countries, start_date, end_date=None):
    if not end_date:
        end_date=(pd.Timestamp.today().normalize() + dt.timedelta(days=1))
    """
    Fetches spot market data for given countries and stores it in the database.
    """
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)

    print(f"Starting flow: Fetching Eikon spot data from {start_date} to {end_date}")

    for country in countries:
        print(f"Processing country: {country}")

        # Check if table exists in the database
        table_exists_query = f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'spot' 
                AND table_name = '{country}'
            );
        """
        try:
            with Database() as db_r:
                table_exists_result = pd.read_sql(table_exists_query, db_r.connection_string)
            if table_exists_result.empty:
                print(f"⚠️ Table check for {country} returned empty, assuming table does not exist.")
                table_exists = False
            else:
                table_exists = table_exists_result.iloc[0, 0]
        except Exception as e:
            print(f"❌ Error checking table existence for {country}: {e}")
            continue

        # Determine last available date in the database
        if not table_exists:
            last_date = pd.Timestamp(start_date).normalize()
            print(f"Table {country} does not exist. Setting last_date to {last_date}.")
        else:
            last_date_query = f"""
                SELECT MAX("datetime") 
                FROM "spot".{str(country)};
            """
            try:
                with Database() as db_r:
                    last_date_result = pd.read_sql(last_date_query, db_r.connection_string)
                last_date = pd.Timestamp(last_date_result.iloc[0, 0]).normalize() if not last_date_result.empty else pd.Timestamp(start_date).normalize()
                print(f"Last available data for {country}: {last_date}")
            except Exception as e:
                print(f"❌ Error fetching last date for {country}: {e}")
                continue

        # Fetch new data if last_date < end_date
        if last_date < end_date:
            print(f"Fetching new data for {country} from {last_date - dt.timedelta(days=2)} to {end_date + dt.timedelta(days=2)}")
            aux_inst = EikonSpot(country, last_date - dt.timedelta(days=2), end_date + dt.timedelta(days=2))
            try:
                aux = aux_inst.spot_data()
                if aux.empty:
                    print(f"⚠️ No data returned for {country}. Skipping.")
                    continue
            except Exception as e:
                print(f"❌ Error fetching data for {country}: {e}")
                continue

            if country in ['gr']:
                aux.index = aux.index - dt.timedelta(days=1)

            df = aux[
                ((aux.index >= (last_date + dt.timedelta(days=1))) &
                 (aux.index < (end_date + dt.timedelta(days=1))))
            ].copy()

            if df.empty:
                print(f"⚠️ No new records to insert for {country}. Skipping.")
                continue

            df = df.reset_index()
            df['check'] = (df['datetime'] - df['datetime'].shift(1)).dt.seconds / 3600
            aux_check = df.loc[df['check'] != 1.].copy()

            df = df.sort_values('datetime').drop_duplicates('datetime', keep='first')
            df = df.set_index('datetime').copy()
            df = df.resample('h').mean().fillna(0).reset_index()
            df = df.drop(['check'], axis=1)

            # Insert into stage table
            try:
                with Database() as db_r:
                    df.to_sql(name="stage_" + country, schema='spot', con=db_r.connection_string,
                              if_exists='replace', index=False)
                print(f"✅ Data for {country} written to stage table successfully. Records: {len(df)}")
            except Exception as e:
                print(f"❌ Error writing to stage_{country}: {e}")
                continue

            # Merge into production table
            try:
                with Database() as db_r:
                    db_r.merge_from_staging_to_prod_enum(schema='spot', table=country)
                print(f"✅ Merge for {country} completed successfully.")
            except Exception as e:
                print(f"❌ Error merging data for {country}: {e}")
                continue

    print("✅ Flow execution completed.")


if __name__ == '__main__':
    eikon_spot_fetch(
        countries=['hr', 'it', 'it_nord', 'gr', 'es'],
        start_date=dt.datetime(2019, 1, 1)
    )
