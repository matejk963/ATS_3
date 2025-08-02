"""Various utility functions used in multiple tests"""
from __future__ import absolute_import
import base64
import json
import os
import mock

import autotrader_core.api as API
import autotrader_lib.common as COMMON
import autotrader_core.exchanges as APIEXCH
import autotrader_core.strategy as STRATEGY
import autotrader_core.utils as UTILS
import autotrader_core.persistence as PERS
import autotrader_lib.config_helper as ATCONF
from six.moves import range

no_send = UTILS.relay_func
AT_USER = "TRD001"


def load_file_from_dir(directory=None):
    """Closure function to attach directory to the loading function"""
    if directory is None:
        directory = os.path.dirname(__file__)

    def load(*file_path, **kwargs):
        mode = kwargs.get("mode", "rb")
        with open(os.path.join(*(directory, "assets",) + file_path), mode) as fo:
            return fo.read()
    return load


def get_path_for_assets(filename=None):
    """returns the path with the given filename in test environment"""
    directory = os.path.dirname(__file__)
    return os.path.join(directory, "assets", filename)


# Use the closure above to load files from the file direcotry by default
load_file = load_file_from_dir()


def help_update_strategy(autotrader, strategy):
    strategy_responses = []
    for strat_key, strat_data in strategy["data"]["strategy_objects"].items():
        strategy_responses.extend(autotrader.update_strategy(strat_key, strat_data))
    return strategy_responses


def load_strategy(autotrader, file_name="test_strategy_file_3.json", zip_file_name="test_strategy_1.zip",
                  packagename=None, ts_limit_timerange=(0, COMMON.HOUR), strategy_id="198917"):
    """Load the given strategy into the autotrader"""
    strategy = json.loads(load_file(file_name))
    if zip_file_name:
        strategy["data"]["strategy_objects"][strategy_id]["package"] = base64.b64encode(load_file(zip_file_name))
    if packagename is None and zip_file_name:
        strategy["data"]["strategy_objects"][strategy_id]["packagename"] = zip_file_name.rsplit(".")[0]
    else:
        strategy["data"]["strategy_objects"][strategy_id]["packagename"] = packagename

    for strat_key, strat_data in strategy["data"]["strategy_objects"].items():
        autotrader.update_strategy(strat_key, strat_data)
        if not strat_data.get("deleted", False):
            at_strategy = autotrader.strategies[strat_key]
            set_limits(at_strategy,
                       ts_limit_timerange,
                       strategy_limit_maximum_sales_volume=strat_data["maximum_sales_volume_per_product"] or 100.,
                       strategy_limit_maximum_purchase_volume=strat_data["maximum_purchase_volume_per_product"] or 100.,
                       strategy_limit_maximum_purchase_price=strat_data["maximum_purchase_price"] or 100.,
                       strategy_limit_minimum_sales_price=strat_data["minimum_sales_price"] or 0.)
    return autotrader.strategies[strategy_id]


def make_limit_tr(limit_value, timerange, raster=COMMON.QUARTER):
    start, end = timerange
    return [{"begin": ts_start, "end": ts_start + raster, "value": limit_value}
            for ts_start in range(start, end, raster)]


def set_limits(strategy, timerange, aggregation=COMMON.QUARTER,
               strategy_limit_maximum_sales_volume=100, strategy_limit_maximum_purchase_volume=100,
               strategy_limit_maximum_purchase_price=100, strategy_limit_minimum_sales_price=0):

    strategy.strategy_limit_maximum_sales_volume = STRATEGY.mk_strategy_tr_dict(
        make_limit_tr(strategy_limit_maximum_sales_volume, timerange, aggregation), "min_nonone")
    strategy.strategy_limit_maximum_purchase_volume = STRATEGY.mk_strategy_tr_dict(
        make_limit_tr(strategy_limit_maximum_purchase_volume, timerange, aggregation), "min_nonone")
    strategy.strategy_limit_maximum_purchase_price = STRATEGY.mk_strategy_tr_dict(
        make_limit_tr(strategy_limit_maximum_purchase_price, timerange, aggregation), "avg_nonone")
    strategy.strategy_limit_minimum_sales_price = STRATEGY.mk_strategy_tr_dict(
        make_limit_tr(strategy_limit_minimum_sales_price, timerange, aggregation), "avg_nonone")


def initialize(autotrader, correlation_ids, prefix, init_file="contract_info_rprt_001.json"):
    # type: (API.AutoTrader, list, str, str) -> API.AutoTrader
    test_data = json.loads(load_file(init_file))

    for correlation_id in correlation_ids:
        autotrader.update_from_json(test_data, {"correlation_id": "{}-{}".format(prefix, correlation_id)})
    return autotrader


def initialize_child_autotrader(autotrader):
    for exchange in [autotrader.epex, autotrader.nordpool, autotrader.trayport]:
        for ci in exchange.init_files_correlation_ids:
            exchange.init_files_correlation_ids[ci] = True


@UTILS.memorize
def mem_send(*args):
    return [{"body": args[0], "properties": args[1] if len(args) > 1 else {}}]


def init_autotrader(epex=False, nordpool=False, trayport=False, send_func=no_send, send_to_pt=no_send,
                    config=None):
    # type: (bool, bool, bool, callable, callable, API.ATCONF.ATConfig) -> API.AutoTrader
    log_mock = mock.Mock()
    at_config = config or ATCONF.ATConfig(log_mock).get_defaults()
    common_params = dict(autotrader_user="TRD001", password="vt")
    epex_config = ATCONF.EpexConfig(log_mock).set_configs_from_dict(common_params)
    nordpool_config = ATCONF.NordpoolConfig(log_mock).set_configs_from_dict(common_params)
    trayport_config = ATCONF.TrayportConfig(log_mock).set_configs_from_dict(common_params)

    autotrader = API.AutoTrader(config=at_config, child_id=0)
    autotrader.is_persistence_initialized = lambda: True
    autotrader.epex = APIEXCH.Epex(send_func, create_dummy_products=True,
                                   allowed=epex, exchange_config=epex_config)
    autotrader.nordpool = APIEXCH.NordPool(send_func, create_dummy_products=True,
                                           allowed=nordpool, exchange_config=nordpool_config)
    autotrader.trayport = APIEXCH.Trayport(send_func, create_dummy_products=True,
                                           allowed=trayport, exchange_config=trayport_config)

    # we do not want to send
    autotrader.send_to_pt = send_to_pt
    autotrader.autotrader_user = AT_USER
    for exch in [autotrader.epex, autotrader.nordpool, autotrader.trayport]:
        exch.initialize()
    return autotrader


class MockNonThreadedMongoDB(PERS.MongoDBConnector):
    """A mock threaded mongo db which sequentialyses all calls avoiding threading"""
    def put_on_write_queue(self, collection_name, action_type, *args, **kwargs):
        action_callable = getattr(self.db[collection_name], action_type)
        action_callable(*args, **kwargs)


def listify(var, length=1):
    """Helper to make sure that variable is a list with the correct length"""
    if not isinstance(var, (list, tuple)):
        var = [var] * length
    return var
