"""
Simulation Mode: We only use tha api.AutoTrader object, and perform everything in a synchronouse way.
Data is received from a recorded EPEX feed and again ExchangeSimulator is used for matching.
See autotrader_core.i9ntests.simulation_definition_executor
"""

from __future__ import print_function
from __future__ import absolute_import
import uuid
import mock

import six

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

# make fast_logger the real logger. This line does not work anywhere else! It has to be the first line in the project.
# flake8: noqa: E402 # flake8 should ignore the following line before other imports
FLOG.make_standard_logging_module()

import autotrader_core.exchange_simulator as ATSIM
from six.moves import range

from collections import defaultdict
import copy
import gc
import json
import os
import os.path
import sys
import datetime
from zipfile import ZipFile
import functools

import autotrader_core.api
import autotrader_lib.common as COMMON
import autotrader_core.persistence as PERSIST
import autotrader_core.exchanges as APIEXCH
import autotrader_core.exchange_trading as APITR
import autotrader_core.i9ntests.util as I9NUTIL
import backtesting.iterative_simulator as ITSIM
import autotrader_core.utils
import autotrader_lib.cet_util as CETUTIL
import autotrader_lib.util
import autotrader_lib.config_helper as ATCONF
import autotrader_core.i9ntests.simulation_definition_reader as SDR

