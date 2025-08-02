from __future__ import absolute_import
import os
import os.path
import zipfile

import openpyxl

import autotrader_lib.util
import autotrader_lib.common as COMMON
import autotrader_core.utils
import autotrader_lib.config_helper as ATCONF
from six.moves import range


def product_name_to_utc_offsets(name):
    if name.startswith("4H"):
        start_hour = int(name[2:4])
        end_hour = int(name[5:])
        return COMMON.HOUR * start_hour, COMMON.HOUR * end_hour
    elif "-" in name:
        start_hour = int(name[:2])
        return COMMON.HOUR * start_hour, COMMON.HOUR * (start_hour + 1)
    else:
        start_hour = int(name[:2])
        quarter = int(name[3:4])
        start_offset = COMMON.HOUR * start_hour + COMMON.QUARTER * (quarter - 1)
        end_offset = COMMON.HOUR * start_hour + COMMON.QUARTER * (quarter)
        return start_offset, end_offset


def convert_strategy(sheet, start_ts, source_dirname, timestamp, exchange, strategy_folder=None):
    """
    Converts the strategy-definition from an xlsx file to a message for autotrader.

    :return: The ente-id and a message with message-type strategy.
    :rtype: str, dict
    """
    definition = {"maximum_purchase_price": None,
                  "approved_group": None,
                  "maximum_bid": None,
                  "maximum_sales_volume_per_product": None,
                  "minimum_sales_price": None,
                  "minimum_purchase_volume_per_product": None,
                  "approved_privs": None,
                  "immediate_purchase_price": None,
                  "global_privs": None,
                  "owner_group": None,
                  "package": None,
                  "immediate_sales_price": None,
                  "maximum_ask": None,
                  "trading_start": None,
                  "use_fixed_random_seed": True,
                  # List of parameters existing in most of the xls files in A2:A27. The empty ones can be replaced
                  # with new parameters, and we want to be sure that removed keys from xls will be still in dict
                  "packagename": None,
                  "active": None,
                  "behavior": None,
                  "comment": None,
                  "decrease_of_capacity": None,
                  "efficiency": None,
                  "increase_of_capacity": None,
                  "internal_number": None,
                  "last_prognosis_before_market_closure": None,
                  "market_area_1": None,
                  "market_area_2": None,
                  "maximum_imbalance_on_market_closure": None,
                  "maximum_order_book": None,
                  "minimum_down_time": None,
                  "minimum_run_time": None,
                  "minimum_spread_for_arbitrage": None,
                  "minimum_spread_for_buyback": None,
                  "minimum_spread_for_storage": None,
                  "risk_affinity": None,
                  "short_name": None,
                  "standard_deviation_begin": None,
                  "standard_deviation_end": None,
                  "stop_on_limit_violation": None,
                  "trading_end_before_market_closure": None,
                  "valid_from": None,
                  "valid_to": None}

    ente_id = str(sheet["B1"].value)
    for key, value in sheet["A2:B27"]:
        if key.value in ("stop_on_limit_violation", "active", "use_fixed_random_seed"):
            if value.value in ("=TRUE()", "1", 1, "True", "true", "TRUE", True):
                definition[key.value] = True
            else:
                definition[key.value] = False
        else:
            definition[key.value] = value.value
        if key.value == "market_area_1":
            definition["exchange_1"] = exchange
        if key.value == "market_area_2":
            definition["exchange_2"] = exchange

    strategy_file = os.path.join(source_dirname, definition["packagename"] + ".zip")
    if definition["packagename"].startswith("own/"):
        definition["packagename"] = definition["packagename"][4:]
        strategy_file = os.path.join(source_dirname, definition["packagename"] + ".zip")
        if strategy_folder:
            folder = os.path.join(ATCONF.get_at_root(), "own_strategies", strategy_folder, definition["packagename"])
        else:
            folder = os.path.join(ATCONF.get_at_root(), "own_strategies", definition["packagename"])
        with zipfile.ZipFile(strategy_file, "w", zipfile.ZIP_DEFLATED) as zipf:
            for filename in os.listdir(folder):
                zipf.write(os.path.join(folder, filename), filename)
    with open(strategy_file, "rb") as f_read:
        definition["package"] = f_read.read()
    # timeseries
    names = list(sheet["B30:AM30"])[0]
    timeseries = dict((i, []) for i in range(len(names)))
    for row in sheet["A31:AM126"]:
        offsets = product_name_to_utc_offsets(row[0].value)
        current_ts = start_ts + offsets[0]
        for i, cell in enumerate(row[1:]):
            ts_row = {"begin": current_ts,
                      "end": current_ts + COMMON.QUARTER,
                      "value": cell.value}
            timeseries[i].append(ts_row)

    for idx, name in enumerate(names):
        if name.value is not None:
            if name.value.startswith("user/"):
                if "user_defined_timeseries" not in definition:
                    definition["user_defined_timeseries"] = {}
                definition["user_defined_timeseries"][name.value[5:]] = timeseries[idx]
            else:
                definition["strategy_" + name.value] = timeseries[idx]
    return ente_id, {"data": {"strategy_objects": {str(ente_id): definition}},
                     "message_type": "strategy",
                     "timestamp": timestamp,
                     "exchange": "PERIOTHEUS"}


