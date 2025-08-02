import os
import pickle

# Folder path containing the outage dictionaries
folder_path = r'C:\data\Data\Spot\Entso\Outages'

def load_and_merge_dictionaries(folder_path, grids_to_include):
    merged_data = {}

    # Iterate over each file in the folder
    for file_name in os.listdir(folder_path):
        if file_name.endswith(".pkl"):
            # Check if the filename contains any of the specified grids
            if not any(grid in file_name for grid in grids_to_include):
                continue

            file_path = os.path.join(folder_path, file_name)
            
            # Load the existing dictionary from the file
            with open(file_path, 'rb') as f:
                existing_data = pickle.load(f)

            # Merge the existing dictionary with the merged_data
            for grid, grid_data in existing_data.items():
                if grid not in merged_data:
                    merged_data[grid] = grid_data
                    continue

                # Merge resource_dict under each grid
                resource_dict = grid_data.get("resource_dict", {})
                for resource_mrid, gen_units in resource_dict.items():
                    if resource_mrid not in merged_data[grid]["resource_dict"]:
                        merged_data[grid]["resource_dict"][resource_mrid] = gen_units
                        continue

                    # Merge generation units
                    for gen_unit_mrid, outages in gen_units.items():
                        if gen_unit_mrid not in merged_data[grid]["resource_dict"][resource_mrid]:
                            merged_data[grid]["resource_dict"][resource_mrid][gen_unit_mrid] = outages
                            continue

                        # Merge outages
                        for outage_mrid, versions in outages.items():
                            if outage_mrid not in merged_data[grid]["resource_dict"][resource_mrid][gen_unit_mrid]:
                                merged_data[grid]["resource_dict"][resource_mrid][gen_unit_mrid][outage_mrid] = versions
                                continue

                            # Merge versions with version check
                            for created_datetime, outage_data in versions.items():
                                if created_datetime not in merged_data[grid]["resource_dict"][resource_mrid][gen_unit_mrid][outage_mrid]:
                                    merged_data[grid]["resource_dict"][resource_mrid][gen_unit_mrid][outage_mrid][created_datetime] = outage_data
                                else:
                                    # Compare versions and keep the one with the lower version number
                                    existing_version = merged_data[grid]["resource_dict"][resource_mrid][gen_unit_mrid][outage_mrid][created_datetime]["version"]
                                    new_version = outage_data["version"]
                                    try:
                                        if int(new_version) < int(existing_version):
                                            merged_data[grid]["resource_dict"][resource_mrid][gen_unit_mrid][outage_mrid][created_datetime] = outage_data
                                    except:
                                        print('60')

    return merged_data

# Example usage
# Specify the grids to include
grids_to_include = ["10YCZ-CEPS-----N", "10YSK-SEPS-----K", "10YFR-RTE------C",
             "10Y1001A1001A82H", "10YAT-APG------L", "10YBE----------2",
             "10YHU-MAVIR----U", "10YRO-TEL------P"]

# Merge the dictionaries from the folder for the specified grids
merged_data = load_and_merge_dictionaries(folder_path, grids_to_include)

# Save the merged data to a new pickle file
output_file_path = r'C:\data\Data\Spot\Entso\Outages\outages_total.pkl'
with open(output_file_path, 'wb') as f:
    pickle.dump(merged_data, f)
