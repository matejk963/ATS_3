# -*- coding: utf-8 -*-
"""
Standalone Utility script to create product message builder files

Converts: pkl files -> JSON_Builder files
(for Conversion: recorded jsonl files -> pkl files see: prepare_backtesting_jsonl_to_pkl.py)
Source: data folder, subdirectory according to selection and pkl files in it
Output: Builder Maps, one complete, and all others split into durations
Such that if one only wants to create hour product, only builder map with duration 3600 has to be selected.

This script needs pandas, and is made to build the BUILDER_MAP which backtesting uses to
generate the correct product messages for the message feed.

This file needs the product pkl files in a subfolder of the "data"-folder.
The "data"-folder should be in the same directory as this file.

When this file is run, it picks up all the pickles from the subfolders in "data"-directory,
and then creates the rules for all products in that pickle.
These rules say at what point in time relative to the delivery start a product message has to be sent.
They also they, what changes there are in product name, trading phase or delivery area state.

The offset of the timestamp to delivery start can be different for any product of the day.
So in the best case the products in the pickles should span at least a full day with the products wanted,
and additionally few previous days,
to include in the best case the very first message which states the opening of a trading phase.
"""
import datetime
import json
import os

import pandas as pd
import numpy as np
import glob

# do not cut columns to save print space
from autotrader_lib.cet_util import utc_dt2cet_dt

pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)
# suppress displaying long numbers in scientific notation
pd.set_option('display.float_format', lambda x: '%.2f' % x)

ROOT = os.path.dirname(__file__)
DATAFOLDER = os.path.join(ROOT, 'data')
BUILDER_MAPS_DIR = os.path.join(ROOT, "builder_maps")

# add additional prints while running script
DEBUG = True

# values which are used for the template in all builder maps
# note that product_id has to be overwritten by the function
# which generates autotrader json messages with the builder maps.
message_type = "product"
exchange = "EPEX"
predefined = "true"
product_id = "0000000001"


def convert(o):
    """patch json convert, return simple integer if conversion of numpy integer fails"""
    if isinstance(o, np.int64):
        return int(o)
    raise TypeError


def get_builder_json_path(duration_s=None):
    # type: (int) -> str
    """get json file name based on duration if available"""
    if duration_s is None:
        filename = "BUILDER_MAP.json"
    else:
        filename = "BUILDER_MAP_{}.json".format(duration_s)
    return os.path.join(BUILDER_MAPS_DIR, filename)


def generate_msg_json(message_type, exchange, timestamp, predefined, product_type, product_id,
                      delivery_start, delivery_end, name, delivery_area_states, trading_phases):
    """put info in correct shape for autotrader json messages"""
    return {
        "message_type": message_type,
        "exchange": exchange,
        "timestamp": timestamp,
        "data": [{
            "predefined": predefined,
            "product_type": product_type,
            "product_id": product_id,
            "delivery_end": delivery_end,
            "name": name,
            "delivery_start": delivery_start,
            "delivery_area_states": delivery_area_states,
            "trading_phases": trading_phases
        }]

    }


def get_products_df(date_restriction="*"):
    # type: (str) -> pd.DataFrame
    """Read all pandas pickles in data folder and according date restriction, and convert to data frame"""
    product_files = glob.glob(os.path.join(DATAFOLDER, date_restriction, '*.pkl'))
    dfs = []
    for f in product_files:
        dfs.append(pd.read_pickle(f, compression='gzip'))
    if dfs:
        return pd.concat(dfs)
    else:
        return pd.DataFrame()


