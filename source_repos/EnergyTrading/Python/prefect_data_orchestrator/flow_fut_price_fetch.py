from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact


from Loaders import EikonFut_db_update as eikon_fut

@flow(timeout_seconds=600, retries=3, retry_delay_seconds=600, log_prints=True)
def fut_price_fetch(countries):
    eikon_fut.fetch_fut_data(countries)



   


