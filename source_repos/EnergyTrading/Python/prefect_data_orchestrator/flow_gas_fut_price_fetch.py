from prefect import flow


from Loaders import fut_gas_price_fetch as fgpf

@flow(timeout_seconds=600, retries=3, retry_delay_seconds=600, log_prints=True)
def gas_fut_price_fetch(countries, base_date):
    for country in countries:
        fgpf.insert_files_to_db(country, base_date)



   