def start(products_date, date_restriction="*"):
    # type: (datetime.date, str) -> None
    """Create the builder files based on the found pkl files"""
    PRODUCT_BUILD_MAP = {}

    df = get_products_df(date_restriction)

    errors = []

    columns = ["duration", "delivery_area_id", "product_id", "timestamp", "delivery_start", "delivery_end",
               "product_type", "name", "start", "end", "state", "phase_state"]
    df = df[columns]
    df["ds_dt"] = pd.to_datetime(df["delivery_start"], unit='s', utc=True)
    df["de_dt"] = pd.to_datetime(df["delivery_end"], unit='s', utc=True)
    df["start_dt"] = pd.to_datetime(df["start"], unit='s', utc=True)
    df["end_dt"] = pd.to_datetime(df["end"], unit='s', utc=True)
    df["timestamp"] = np.round(df["timestamp"])
    df["rough_timestamp"] = np.round(df["timestamp"] // 100 * 100)
    df["ts_dt"] = pd.to_datetime(df["timestamp"], unit='s', utc=True)

    df["start_diff"] = df["start"] - df["delivery_start"]
    df["end_diff"] = df["end"] - df["delivery_start"]
    df["timestamp_diff"] = df["timestamp"] - df["delivery_start"]

    group_columns = ["ds_dt", "de_dt", "delivery_start", "delivery_end"]

    # select 24h window of products. select the last product shortest product, und go back 24h
    df = df[(df.start_dt >= products_date) & (df.start_dt < products_date + datetime.timedelta(days=1))]
    df.drop_duplicates(subset=["duration", "delivery_area_id", "product_id", "rough_timestamp", "delivery_start",
                               "delivery_end", "product_type", "name", "start", "end", "state", "phase_state"],
                       inplace=True)  # sometimes multiple entries are sent for the exact same change

    for duration, duration_group in df.groupby(['duration']):
        duration = int(duration)
        PRODUCT_BUILD_MAP[duration] = {}
        for product_type, type_grouped in duration_group.groupby(["product_type"]):
            if product_type not in PRODUCT_BUILD_MAP[duration]:
                PRODUCT_BUILD_MAP[duration][product_type] = {}

            for (time_from, time_to, delivery_start, delivery_end), group in type_grouped.groupby(group_columns):
                if DEBUG:
                    print(time_from, time_to, delivery_start, delivery_end)
                time_from_cet = utc_dt2cet_dt(time_from.to_datetime())
                time_to_cet = utc_dt2cet_dt(time_to.to_datetime())
                time_key_from = time_from_cet.time().isoformat()
                time_key_to = time_to_cet.time().isoformat()
                if time_key_from not in PRODUCT_BUILD_MAP[duration][product_type]:
                    PRODUCT_BUILD_MAP[duration][product_type][time_key_from] = {}
                if time_key_to not in PRODUCT_BUILD_MAP[duration][product_type][time_key_from]:
                    PRODUCT_BUILD_MAP[duration][product_type][time_key_from][time_key_to] = {}

                for (timestamp_diff, name), grouped in group.groupby(["timestamp_diff", "name"]):
                    if DEBUG:
                        print(duration, time_key_from, time_key_to, timestamp_diff, product_type)

                    area_data = grouped[["delivery_area_id", "phase_state"]]
                    area_data = area_data.set_index("delivery_area_id").to_dict()["phase_state"]
                    delivery_area_states = {area: {"state": state} for area, state in area_data.items()}

                    trading_phases = {
                        d["delivery_area_id"]: {"start": d["start_diff"], "end": d["end_diff"], "state": d["state"]}
                        for d in grouped[["delivery_area_id", "start_diff", "end_diff", "state"]].to_dict('records')
                    }

                    # 2H and 4H for GB, update data in product name
                    duration = delivery_end - delivery_start
                    if duration == 7200 and "gb" in product_type.lower():
                        name = name[:2] + "%y%m%d" + name[-3:]
                    elif duration == 14400 and "gb" in product_type.lower():
                        name = name[:2] + "%y%m%d" + name[-2:]
                    final_name = time_from_cet.strftime("%Y%m%d %H:%M") + "-" + time_to_cet.strftime("%Y%m%d %H:%M")
                    if name == final_name:
                        name = "{{from:[%Y%m%d %H:%M]}}-{{to:[%Y%m%d %H:%M]}}"
                    msg = generate_msg_json(message_type, exchange, timestamp_diff, predefined, product_type,
                                            product_id, 0, duration, name, delivery_area_states, trading_phases)

                    PRODUCT_BUILD_MAP[duration][product_type][time_key_from][time_key_to][timestamp_diff] = msg

        with open(get_builder_json_path(int(duration)), "w") as f_out:
            try:
                json.dump(PRODUCT_BUILD_MAP[duration], f_out, default=convert)
            except Exception as exc:
                errors.append(exc)
    with open(get_builder_json_path(), "w") as f_out:
        try:
            json.dump(PRODUCT_BUILD_MAP, f_out, default=convert)
        except Exception as exc:
            errors.append(exc)
    print("WARNING: product names might have to be changed for GB products, since they contain date info")
    print("Errors", errors)


if __name__ == '__main__':
    date_restriction = "*"  # allow all folders in data to be used

    # start conversion of pkl files to builder maps
    start(products_date=pd.datetime(2020, 8, 1), date_restriction=date_restriction)
