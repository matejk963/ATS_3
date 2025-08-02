"""

file for storing constants and values used over in modules

"""

    
# Fundamental names conversion dict

# Dictionary containing the mapping
long_short_name_dict = {
    'de': 'DEU',
    'fr': 'FRA',
    'it': 'ITA',
    'nl': 'NLD',
    'be': 'BEL',
    'at': 'AUT',
    'hu': 'HUN',
    'ro': 'ROU',
    'cz': 'CZE',
    'sk': 'SVK',
    'osc': 'OSC'
}

# Function to get the long name (e.g., 'de' -> 'DEU')
def from_own_name(own_name):
    return long_short_name_dict.get(own_name, "Not found")

# Function to get the short name (e.g., 'DEU' -> 'de')
def to_own_name(long_name):
    # Reverse the dictionary only when this function is called
    reversed_dict = {v: k for k, v in long_short_name_dict.items()}
    return reversed_dict.get(long_name, "Not found")

# Sources of normal data
normal_source_dict = {
    'local': ['de', 'fr', 'be', 'nl', 'at'],
    'db': ['hu', 'cz', 'ro', 'sk']
}

def get_normal_data_source(element):
    for key, values in normal_source_dict.items():
        if element in values:
            return key
    return None  # Return None if the element is not found

# Subclasses to construct ResidualDemand
residual_demand_constituents_dict = {
    'ResidualDemand': ['de', 'fr', 'be', 'nl', 'at', 'cz'],
    'CON_Wind_Solar': ['ro']
    
}
def get_residual_demand_source(element):
    for key, values in residual_demand_constituents_dict.items():
        if element in values:
            return key
    return None  # Return None if the element is not found

# Mapping for available capacity name for eithe av cap or inst cap
av_cap_mapping = {
    'AvailCap': ['av_cap', 'avail_cap', 'ac', 'available_capacity'],
    'InstCap': ['inst_cap', 'install_cap', 'ic', 'installed_capacity']
}
def get_av_cap_mapping(element):
    for key, values in av_cap_mapping.items():
        if element.lower() in values:
            return key
    return None  # Return None if the element is not found

# Mapping for production source
capacity_source_dict = {'DEU':{'Coal': 105269300,
                                'Lig': 105269303,
                                'Gas': 105663406,
                                'Pump': 111205650,
                                'RoR': 111205652,
                                'Res': 111205651,
                                'Nuc': 105269302,
                                'Oil': 106819498,},
                        'FRA': {'Coal': 106336320,
                                'Gas': 106336321,
                                'Hydro Res': 106336323,
                                'Hydro RoR': 106336324,
                                'Nuc': 106336319,
                                'Oil': 106336325,
                                'Pump': 106336322},
                        'ROU': {'Gas':None,
                                'Coal': None,
                                'Nuc': None,
                                'Lig': None},
                        'HUN': {'Bio': None,
                                'Lig': None,
                                'Gas': None,
                                'Coal': None,
                                'Oil': None,
                                'Nuc': None}}

def get_capacity_sources_for_market(market):
    # first_level_key is market
    # Check if the first_level_key exists in the dictionary
    if market in capacity_source_dict:
        # Return a list of second-level keys
        return list(capacity_source_dict[market].keys())
    else:
        # If the first-level key doesn't exist, return an empty list or a message
        return f"Key '{market}' not found in the dictionary."

def get_capacity_source(market, source_name):
    selected_dict = capacity_source_dict[market]
    return selected_dict.get(source_name, "Not found")

# Gas contracts mapping
gas_fut_map = {
    'ttf': ['de', 'fr', 'at', 'be', 'nl' , 'it', 'cz', 'sk', 'hu',
            'ro', 'hr', 'gr']
}

def get_gas_fut_mapping(element):
    for key, values in gas_fut_map.items():
        if element.lower() in values:
            return key
    return None  # Return None if the element is not found

# Ice contracts name mapping
ice_names_dict = {
    'tfm': ['ttf'],
    'atw': ['api2'],
    'cfi2': ['eua']
}
def get_name_from_ice(ice_name):
    # Retrieve the list from the dictionary, or return "Not found"
    name_list = ice_names_dict.get(ice_name)    
    # If the key exists and the list is not empty, return the first element
    if name_list and len(name_list) > 0:
        return name_list[0]    
    # Return "Not found" if the key doesn't exist or the list is empty
    return "Not found"

def get_name_to_ice(name):
    for key, values in ice_names_dict.items():
        if name.lower() in values:
            return key
    return None  # Return None if the element is not found

scenarios_inst_dict = {
    'ext_data_scen_inst': ['ext_data', 'ex_data', 'external_data',
                            'residualdemand', 'hydro'],
    'av_cap_scen_inst': ['av_cap','avail_cap', 'available_capacity',
                            'availablecapacitydata'],
    'fuels_scen_inst': ['fuel', 'fuels', 
                        'gas', 'coal', 'eua', 'mcr']
}

def get_scen_inst_from_type(scen_type):
    for key, values in scenarios_inst_dict.items():
        if scen_type.lower() in values:
            return key
    return None

fuel_names_map = {
    'Gas': 'ttf',
    'Coal': 'api2',
    'Eua': 'eua',
    'mcr': 'mcr'
}