def get_marketstate_unixtime(timestamp):
    day, time = timestamp.split("_")
    delta_days = int(day[1:])
    return COMMON.DAY * delta_days + product_name_to_utc_offsets(time)[0]


def convert_marketstate(sheet, start_date):
    timeseries = []
    for row in sheet["A2:B200"]:
        if row[0].value is None:
            continue
        current_ts = start_date \
            + get_marketstate_unixtime(row[0].value)
        ts_row = dict(begin=current_ts,
                      end=current_ts + COMMON.QUARTER,
                      value=row[1].value)
        timeseries.append(ts_row)
    return timeseries


def convert_results(sheet, start_ts):
    results = {}
    names = list(sheet["B2:AA2"])[0]
    for row in sheet["A3:AA122"]:
        current_ts, end_ts = product_name_to_delivery_period(row[0].value, start_ts)
        ts_results = {}
        for i, cell in enumerate(row[1:]):
            ts_results[names[i].value] = cell.value
        results[(current_ts, end_ts)] = ts_results
    for row in sheet["A124:AA124"]:
        ts_results = {}
        for idx, cell in enumerate(row[1:]):
            ts_results[names[idx].value] = cell.value
        results["AVG"] = ts_results
    return results


def product_name_to_delivery_period(name, start_ts):
    """
    Convert names, as used in the excel file to delivery periods.
    :param name: As used in the excel file. E.g. "10Q1" or "10-11"
    :type name: str
    :param start_ts: Timestamp for the start of the day
    :type start_ts: int or float
    :return: start and end timestamps
    :rtype: tuple
    """
    offsets = product_name_to_utc_offsets(name)
    current_ts = start_ts + offsets[0]
    end_ts = start_ts + offsets[1]
    return current_ts, end_ts


def convert_results_quarterly(sheet, start_ts):
    results = {}
    names = list(sheet["B2:M2"])[0]
    for row in sheet["A3:M98"]:
        current_ts, end_ts = product_name_to_delivery_period(row[0].value, start_ts)
        ts_results = {}
        for idx, cell in enumerate(row[1:]):
            ts_results[names[idx].value] = cell.value
        results[(current_ts, end_ts)] = ts_results
    return results


def read(file_name, strategy_folder=None):
    """
    Read an xlsx workbook with the simulation definition.

    :param file_name: The name of the xlsx file to read.
    :type file_name: str
    :return: The simulation definition as dict and a market_state dict.
    :rtype: dict, dict
    """
    export = {}
    source_dirname = os.path.dirname(file_name)
    wb = openpyxl.load_workbook(file_name, data_only=True, keep_vba=True)

    definition = wb["__definition__"]
    definition_export = {}
    timeline = []
    timeline_mode = False
    start_ts = 0
    exchange = None

    strategy_ids = set()

    for key, value in definition["A1:B1000"]:
        if key.value is not None:
            if key.value == "description":
                definition_export["description"] = "{}{}\n".format(
                    definition_export.get("description", ""),
                    value.value)
            if key.value == "simulationdate":
                date = value.value.date()
                start_ts = autotrader_core.utils.boundaries_for_cet_day(date)[0]
                definition_export[key.value] = value.value
            elif key.value in ["EPEXFeed", "NORDFeed"]:
                if key.value == "EPEXFeed" and value.value != "":
                    exchange = COMMON.Exchange.epex
                elif key.value == "NORDFeed" and value.value != "":
                    exchange = COMMON.Exchange.nordpool
                definition_export[key.value] = value.value
            elif key.value == "sheetstimeline":
                timeline_mode = True
            elif timeline_mode:
                sheet = wb[value.value]
                if sheet["A1"].value == "strategy":
                    try:
                        market_state = wb["market_state"]
                        market_state_ts = convert_marketstate(market_state, start_ts)
                    except Exception:
                        market_state_ts = []
                    timestamp = autotrader_lib.util.convert_dt_to_timestamp(key.value)
                    ente_id, data = convert_strategy(
                        sheet, start_ts, source_dirname, timestamp, exchange, strategy_folder
                    )
                    strategy_ids.add(ente_id)
                    export["results_{}".format(ente_id)] = convert_results(wb["results_{}".format(ente_id)], start_ts)
                    export["results_quarterly_{}".format(ente_id)
                           ] = convert_results_quarterly(wb["results_quarterly_{}".format(ente_id)], start_ts)
                timeline.append((timestamp, data))
            else:
                definition_export[key.value] = value.value
            if timeline_mode and key.value is None:
                timeline_mode = False
    definition_export["timeline"] = timeline
    export["definition"] = definition_export
    export["strategy_ids"] = strategy_ids

    return export, market_state_ts