DATABASE_NAME = "autoTRADER_persist_test_{}".format(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ"))
MK_CONNECTOR_PARAMS = dict(host=os.environ.get("AUTOTRADER_PERSISTENCE_HOST", None),
                           port=os.environ.get("AUTOTRADER_PERSISTENCE_PORT", None),
                           username=os.environ.get("AUTOTRADER_PERSISTENCE_USERNAME", None),
                           password=os.environ.get("AUTOTRADER_PERSISTENCE_PASSWORD", None),
                           write_concern=1,
                           database_name=DATABASE_NAME,
                           expiry_interval=999999999,
                           reset_counter=True)

germany = (COMMON.Area.rwe, COMMON.Area.ve, COMMON.Area.eon, COMMON.Area.enbw)

log = FLOG.getLogger("simulation_definition_executor")


def log_send_msg(exchange, *args, **kwargs):
    msg = "Sent to {}: args:{}, kwargs:{}".format(exchange, args, kwargs)
    log.debug(msg)


def with_log(f):
    def inner(*args, **kwargs):
        log.debug("Called %s with %s, %s", f, args, kwargs)
        return f(*args, **kwargs)
    return inner


def assertions_to_text(assertions):
    """Convert list of assertions into text

    :param assertions: list of assertions
    :type assertions: list[tuple[str]]
    :return: return table of violated assertions
    :rtype: str
    """
    assertions.sort(key=lambda a: a[1])
    text = "Product: {:>32} [delivery: {:>16}-{:>16}]: {:>20} {:>30} {}\n".format(
        "PRODUCT NAME", "START[CET]", "END[CET]", "REFERENCE_NAME",
        "SIMU_RESULT_VALUE", "VIOLATED_REFERENCE_VALUE")

    for name, start, end, reference_name, reference_value, simu_result_value in assertions:
        text += "Product: {:>32} [delivery: {:>16}-{:>16}]: {:>30} {:>40} {}\n".format(
            str(name),
            CETUTIL.utc_ts2cet_dt(start).strftime("%Y-%m-%d %H:%M") if start else "",
            CETUTIL.utc_ts2cet_dt(end).strftime("%Y-%m-%d %H:%M") if end else "",
            str(reference_name), str(reference_value), str(simu_result_value)
        )
    return text


def setup_autotraders(config, reraise_on_strategy_exception):
    """
    Create two api.AutoTrader objects, one parent and one child.
    They are set up to communicate with each other.

    The arguments are passed to the AutoTrader constructor

    :type config: ATCONF.ATConfig
    :type reraise_on_strategy_exception: bool

    :return: auto_trader_parent, auto_trader_child
    :rtype: (autotrader_core.api.AutoTrader,autotrader_core.api.AutoTrader)
    """
    auto_trader_parent = autotrader_core.api.AutoTrader(create_dummy_products=False,
                                                        use_own_strategies_folder=True, config=config,
                                                        reraise_on_strategy_exception=reraise_on_strategy_exception)

    # Load default exchange configs
    common_params = dict(autotrader_user="TRD001", password="vt")
    epex_config = ATCONF.EpexConfig(mock.Mock()).set_configs_from_dict(common_params)
    nordpool_config = ATCONF.NordpoolConfig(mock.Mock()).set_configs_from_dict(common_params)
    trayport_config = ATCONF.TrayportConfig(mock.Mock()).set_configs_from_dict(common_params)

    auto_trader_parent.epex = APIEXCH.Epex(copy.copy(I9NUTIL.mem_send),
                                           create_dummy_products=False,
                                           allowed=True, exchange_config=epex_config)
    auto_trader_parent.epex.next_omt_request = 0  # necessary since exchange initialize method is not called

    auto_trader_parent.nordpool = APIEXCH.NordPool(copy.copy(I9NUTIL.mem_send),
                                                   create_dummy_products=False,
                                                   allowed=True, exchange_config=nordpool_config)
    auto_trader_parent.trayport = APIEXCH.Trayport(copy.copy(I9NUTIL.mem_send),
                                                   create_dummy_products=False,
                                                   allowed=True, exchange_config=trayport_config)

    auto_trader_parent.send_to_pt = lambda *args, **kwargs: log_send_msg(COMMON.Exchange.periotheus, args, kwargs)
    for exchange in auto_trader_parent.all_exchanges:
        exchange.init_files_correlation_ids = {"initialized": True}

    auto_trader_child = copy.deepcopy(auto_trader_parent)
    auto_trader_child.is_parent = False
    for exchange in auto_trader_child.all_exchanges:
        exchange.is_parent = False
    auto_trader_child.send_to_parent = with_log(auto_trader_parent.update_from_strategy_request)
    auto_trader_parent.send_to_children = with_log(functools.partial(auto_trader_child.update_from_json, properties={}))

    return auto_trader_parent, auto_trader_child


def simulate(simulation_file, assert_result=True, write_logfiles=False, use_persistence=False,
             nasty_orders_generators=None, reraise_on_strategy_exception=True, generate_and_assert_xls=True,
             callback_simulation_definition=None, callback_start=None, callback_timer=None,
             callback_finish=None, strategy_folder=None, database_name=None):
    import openpyxl
    if write_logfiles:
        FLOG.setup("", "autotrader.log")
    else:
        FLOG.disable()

    if use_persistence:
        connector_params = MK_CONNECTOR_PARAMS
        if database_name is not None:
            connector_params["database_name"] = database_name
        print("Using database {}".format(connector_params["database_name"]))
        PERSIST.MongoDBConnector._set_instance(PERSIST.MongoDBConnector, I9NUTIL.MockNonThreadedMongoDB())
        PERSIST.MongoDBConnector().initialize(**connector_params)
        PERSIST.MongoDBConnector().db.state.drop()

    simulation_definition, market_state = SDR.read(simulation_file, strategy_folder)

    if callback_simulation_definition is not None:
        callback_simulation_definition(simulation_definition)

    simulation_data_filename_epex = simulation_definition["definition"].get("EPEXFeed", None)
    simulation_data_filename_nord = simulation_definition["definition"].get("NORDFeed", None)
    simulation_data_filename_trayport = simulation_definition["definition"].get("TRAYPORTFeed", None)

    if [simulation_data_filename_epex,
        simulation_data_filename_nord,
        simulation_data_filename_trayport].count(None) < 2:
        raise AssertionError("backtesting is supported only for one concurrent exchange")

    # let's default for one of the exchange, say epex
    exchange_type = COMMON.Exchange.epex
    simulation_data_filename = simulation_data_filename_epex
    if simulation_data_filename_nord:
        exchange_type = COMMON.Exchange.nordpool
        simulation_data_filename = simulation_data_filename_nord
    elif simulation_data_filename_trayport:
        exchange_type = COMMON.Exchange.trayport
        simulation_data_filename = simulation_data_filename_trayport

    print("Running simulation based on", simulation_file,
          "using", simulation_data_filename,
          "on exchange", exchange_type)

    source_dirname = os.path.dirname(simulation_file)
    live_data_json_file = os.path.join(source_dirname, simulation_data_filename)
    if all([os.path.exists("{}.zip".format(live_data_json_file)),
            not os.path.exists("{}.json".format(live_data_json_file)),
            not os.path.exists("{}.jsonl".format(live_data_json_file))]):
        # extract zip file
        print("extracting simulation file {}".format(live_data_json_file))
        with ZipFile("{}.zip".format(live_data_json_file), "r") as myzip:
            myzip.extractall(path=source_dirname)

    lines_mode = False  # in lines mode every file line is its own json message
    if os.path.exists("{}.jsonl".format(live_data_json_file)):
        lines_mode = True
        with open("{}.jsonl".format(live_data_json_file), "r") as ff:
            json_struct = ff.readlines()
    else:
        with open("{}.json".format(live_data_json_file), "r") as ff:
            json_struct = json.load(ff)

    gc.collect()  # Needed for Windows

    import time
    ttt = time.time()

    default_config = {
        "hwm_queu_lag": 10e10,
        "backtesting": True
    }

    if exchange_type == COMMON.Exchange.epex:
        default_config["epex"] = "True"
    elif exchange_type == COMMON.Exchange.trayport:
        default_config["trayport"] = "True"
    elif exchange_type == COMMON.Exchange.nordpool:
        default_config["nordpool"] = "True"

    at_config = ATCONF.ATConfig(logger=log).set_configs_from_dict(default_config)

    auto_trader_parent, auto_trader_child = setup_autotraders(at_config, reraise_on_strategy_exception)
    exchange_simulator = ITSIM.IterativeSimulator(
        autotrader=auto_trader_parent,
        exchange_id=exchange_type,
        nasty_orders_generators=ITSIM._convert_to_list(nasty_orders_generators),
        omt_simulator=ATSIM.OMTSimulator(),
    )

    for exchange in auto_trader_child.all_active_exchanges:
        exchange.update_market_halt(market_state)

    if lines_mode:
        initial_ts = int(json.loads(json_struct[0])["timestamp"] - 1)
        last_ts = int(json.loads(json_struct[-1])["timestamp"] - 1)
    else:
        initial_ts = int(json_struct[0]["timestamp"] - 1)
        last_ts = int(json_struct[-1]["timestamp"] + 1)

    # just for debugging (speedup)
    # last_ts = int(json_struct[10000]["timestamp"]+1)

    jidx = 0
    jlen = len(json_struct)
    json_obj = json_struct[jidx]
    if lines_mode:
        json_obj = json.loads(json_struct[jidx])

    timeline = simulation_definition["definition"]["timeline"]
    timeline.sort()  # just to make sure :)
    timeline_idx = 0
    timeline_len = len(timeline)

    if callback_start is not None:
        callback_start(auto_trader_parent)

    if strategy_folder:
        orig_function = auto_trader_child.get_custom_strategies_path
        strategy_path = os.path.join(orig_function(), strategy_folder)
        auto_trader_child.get_custom_strategies_path = lambda: strategy_path
    else:
        orig_function = None

    try:
        printed_points = 0
        for ts in range(initial_ts, last_ts + 10, 10):
            for i in range(printed_points, int(100 * float(jidx) / jlen)):
                if i % 10 == 0:
                    sys.stdout.write(str(i) + "%")
                else:
                    sys.stdout.write(".")
                printed_points = i + 1
                sys.stdout.flush()
            # Load a strategy. Calls on_strategy_update in the strategy.
            while timeline_idx < timeline_len and timeline[timeline_idx][0] <= ts:
                strategy_objects = timeline[timeline_idx][1]["data"]["strategy_objects"]
                for strategy_id, strategy_data in strategy_objects.items():
                    auto_trader_child.update_strategy(strategy_id, strategy_data)  # Calls get_custom_strategy_path
                # On strategy update might send something to the exchange.
                at_response_messages = exchange_simulator.exchange.send_func.cache().get("res", [])
                exchange_simulator.exchange.send_func.clear_cache()
                exchange_simulator.send(at_response_messages)
                timeline_idx += 1
            while json_obj is not None and json_obj["timestamp"] <= ts:
                # Clean order books and persistence on new session
                if json_obj["message_type"] == "new_session":
                    for product in exchange_simulator.exchange.products.get_all():
                        for order in product.orders.get():
                            order.quantity = 0
                            order.update_db(timestamp=json_obj["timestamp"])
                        product.orders = APITR.OrderBook()
                    for product in exchange_simulator.exchange.products.get_all():
                        for order in product.orders.get():
                            order.quantity = 0
                        product.orders = APITR.OrderBook()
                else:
                    try:
                        exchange_simulator.receive({"body": json_obj, "properties": {}})
                    except COMMON.RestartExchangeException:
                        # Triggered on a market start
                        if json_obj["message_type"] == "market_state":
                            print("catching RestartExchangeException exception for ", json_obj)
                            continue
                        else:
                            raise
                try:
                    jidx += 1
                    json_obj = json_struct[jidx]
                    if lines_mode:
                        json_obj = json.loads(json_struct[jidx])
                except IndexError:
                    json_obj = None

            if callback_timer is not None:
                callback_timer(auto_trader_parent, ts)

            # 10 seconds timer
            exchange_simulator.run_once(COMMON.TimerEvent.timer, timestamp=ts, auto_trader_child=auto_trader_child,
                                        send_func=exchange_simulator.exchange.send_func)

            # quite the same for the products queue timer
            exchange_simulator.run_once(COMMON.TimerEvent.timer_fast, timestamp=ts, auto_trader_child=auto_trader_child,
                                        send_func=exchange_simulator.exchange.send_func)

    finally:
        if orig_function:
            auto_trader_child.get_custom_strategies_path = orig_function

    print("\n", time.time() - ttt, "seconds")
    if callback_finish is not None:
        callback_finish(auto_trader_child)

    if not generate_and_assert_xls:
        return

    # write results
    simulation_file_path, simulation_file_name = os.path.split(simulation_file)
    results_file_name = "{}_results{}".format(*os.path.splitext(simulation_file_name))
    results_file = os.path.join(simulation_file_path, results_file_name)

    wb = openpyxl.load_workbook(simulation_file, keep_vba=False)
    definition = wb["__definition__"]
    start_date = definition["B8"].value.date()
    start_ts = autotrader_core.utils.boundaries_for_cet_day(start_date)[0]

    ws_trades = wb.create_sheet("trades")
    ws_trades.append(
        (
            "time", "exchange", "product", "strategy", "trade_id", "quantity", "price", "sell_delivery_area",
            "buy_delivery_area", "order txt", "product_id"
        )
    )
    for product in exchange_simulator.exchange.products.get_all():
        for t in product.trades.get(trade_filter=COMMON.TradeFilter.own):
            ws_trades.append(
                (
                    autotrader_lib.util.convert_from_timestamp(t.execution_time,
                                                               "%Y-%m-%d %H:%M:%S"), t.exchange, t.product.name,
                    t.portfolio_key, t.trade_id, t.quantity, t.price, t.sell_delivery_area, t.buy_delivery_area,
                    str(t.tags), t.product.product_id
                )
            )

    # container for all violations
    assertions = []

    for strategy_id in simulation_definition["strategy_ids"]:
        print("Strategy", strategy_id, "...")
        results = simulation_definition["results_{}".format(strategy_id)]
        results_quarterly = simulation_definition["results_quarterly_{}".format(strategy_id)]
        results_sheet = wb["results_{}".format(strategy_id)]
        results_quarterly_sheet = wb["results_quarterly_{}".format(strategy_id)]

        buy_volume_collector = defaultdict(float)
        sell_volume_collector = defaultdict(float)
        buy_price_deltas = []
        buy_prices = []
        sell_price_deltas = []
        sell_prices = []
        trade_order_counts = []
        all_products = exchange_simulator.exchange.products.get_all()
        products_by_interval = defaultdict(dict)
        for product in all_products:
            products_by_interval[(product.delivery_start, product.delivery_end)][product.product_id] = product
        for product_interval, product_dict in products_by_interval.items():
            if product_interval not in results:
                continue

            def trade_query(*args, **kwargs):
                result = []
                for product in product_dict.values():
                    result.extend(product.trades.get(*args, **kwargs))
                return result

            def ass(limit, value, reference):
                for product in product_dict.values():
                    assertions.append((product.name, product.delivery_start, product.delivery_end,
                                       limit, value, reference))

            result_values = results[product_interval]
            for key, value in result_values.items():
                if isinstance(value, (int, float)):
                    result_values[key] = round(value, 1)
            public_trades = trade_query(trade_filter=COMMON.TradeFilter.public)
            public_trades = [t for t in public_trades if t.buy_delivery_area in germany and
                             t.sell_delivery_area in germany]

            # AVG Price Public
            if public_trades:
                ptq = sum(t.quantity for t in public_trades)
                ptp = sum(t.quantity * t.price for t in public_trades) / ptq if ptq else None
            else:
                ptq = 0.
                ptp = None

            balanced_volume = 0.

            own_trades = trade_query(trade_filter=COMMON.TradeFilter.own_buy, portfolio_key=strategy_id)
            if own_trades:
                volume = sum(t.quantity for t in own_trades)
                max_price = max(t.price for t in own_trades)
                avg_price = sum(t.quantity * t.price for t in own_trades) / volume if volume else None
            else:
                volume = 0.
                max_price = None
                avg_price = None
            volume = round(volume, 1)
            balanced_volume += volume
            for vcts in range(product_interval[0], product_interval[1], 900):
                buy_volume_collector[vcts] += volume
            result_values["buy_volume"] = volume
            if result_values["max_buy_volume"] is not None:
                if volume > result_values["max_buy_volume"]:
                    ass("max_buy_volume", volume, result_values["max_buy_volume"])
            if result_values["min_buy_volume"] is not None:
                if volume < result_values["min_buy_volume"]:
                    ass("min_buy_volume", volume, result_values["min_buy_volume"])
            result_values["buy_price"] = avg_price
            if result_values["max_buy_price"] is not None:
                if max_price is not None and max_price > result_values["max_buy_price"]:
                    ass("max_buy_price", max_price, result_values["max_buy_price"])
            if result_values["max_buy_avg_price"] is not None:
                if avg_price is not None and avg_price > result_values["max_buy_avg_price"]:
                    ass("max_buy_avg_price", avg_price, result_values["max_buy_avg_price"])
            if avg_price is not None and ptp is not None:
                result_values["delta_buy_avg_price"] = (avg_price - ptp)
                buy_price_deltas.append(((avg_price - ptp), volume))
                buy_prices.append((avg_price, volume))
                if result_values["max_delta_buy_avg_price"] is not None:
                    if (avg_price - ptp) > result_values["max_delta_buy_avg_price"]:
                        ass("max_delta_buy_avg_price", "Own/Public-Avg:{:.2f}/{:.2f}".format(
                            avg_price, ptp), result_values["max_delta_buy_avg_price"]
                            )
            else:
                result_values["delta_buy_avg_price"] = None

            # max_sell_volume, min_sell_volume, min_sell_price, min_sell_avg_price, min_delta_sell_avg_price
            own_trades = trade_query(trade_filter=COMMON.TradeFilter.own_sell, portfolio_key=strategy_id)
            if own_trades:
                volume = sum(t.quantity for t in own_trades)
                min_price = min(t.price for t in own_trades)
                avg_price = sum(t.quantity * t.price for t in own_trades) / volume
            else:
                volume = 0.
                min_price = None
                avg_price = None
            volume = round(volume, 1)
            balanced_volume -= volume
            for vcts in range(product_interval[0], product_interval[1], 900):
                sell_volume_collector[vcts] += volume
            result_values["sell_volume"] = volume
            if result_values["max_sell_volume"] is not None:
                if volume > result_values["max_sell_volume"]:
                    ass("max_sell_volume", volume, result_values["max_sell_volume"])
            if result_values["min_sell_volume"] is not None:
                if volume < result_values["min_sell_volume"]:
                    ass("min_sell_volume", volume, result_values["min_sell_volume"])
            result_values["sell_price"] = avg_price
            if result_values["min_sell_price"] is not None:
                if min_price is not None and min_price < result_values["min_sell_price"]:
                    ass("min_sell_price", min_price, result_values["min_sell_price"])
            if result_values["min_sell_avg_price"] is not None:
                if avg_price is not None and avg_price < result_values["min_sell_avg_price"]:
                    ass("min_sell_avg_price", avg_price, result_values["min_sell_avg_price"])

            if avg_price is not None and ptp is not None:
                result_values["delta_sell_avg_price"] = (avg_price - ptp)
                sell_price_deltas.append(((avg_price - ptp), volume))
                sell_prices.append((avg_price, volume))
                if result_values["min_delta_sell_avg_price"] is not None:
                    if (avg_price - ptp) < result_values["min_delta_sell_avg_price"]:
                        ass("min_delta_sell_avg_price", "Own/Public-Avg:{:.2f}/{:.2f}".format(
                            avg_price, ptp), result_values["min_delta_sell_avg_price"]
                            )
            else:
                result_values["delta_sell_avg_price"] = None

            # max_trade_count, max_trade_size
            own_trades = trade_query(trade_filter=COMMON.TradeFilter.own)
            result_values["trade_count"] = len(own_trades)
            if result_values["max_trade_count"] is not None and len(own_trades) > result_values["max_trade_count"]:
                ass("max_trade_count", len(own_trades), result_values["max_trade_count"])
            tsize = max(t.quantity for t in own_trades) if own_trades else None
            result_values["trade_size"] = tsize
            if result_values["max_trade_size"] is not None and tsize is not None and tsize > result_values["max_trade_size"]:
                ass("max_trade_size", max(t.quantity for t in own_trades), result_values["max_trade_size"])
            # check for 0 quantity trades
            if own_trades and min(t.quantity for t in own_trades) <= 0.:
                ass("trade_size_nonzero", min(t.quantity for t in own_trades), 0.)

            # order count
            result_values["order_count"] = exchange_simulator.executed_own_order_count[product_interval]
            if result_values.get("max_order_count") is not None and \
                    result_values["order_count"] > result_values["max_order_count"]:
                ass("max_order_count", result_values["order_count"], result_values["max_order_count"])

            trade_order_counts.append((result_values["trade_count"], result_values["order_count"]))

            # max_balanced_volume, min_balanced_volume
            result_values["balanced_volume"] = balanced_volume
            if result_values["max_balanced_volume"] is not None:
                if balanced_volume > result_values["max_balanced_volume"]:
                    ass("max_balanced_volume", balanced_volume, result_values["max_balanced_volume"])
            if result_values["min_balanced_volume"] is not None:
                if balanced_volume < result_values["min_balanced_volume"]:
                    ass("min_balanced_volume", balanced_volume, result_values["min_balanced_volume"])

        sum_trades = sum([toc[0] or 0 for toc in trade_order_counts])
        sum_orders = sum([toc[1] or 0 for toc in trade_order_counts])
        num_lines_trades = sum([1 if toc[0] > 0 else 0 for toc in trade_order_counts])
        num_lines_orders = sum([1 if toc[1] > 0 else 0 for toc in trade_order_counts])
        # division by zero not possible here
        avg_trade_count = sum_trades / float(num_lines_trades) if num_lines_trades else 0.
        avg_order_count = sum_orders / float(num_lines_orders) if num_lines_orders else 0.

        if "max_trade_count" in results["AVG"]:
            mdbap = results["AVG"]["max_trade_count"]
            if mdbap is not None and avg_trade_count is not None:
                if mdbap < avg_trade_count:
                    assertions.append(
                        ("AVG", "", "", "max_trade_count", avg_trade_count, mdbap))
        if "max_order_count" in results["AVG"]:
            mdbap = results["AVG"]["max_order_count"]
            if mdbap is not None and avg_order_count is not None:
                if mdbap < avg_order_count:
                    assertions.append(
                        ("AVG", "", "", "max_order_count", avg_order_count, mdbap))

            # evaluate price aggregates
        bvol = sum(x[1] for x in buy_prices)
        if bvol > 0.:
            weighted_buy_price = sum(x[0] * x[1] for x in buy_prices) / bvol
        else:
            weighted_buy_price = None
        svol = sum(x[1] for x in sell_prices)
        if svol > 0.:
            weighted_sell_price = sum(x[0] * x[1] for x in sell_prices) / svol
        else:
            weighted_sell_price = None
        mdbap = results["AVG"]["max_buy_price"]
        if mdbap is not None:
            if weighted_buy_price is not None and mdbap < weighted_buy_price:
                assertions.append(
                    ("AVG", "", "", "max_buy_price", weighted_buy_price, mdbap))
        mdsap = results["AVG"]["min_sell_price"]
        if mdsap is not None and weighted_sell_price is not None:
            if mdsap > weighted_sell_price:
                assertions.append(
                    ("AVG", "", "", "min_sell_price", weighted_sell_price, mdsap))

        # evaluate price delta aggregates
        bvol = sum(x[1] for x in buy_price_deltas)
        if bvol > 0.:
            weighted_buy_price_delta = sum(x[0] * x[1] for x in buy_price_deltas) / bvol
        else:
            weighted_buy_price_delta = None
        svol = sum(x[1] for x in sell_price_deltas)
        if svol > 0.:
            weighted_sell_price_delta = sum(x[0] * x[1] for x in sell_price_deltas) / svol
        else:
            weighted_sell_price_delta = None
        mdbap = results["AVG"]["max_delta_buy_avg_price"]
        if mdbap is not None and weighted_buy_price_delta is not None:
            if mdbap < weighted_buy_price_delta:
                assertions.append(("AVG", "", "", "max_delta_buy_avg_price", weighted_buy_price_delta, mdbap))
        mdsap = results["AVG"]["min_delta_sell_avg_price"]
        if mdsap is not None and weighted_sell_price_delta is not None:
            if mdsap > weighted_sell_price_delta:
                assertions.append(("AVG", "", "", "min_delta_sell_avg_price", weighted_sell_price_delta, mdsap))

        timestamps = [k[0] for k in results_quarterly.keys()]
        timestamps.sort()
        for ts in timestamps:
            def ass(limit, value, reference):
                assertions.append(("QUARTER", ts, ts + 900, limit, value, reference))

            result_values = results_quarterly[(ts, ts + 900)]
            for key, value in result_values.items():
                if isinstance(value, (int, float)):
                    result_values[key] = round(value, 1)

            buy_volume = round(buy_volume_collector[ts], 1)
            sell_volume = round(sell_volume_collector[ts], 1)
            balanced_volume = round(buy_volume - sell_volume, 1)

            last_buy_volume = round(buy_volume_collector.get(ts - 900, 0.), 1)
            last_sell_volume = round(sell_volume_collector.get(ts - 900, 0.), 1)
            last_balanced_volume = round(last_buy_volume - last_sell_volume, 1)

            change = balanced_volume - last_balanced_volume

            result_values["buy_volume"] = buy_volume
            if result_values["max_buy_volume"] is not None:
                if buy_volume > result_values["max_buy_volume"]:
                    ass("quarterly: max_buy_volume", buy_volume, result_values["max_buy_volume"])
            if result_values["min_buy_volume"] is not None:
                if buy_volume < result_values["min_buy_volume"]:
                    ass("quarterly: min_buy_volume", buy_volume, result_values["min_buy_volume"])

            result_values["sell_volume"] = sell_volume
            if result_values["max_sell_volume"] is not None:
                if sell_volume > result_values["max_sell_volume"]:
                    ass("quarterly: max_sell_volume", sell_volume, result_values["max_sell_volume"])
            if result_values["min_sell_volume"] is not None:
                if sell_volume < result_values["min_sell_volume"]:
                    ass("quarterly: min_sell_volume", sell_volume, result_values["min_sell_volume"])

            result_values["balanced_volume"] = balanced_volume
            if result_values["max_balanced_volume"] is not None:
                if balanced_volume > result_values["max_balanced_volume"]:
                    ass("quarterly: max_balanced_volume", balanced_volume, result_values["max_balanced_volume"])
            if result_values["min_balanced_volume"] is not None:
                if balanced_volume < result_values["min_balanced_volume"]:
                    ass("quarterly: min_balanced_volume", balanced_volume, result_values["min_balanced_volume"])

            result_values["change"] = change
            if "min_change" in result_values and result_values["min_change"] is not None:
                if round(change, 3) < round(result_values["min_change"], 3):
                    ass("quarterly: min_change", change, result_values["min_change"])
            if "max_change" in result_values and result_values["max_change"] is not None:
                if round(change, 3) > round(result_values["max_change"], 3):
                    ass("quarterly: max_change", change, result_values["max_change"])

        # this maps the name to the position index of the result col in the sheet
        quarterly_result_names = {"balanced_volume": 3,
                                  "buy_volume": 6,
                                  "sell_volume": 9,
                                  "change": 12}
        for row in results_quarterly_sheet["A3:M98"]:
            offsets = SDR.product_name_to_utc_offsets(row[0].value)
            current_ts = start_ts + offsets[0]
            end_ts = start_ts + offsets[1]
            for name, index in quarterly_result_names.items():
                if name in results_quarterly[(current_ts, end_ts)]:
                    row[index].value = results_quarterly[(current_ts, end_ts)][name]

        # this maps the name to the position index of the result col in the sheet
        result_names = {"balanced_volume": 3,
                        "buy_volume": 6,
                        "buy_price": 8,
                        "delta_buy_avg_price": 11,
                        "sell_volume": 14,
                        "sell_price": 16,
                        "delta_sell_avg_price": 19,
                        "trade_count": 21,
                        "trade_size": 23,
                        "OTR": 24,
                        "order_count": 26}
        for row in results_sheet["A3:AA122"]:
            offsets = SDR.product_name_to_utc_offsets(row[0].value)
            current_ts = start_ts + offsets[0]
            end_ts = start_ts + offsets[1]
            for name, index in result_names.items():
                if name in results[(current_ts, end_ts)]:
                    row[index].value = results[(current_ts, end_ts)][name]

        results_sheet["L124"].value = weighted_buy_price_delta
        results_sheet["T124"].value = weighted_sell_price_delta
        results_sheet["I124"].value = weighted_buy_price
        results_sheet["Q124"].value = weighted_sell_price
        results_sheet["V124"].value = avg_trade_count
        results_sheet["AA124"].value = avg_order_count

    try:
        wb.save(results_file)
    except IOError:
        new_filename = results_file + str(uuid.uuid4()) + "_temp.xlsx"
        log_txt = "Please close the excel file before running simulation Tests." \
                  " Open Result Excel files cannot be overwritten." \
                  " Results will be saved in {}".format(new_filename)
        print(log_txt)
        log.exception(log_txt)
        wb.save(new_filename)

    if assert_result and assertions:
        assertion_text = assertions_to_text(assertions)
        raise Exception("result not equal: Assertions: \n{}".format(assertion_text))

    return auto_trader_parent
