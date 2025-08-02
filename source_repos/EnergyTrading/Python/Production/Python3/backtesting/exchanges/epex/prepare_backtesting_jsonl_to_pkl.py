"""
Running this file is the first step to generate builder_maps for backtesting
This file is responsible for:

Conversion: jsonl -> pkl

Source: Files need to be in "jsonl_files" directory
Output:
 - Creates folder in "data" directory with the dates of the first and last timestamp
 - Creates a pkl file with the same name inside that directory
Output needs to be in that directory so other scripts can pick it up.

The recordings are filtered, reformatted and saved in smaller pickle files.
Those pickle files are then later used to generate the set of rules which are used to simulate
product messages. The set of rules are then saved in builder maps.
"""
from __future__ import absolute_import
from __future__ import print_function
import json

import datetime
import os

import pandas as pd
import typing as T

ROOT = os.path.dirname(__file__)
DATAFOLDER = os.path.join(ROOT, 'data')
JSONL_DIR = os.path.join(ROOT, "jsonl_files")

# do not cut columns to save print space
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)
# suppress displaying long numbers in scientific notation
pd.set_option('display.float_format', lambda x: '%.2f' % x)


def prepare_products_df(product_data):
    # type: (T.List[T.Dict]) -> pd.DataFrame
    """Reshape json messages to a format which can be made into a pandas table"""
    products_container = []
    for product_msg in product_data:
        for product in product_msg["data"]:
            if product["trading_phases"]:
                for delivery_area_id, phase in product["trading_phases"].items():
                    new_prod = product.copy()
                    del new_prod["trading_phases"]
                    del new_prod["delivery_area_states"]
                    new_prod["phase_state"] = product["delivery_area_states"][delivery_area_id].get("state")
                    new_prod["duration"] = product.get("delivery_end", 0) - product.get("delivery_start", 0)
                    new_prod["trade_duration"] = (phase.get("end", 0) - phase.get("start", 0)) or None
                    new_prod["timestamp"] = product_msg["timestamp"]
                    new_prod["delivery_area_id"] = delivery_area_id
                    new_prod.update(phase)
                    products_container.append(new_prod)
            else:
                new_prod = product.copy()
                new_prod["phase_state"] = None
                new_prod["duration"] = product.get("delivery_end", 0) - product.get("delivery_start", 0)
                new_prod["trade_duration"] = None
                new_prod["timestamp"] = product_msg["timestamp"]
                new_prod["delivery_area_id"] = None
                products_container.append(new_prod)
    return pd.DataFrame(products_container)


def start(jsonl_files):
    # type: (list) -> None
    """Run conversion and save product data of given files to single pkl file"""
    PRODS = {}
    PROD_BY_ID = {}

    p_msgs = []
    for f in jsonl_files:
        with open(f, "r") as f_in:
            try:
                for idx, json_line in enumerate(f_in.readlines()):
                    line = json.loads(json_line)
                    if line["message_type"] != "product":
                        continue

                    p_msgs.append(line)
                    for d in line["data"]:
                        product_type = d["product_type"]
                        delivery_start = d["delivery_start"]
                        delivery_end = d["delivery_end"]
                        product_id = d["product_id"]

                        delivery_start = datetime.datetime.fromtimestamp(delivery_start).isoformat()
                        delivery_end = datetime.datetime.fromtimestamp(delivery_end).isoformat()

                        if product_id not in PROD_BY_ID:
                            PROD_BY_ID[product_id] = []
                        PROD_BY_ID[product_id].append(line)
                        if product_type not in PRODS:
                            PRODS[product_type] = {}
                        if delivery_start not in PRODS[product_type]:
                            PRODS[product_type][delivery_start] = {}
                        if delivery_end not in PRODS[product_type][delivery_start]:
                            PRODS[product_type][delivery_start][delivery_end] = []
                        PRODS[product_type][delivery_start][delivery_end].append(line)
            except json.decoder.JSONDecodeError as exc:
                print(exc)
            finally:
                print("FINISHED")
    print("convert json lines to dataframe")
    df = prepare_products_df(p_msgs)

    # save pickle in data folder
    first_ts = datetime.datetime.fromtimestamp(df.timestamp.min()).strftime("%Y-%m-%d_%H-%M")
    last_ts = datetime.datetime.fromtimestamp(df.timestamp.max()).strftime("%Y-%m-%d_%H-%M")
    base_name = "{}_to_{}".format(first_ts, last_ts)
    save_dir = os.path.join(DATAFOLDER, base_name)
    output_path = os.path.join(save_dir, base_name + ".pkl")
    print(("save pickle in data folder... {}".format(output_path)))
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    df.to_pickle(output_path, compression="gzip")


if __name__ == '__main__':
    # enter here the jsonl files to be used to create a new product data pickle
    jsonl_files = [
        # REPLACE with your jsonl files!
        os.path.join(JSONL_DIR, "MY_JSON_FILE.jsonl")
    ]

    # start conversion
    start(jsonl_files)
