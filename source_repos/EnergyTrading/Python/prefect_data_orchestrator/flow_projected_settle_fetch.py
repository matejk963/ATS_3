from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact
from Database.DB_reader import Database
from Utilities.tech_analysis.tech_analysis_manager import TechAnalysis_manager

from Loaders import projected_settlement_db_fill

@flow(timeout_seconds=600, retries=3, retry_delay_seconds=600, log_prints=True)
def ps_db_fill(countries, base_start_date):
    with Database() as db:
        ta_inst = TechAnalysis_manager(markets=countries)
        
        for country in countries:
            print(f"Starting processing for market: {countries}")
            projected_settlement_db_fill.process_market(db, countries, base_start_date, ta_inst)
            print(f"Completed processing for market: {countries}")






