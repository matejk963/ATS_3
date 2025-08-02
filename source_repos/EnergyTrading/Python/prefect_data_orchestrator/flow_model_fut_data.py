from prefect import flow, task, get_run_logger
from Utilities.fund_analysis.fund_analysis.updates import update_coal_prices, update_eua_prices, update_ttf_prices
import datetime as dt


@task(timeout_seconds=600, retries=3, retry_delay_seconds=300, log_prints=True)
def update_futures_data():
    """Updates TTF gas, EUA, and coal futures prices in the database."""
    logger = get_run_logger()
    logger.info("🚀 Starting futures prices update...")

    base_date = dt.datetime(2019, 1, 1)
    fut_periods = 60

    # ✅ Update Gas Data
    logger.info("Updating TTF gas futures prices...")
    update_ttf_prices.gas_data_to_db(base_date=base_date, fut_periods=fut_periods)
    update_ttf_prices.gas_da_df(base_date=base_date)
    logger.info("✅ TTF gas data updated successfully.")

    # ✅ Update EUA Data
    logger.info("Updating EUA futures prices...")
    update_eua_prices.eua_data_to_db(base_date=base_date, fut_periods=fut_periods)
    logger.info("✅ EUA futures data updated successfully.")

    # ✅ Update Coal Data
    logger.info("Updating coal futures prices...")
    update_coal_prices.coal_data_to_db(base_date=base_date, fut_periods=fut_periods)
    logger.info("✅ Coal futures data updated successfully.")

    logger.info("✅ All futures data updated successfully!")


@flow(timeout_seconds=1800, retries=1, retry_delay_seconds=600, log_prints=True)
def update_all_futures_flow():
    """Unified Prefect flow to update all futures prices."""
    logger = get_run_logger()
    logger.info("🔄 Running the unified futures update flow...")
    
    update_futures_data()

    logger.info("✅ Flow execution completed.")


if __name__ == "__main__":
    update_all_futures_flow()
