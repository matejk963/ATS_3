import os
import pickle
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class OutageDataMerger:
    def __init__(self, folder_path):
        self.folder_path = folder_path

    def load_and_merge_dictionaries(self, grid, start_date, end_date):
        merged_data = {}

        # Iterate over each file in the folder
        for file_name in os.listdir(self.folder_path):
            if file_name.endswith(".pkl") and grid in file_name:
                # Parse the file's start and end dates from its name
                try:
                    parts = file_name.split('_')
                    file_start_date = datetime.strptime(parts[-2], "%Y%m%d")
                    file_end_date = datetime.strptime(parts[-1].replace('.pkl', ''), "%Y%m%d")
                except ValueError:
                    continue

                # Skip files outside the specified date range
                if file_end_date < start_date or file_start_date > end_date:
                    continue

                file_path = os.path.join(self.folder_path, file_name)

                # Load the existing dictionary from the file
                with open(file_path, 'rb') as f:
                    existing_data = pickle.load(f)

                # Merge the existing dictionary with the merged_data
                for grid_key, grid_data in existing_data.items():
                    if grid_key not in merged_data:
                        merged_data[grid_key] = grid_data
                        continue

                    # Merge resource_dict under each grid
                    resource_dict = grid_data.get("resource_dict", {})
                    for resource_mrid, prod_units in resource_dict.items():
                        for gen_resource_mrid, gen_units in prod_units.items():
                            if resource_mrid not in merged_data[grid_key].get("resource_dict", {}):
                                merged_data[grid_key].setdefault("resource_dict", {})[resource_mrid] = {}
                                merged_data[grid_key].setdefault("resource_dict", {})[resource_mrid][gen_resource_mrid] = gen_units
                                continue
                            elif gen_resource_mrid not in merged_data[grid_key].setdefault("resource_dict", {})[resource_mrid]:
                                merged_data[grid_key].setdefault("resource_dict", {})[resource_mrid][gen_resource_mrid] = gen_units
                                continue
                            # # Merge generation units
                            # for gen_unit_mrid, outages in gen_units.items():
                            #     if gen_unit_mrid not in merged_data[grid_key]["resource_dict"].get(resource_mrid, {}):
                            #         merged_data[grid_key]["resource_dict"].setdefault(resource_mrid, {})[gen_unit_mrid] = outages
                            #         continue

                            # Merge outages
                            for outage_mrid, versions in gen_units.items():
                                if outage_mrid not in merged_data[grid_key]["resource_dict"][resource_mrid][gen_resource_mrid]:
                                    merged_data[grid_key]["resource_dict"][resource_mrid][gen_resource_mrid][outage_mrid] = versions
                                    continue

                                # Merge versions with version check
                                existing_versions = merged_data[grid_key]["resource_dict"][resource_mrid][gen_resource_mrid][outage_mrid]
                                if isinstance(versions, dict):
                                    for created_datetime, outage_data in versions.items():
                                        if created_datetime not in existing_versions:
                                            existing_versions[created_datetime] = outage_data
                                        else:
                                            existing_version = existing_versions[created_datetime]["version"]
                                            new_version = outage_data["version"]
                                            try:
                                                if int(new_version) < int(existing_version):
                                                    existing_versions[created_datetime] = outage_data
                                            except ValueError:
                                                logging.error("Error comparing versions.")
                                else:
                                    logging.error("Expected dictionary for versions but found list.")

        output_file_path = os.path.join(self.folder_path, f"outages_{grid}_merged.pkl")
        with open(output_file_path, 'wb') as f:
            pickle.dump(merged_data, f)
        return merged_data


# Example usage
if __name__ == "__main__":
    folder_path = '//192.168.10.91/d/data/Data/Spot/Entso/Outages'
    grid = "10YHU-MAVIR----U"
    start_date = datetime(2018, 1, 1)
    end_date = datetime(2028, 12, 31)

    merger = OutageDataMerger(folder_path)
    merged_data = merger.load_and_merge_dictionaries(grid, start_date, end_date)

    # Save the merged data to a new pickle file
    # output_file_path = os.path.join(folder_path, f"outages_{grid}_merged.pkl")
    # with open(output_file_path, 'wb') as f:
    #     pickle.dump(merged_data, f)
