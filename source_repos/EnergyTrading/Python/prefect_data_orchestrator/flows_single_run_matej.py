import sys
import os
import json
from datetime import datetime

# Load configuration
from Common.config_load import get_config_path as CONFIG_PATH

with open(CONFIG_PATH(), 'r') as file:
    config = json.load(file)['PrefectPostgres']
prefect_postgres_pass = config['matej']

os.environ["PREFECT_API_DATABASE_CONNECTION_URL"] = (
    f"postgresql+asyncpg://prefect_user:{prefect_postgres_pass}@localhost:5432/prefect"
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

OUTAGE_FETCH_PATH = os.path.join(PROJECT_ROOT, "Utilities", "entso_data", "AvailCap")
sys.path.insert(0, OUTAGE_FETCH_PATH)
print(f"✅ Added {OUTAGE_FETCH_PATH} to sys.path for module lookup.")

sys.path.insert(0, SCRIPT_DIR)
print(f"📂 Added {SCRIPT_DIR} to sys.path for module lookup.")

try:
    from flow_fut_price_fetch import fut_price_fetch
    from flow_fund_fetch import fund_fetch
    from flow_eikon_spot import eikon_spot_fetch
    from flow_av_inst_cap_fetch import entsoe_inst_cap_flow
    from flow_ensto_av_cap_fetch import entsoe_av_cap_flow  # Check if this should be entsoe
    from flow_model_fut_data import update_all_futures_flow
    from flow_fund_model_run import fund_model_run
    from flow_projected_settle_fetch import ps_db_fill
except ModuleNotFoundError as e:
    print(f"❌ ERROR: Missing module: {e}. Ensure all flow files are in the same directory.")
    exit(1)

def run_all_flows():
    print("Starting execution of all flows sequentially...\n")

    print("▶ Running eikon_spot_fetch...")
    try:
        eikon_spot_fetch(countries=['it', 'it_nord', 'es', 'hr', 'gr'],
                         start_date=datetime(2019, 1, 1))
    except Exception as e:
        print(f"❌ Error running eikon_spot_fetch: {e}")
    print()

    print("▶ Running fund_fetch (mid-00)...")
    try:
        fund_fetch(
            fund_list=['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
            grid_list=['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
            hour='00'
        )
    except Exception as e:
        print(f"❌ Error running fund_fetch (mid-00): {e}")
    print()

    print("▶ Running fund_fetch (mid-perc-00)...")
    try:
        fund_fetch(
            fund_list=[f"ResidualDemand_{a}th" for a in [10, 25, 75, 90]],
            grid_list=['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP'],
            hour='00'
        )
    except Exception as e:
        print(f"❌ Error running fund_fetch (mid-perc-00): {e}")
    print()

    print("▶ Running fund_fetch (mid-perc-12)...")
    try:
        fund_fetch(
            fund_list=[f"ResidualDemand_{a}th" for a in [10, 25, 75, 90]],
            grid_list=['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP'],
            hour='12'
        )
    except Exception as e:
        print(f"❌ Error running fund_fetch (mid-perc-12): {e}")
    print()

    print("▶ Running fund_fetch (mid-12)...")
    try:
        fund_fetch(
            fund_list=['ResidualDemand', 'Temp', 'INF', 'Wind', 'Solar', 'CON'],
            grid_list=['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP', 'HUN', 'ROU'],
            hour='12'
        )
    except Exception as e:
        print(f"❌ Error running fund_fetch (mid-12): {e}")
    print()

    print("▶ Running fund_fetch (mnd-00)...")
    try:
        fund_fetch(
            fund_list=['Temp_mnd', 'Wind_mnd', 'Solar_mnd', 'CON_mnd'],
            grid_list=['DEU', 'FRA', 'BEL', 'NLD', 'AUT', 'ESP'],
            hour='00'
        )
    except Exception as e:
        print(f"❌ Error running fund_fetch (mnd-00): {e}")
    print()

    print("▶ Running fund_fetch (AvCap-fetch)...")
    try:
        fund_fetch(
            fund_list=['AvailCap'],
            grid_list=['DEU', 'FRA'],
            hour='00'
        )
    except Exception as e:
        print(f"❌ Error running fund_fetch (AvCap-fetch): {e}")
    print()

    print("▶ Running update_all_futures_flow...")
    try:
        update_all_futures_flow()  # Call as a function
    except Exception as e:
        print(f"❌ Error running update_all_futures_flow: {e}")
    print()

    print("▶ Running fut_price_fetch...")
    try:
        fut_price_fetch(countries=['de', 'fr', 'at', 'nl', 'be', 'it', 'hu', 'ro', 'es', 'cz', 'sk', 'ttf', 'eua'])
    except Exception as e:
        print(f"❌ Error running fut_price_fetch: {e}")
    print()

    print("▶ Running entsoe_av_cap_flow...")
    try:
        entsoe_av_cap_flow(selected_grids=["10YHU-MAVIR----U", "10YRO-TEL------P"])
    except Exception as e:
        print(f"❌ Error running entsoe_av_cap_flow: {e}")
    print()

    print("▶ Running entsoe_inst_cap_flow...")
    try:
        entsoe_inst_cap_flow(grid_mapping={
            "10YHU-MAVIR----U": {"column_suffix": "_hu", "table_name": "HUN"},
            "10YRO-TEL------P": {"column_suffix": "_ro", "table_name": "ROU"},
            "10YCZ-CEPS-----N": {"column_suffix": "_cz", "table_name": "CZE"},
            "10YSK-SEPS-----K": {"column_suffix": "_sk", "table_name": "SVK"},
            "10Y1001A1001A82H": {"column_suffix": "_de", "table_name": "DEU"},
            "10YAT-APG------L": {"column_suffix": "_at", "table_name": "AUT"},
            "10YBE----------2": {"column_suffix": "_be", "table_name": "BEL"},
            "10YNL----------L": {"column_suffix": "_nl", "table_name": "NLD"},
        })
    except Exception as e:
        print(f"❌ Error running entsoe_inst_cap_flow: {e}")
    print()

    print("▶ Running ps_db_fill...")
    try:
        ps_db_fill(
            countries=['de', 'fr', 'at', 'nl', 'be', 'it', 'hu', 'ro', 'es', 'cz', 'sk', 'ttf'],
            base_start_date=datetime(2019, 1, 1)
        )
    except Exception as e:
        print(f"❌ Error running ps_db_fill: {e}")
    print()

if __name__ == "__main__":
    run_all_flows()