"""
This module contains utility functions for dealing with units.
"""

import autotrader_lib.common as COMMON


MAP_UPPER_STR_TO_UNIT = {
    "": COMMON.Units.MW,
    "MW": COMMON.Units.MW,
    "MWH/H": COMMON.Units.MW,
    "PEG_MWH_DAY": COMMON.Units.PEG_MWH_DAY,
    COMMON.Units.MW.upper(): COMMON.Units.MW,
    COMMON.Units.MWH.upper(): COMMON.Units.MWH,
    COMMON.Units.PEG_MWH_DAY.upper(): COMMON.Units.PEG_MWH_DAY
}

# IMPORTANT: PEG_MWH_DAY is a mixed unit: until the duration limit, it is energy, above the limit it is power
# Idea to include the rare cases of Daylight Saving Time: 25 hour limit is used instead of 24
CONVERSIONS = {
    COMMON.Units.MW: {
        COMMON.Units.MW: lambda amount, _: float(amount),
        COMMON.Units.MWH: lambda amount, duration_hrs: float(amount) * duration_hrs,
        COMMON.Units.PEG_MWH_DAY: lambda amount, duration_hrs: amount * 24. if duration_hrs > 25. else float(
            amount) * duration_hrs
    },
    COMMON.Units.MWH: {
        COMMON.Units.MW: lambda amount, duration_hrs: float(amount) / duration_hrs,
        COMMON.Units.MWH: lambda amount, _: float(amount),
        COMMON.Units.PEG_MWH_DAY:
            lambda amount, duration_hrs: amount * 24. / duration_hrs if duration_hrs > 25. else float(amount)
    },
    COMMON.Units.PEG_MWH_DAY: {
        COMMON.Units.MW: lambda amount, duration_hrs: amount / 24. if duration_hrs > 25. else float(
            amount) / duration_hrs,
        COMMON.Units.MWH: lambda amount, duration_hrs: amount / 24. * duration_hrs if duration_hrs > 25. else float(
            amount),
        COMMON.Units.PEG_MWH_DAY: lambda amount, _: float(amount)
    }
}


def convert_units(amount, from_unit="", to_unit="", duration_hours=None):
    """Calculates the input amount in to_unit, converting from the from_unit and - if necessary - the duration hours"""
    from_unit = MAP_UPPER_STR_TO_UNIT[from_unit.upper()]
    to_unit = MAP_UPPER_STR_TO_UNIT[to_unit.upper()]
    return CONVERSIONS[from_unit][to_unit](amount, duration_hours)
