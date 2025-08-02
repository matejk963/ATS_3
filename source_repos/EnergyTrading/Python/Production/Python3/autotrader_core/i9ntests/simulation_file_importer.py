from __future__ import absolute_import
from __future__ import print_function
import json

import autotrader_core.persistence as PERSIST
import autotrader_core.api
import autotrader_core.utils
import argparse
import os
import sys
import logging
import logging.config
import six.moves.configparser as configparser
from six.moves import range


def parse_args(argv=None):

    if argv is None:
        argv = sys.argv[1:]

    print(argv)

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('FILE',
                        help="Json file to be imported to the persistence.")

    args = parser.parse_args(argv)
    print(args.FILE)
    return args


def run(simulation_data_filename):

    default_config = {"external_simulation_queue": False,
                      "nagios_strategy": "",
                      "autotrader_user": None,
                      "epex": True,
                      "epex_conf": {"autotrader_user": "AT_USER"},
                      "nordpool": False,
                      "nordpool_conf": {"autotrader_user": "AT_USER"},
                      }

    config = configparser.SafeConfigParser()
    config.optionxform = str  # enable case-sensitivity
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    config.read(os.path.join(assets_dir, "autotrader_simulation_nolog.conf"))
    logging.config.fileConfig(
        os.path.join(assets_dir, "autotrader_simulation_nolog.conf"), disable_existing_loggers=True
    )

    PERSIST.MongoDBConnector().initialize(expiry_interval=999999999)

    default_config.update(dict(config.items("autotrader")))
    parser = argparse.ArgumentParser()
    parser.set_defaults(**default_config)
    args = {}

    with open(simulation_data_filename, "r") as ff:
        json_struct = json.load(ff)

    auto_trader = autotrader_core.api.AutoTrader(create_dummy_products=False,
                                                 use_own_strategies_folder=True, config=args,
                                                 reraise_on_strategy_exception=True)

    jlen = len(json_struct)

    printed_points = 0
    for jidx, json_obj in enumerate(json_struct):
        for i in range(printed_points, int(100 * float(jidx) / jlen)):
            if i % 10 == 0:
                sys.stdout.write(str(i) + "%")
            else:
                sys.stdout.write(".")
            printed_points = i + 1
            sys.stdout.flush()
        auto_trader.update_from_json(json_obj, {})


if __name__ == "__main__":
    args = parse_args()
    run(args.FILE)
