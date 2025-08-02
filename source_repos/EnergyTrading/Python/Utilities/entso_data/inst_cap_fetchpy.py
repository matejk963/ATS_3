import pandas as pd
import requests
from xml.etree import ElementTree as ET
import json  # Assuming JSON for config file

from Common.config_load import get_config_path

# Load API key from config
with open(get_config_path(), 'r') as f:
    config = json.load(f)  # Adjust based on your config file format
    api_key = config['EntsoE']['matej_api_key']

url = "https://web-api.tp.entsoe.eu/api"

# Define date range
date_range = pd.date_range('2025-01-01', '2025-01-03')

# Grid mapping dictionary
grid_mapping = {
    "10YHU-MAVIR----U": {"column_suffix": "_hu", "table_name": "HUN"}
    # Add more grids as needed
}

# Namespace for XML parsing (matches the XML example provided)
namespace = {"ns": "urn:iec62325.351:tc57wg16:451-6:configurationdocument:3:0"}

# Initialize final DataFrames to store aggregated results
df_final_capacity = pd.DataFrame()
df_final_units = pd.DataFrame()

# Iterate over grids and dates
for grid_code, grid_info in grid_mapping.items():
    for fcst_date in date_range:
        implement_date = fcst_date.strftime("%Y-%m-%d")

        params = {
            "securityToken": api_key,
            "documentType": "A95",  # Production and Generation Units
            "businessType": "B11",  # Production
            "BiddingZone_Domain": grid_code,
            "Implementation_DateAndOrTime": implement_date
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to retrieve data for {grid_info['table_name']} on {implement_date}: {e}")
            continue  # Skip to next iteration

        # Parse XML
        try:
            xml_data = ET.fromstring(response.text)
        except ET.ParseError as e:
            print(f"XML Parsing failed for {grid_info['table_name']} on {implement_date}: {e}")
            continue

        # Data storage for current date
        capacity_by_psrtype_list = []  
        unit_details_list = []  

        # Extract data from each TimeSeries
        for timeseries in xml_data.findall(".//ns:TimeSeries", namespace):
            # Production unit code
            prod_unit_elem = timeseries.find("ns:registeredResource.mRID", namespace)
            prod_unit_code = prod_unit_elem.text if prod_unit_elem is not None else "Unknown"

            # Get MktPSRType
            mkt_psr = timeseries.find("ns:MktPSRType", namespace)
            psr_type_elem = mkt_psr.find("ns:psrType", namespace) if mkt_psr is not None else None
            psr_type = psr_type_elem.text if psr_type_elem is not None else "Unknown"

            # Check for GeneratingUnit_PowerSystemResources
            gen_units = mkt_psr.findall("ns:GeneratingUnit_PowerSystemResources", namespace) if mkt_psr is not None else []

            if gen_units:  # If generation units exist
                for gen_unit in gen_units:
                    gen_unit_code_elem = gen_unit.find("ns:mRID", namespace)
                    gen_unit_code = gen_unit_code_elem.text if gen_unit_code_elem is not None else "Unknown"

                    inst_cap_elem = gen_unit.find("ns:nominalP", namespace)
                    inst_cap = float(inst_cap_elem.text) if inst_cap_elem is not None else 0

                    # Create unique name
                    unit_name = f"{psr_type}_{prod_unit_code}_{gen_unit_code}"

                    # Append to current date list
                    capacity_by_psrtype_list.append({
                        "fcst_date": implement_date,
                        "psr_type": psr_type,
                        "installed_capacity": inst_cap
                    })

                    # Append to unit details list
                    unit_details_list.append({
                        "fcst_date": implement_date,
                        "unit_name": unit_name
                    })
            else:  # No generation units, use MktPSRType data
                inst_cap_elem = mkt_psr.find("ns:nominalIP_PowerSystemResources.nominalP", namespace) if mkt_psr is not None else None
                inst_cap = float(inst_cap_elem.text) if inst_cap_elem is not None else 0

                # Create unique name without generation unit
                unit_name = f"{psr_type}_{prod_unit_code}_None"

                # Append to current date list
                capacity_by_psrtype_list.append({
                    "fcst_date": implement_date,
                    "psr_type": psr_type,
                    "installed_capacity": inst_cap
                })

                # Append to unit details list
                unit_details_list.append({
                    "fcst_date": implement_date,
                    "unit_name": unit_name
                })

        # Convert to DataFrame for this fcst_date (Capacity DataFrame)
        df_capacity = pd.DataFrame(capacity_by_psrtype_list)

        # Aggregate and pivot data for the current date
        if not df_capacity.empty:
            df_capacity = df_capacity.groupby(["fcst_date", "psr_type"], as_index=False)["installed_capacity"].sum()

            # Pivot for structured output
            df_capacity_pivot = df_capacity.pivot_table(
                index="fcst_date", 
                columns="psr_type", 
                values="installed_capacity", 
                fill_value=0
            )

            # Concatenate to final DataFrame
            df_final_capacity = pd.concat([df_final_capacity, df_capacity_pivot])

        # Convert to DataFrame for this fcst_date (Units DataFrame)
        df_units = pd.DataFrame(unit_details_list)

        # Concatenate unit details to final units DataFrame
        df_final_units = pd.concat([df_final_units, df_units])




# Display final results
print("\nFinal Aggregated Capacity DataFrame:")
print(df_final_capacity)

print("\nFinal Aggregated Units DataFrame:")
print(df_final_units)
