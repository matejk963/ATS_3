from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact
import datetime as dt


from Loaders import fund_fetch as ff

@flow(timeout_seconds=300, retries=3, retry_delay_seconds=300, log_prints=True, )
def fund_fetch(fund_list, grid_list, hour):
    from_ = dt.datetime.now().date()
    ff.fetch_fund_ftp(fund_list=fund_list,
                        grid_list=grid_list,
                        hour=hour,
                        from_=from_)



   


