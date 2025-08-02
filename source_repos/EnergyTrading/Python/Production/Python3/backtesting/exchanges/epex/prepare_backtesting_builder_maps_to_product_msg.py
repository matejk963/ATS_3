# -*- coding: utf-8 -*-
"""
The utility functions in this script help to create product messages for backtesting feed.

It uses the Builder maps from the Conversion: pkl -> Builder Maps

"""
from __future__ import absolute_import
from __future__ import print_function
import json
import datetime
import os
import re

import autotrader_lib.cet_util as ALCU

BUILDER_MAPS_DIR = os.path.join(os.path.dirname(__file__), "builder_maps")


class PRODUCT_TYPE_FILTER:
    local = "INTRA"
    xbid = "XBID"
    uk = "GB"


def get_builder_json_path(duration_s):
    # type: (int) -> str
    return os.path.join(BUILDER_MAPS_DIR, "BUILDER_MAP_{}.json".format(duration_s))


def generate(start_ts, end_ts, p_type, product_id):
    # type: (float, float, str, str) -> list
    start_dt_cet = ALCU.utc_ts2cet_dt(start_ts)
    end_dt_cet = ALCU.utc_ts2cet_dt(end_ts)
    duration_s = int((end_dt_cet - start_dt_cet).total_seconds())
    filepath = get_builder_json_path(duration_s)

    product_msgs = []

    with open(filepath, "r") as f_in:
        content = json.load(f_in)

    for product_type in content:
        if p_type.lower() not in product_type.lower():
            continue
        product_type_content = content[product_type]
        timerange = product_type_content[start_dt_cet.time().isoformat()][end_dt_cet.time().isoformat()]
        for msg_template in timerange.values():
            new_message = msg_template.copy()
            new_message["timestamp"] = start_ts + msg_template["timestamp"]
            new_message["data"][0]["product_id"] = product_id
            new_message["data"][0]["delivery_start"] = int(start_ts + msg_template["data"][0]["delivery_start"])
            new_message["data"][0]["delivery_end"] = int(start_ts + msg_template["data"][0]["delivery_end"])
            new_message["data"][0]["trading_phases"] = {
                area: {"start": start_ts + tr["start"], "end": start_ts + tr["end"], "state": tr["state"]}
                for area, tr in msg_template["data"][0]["trading_phases"].items()
            }

            name = msg_template["data"][0]["name"]

            # 2H and 4H for GB, update date in product name, also make it possible for other products
            to_replace = re.findall(r"({{(\w+):\[(%Y%m%d %H:%M)]}})", name)

            for to_replace, value, date_pattern in to_replace:
                if value == "from":
                    name = name.replace(to_replace, start_dt_cet.strftime(date_pattern))
                elif value == "to":
                    name = name.replace(to_replace, end_dt_cet.strftime(date_pattern))

            new_message["data"][0]["name"] = start_dt_cet.strftime(name)

            product_msgs.append(new_message)
    product_msgs.sort(key=lambda x: x["timestamp"])
    return product_msgs


if __name__ == '__main__':
    start_ts = ALCU.cet_dt2ts(datetime.datetime(2020, 8, 1, 4))
    end_ts = ALCU.cet_dt2ts(datetime.datetime(2020, 8, 1, 8))
    product_msgs = generate(start_ts, end_ts, PRODUCT_TYPE_FILTER.uk, "00000001")
    print(product_msgs)
