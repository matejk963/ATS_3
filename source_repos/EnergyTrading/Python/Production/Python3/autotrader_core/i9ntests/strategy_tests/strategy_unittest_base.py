#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
import collections
import datetime
import json
import logging
import mock
import numbers
import os
import time
import unittest

import autotrader_core.api as API
import autotrader_lib.common as COMMON
import autotrader_core.i9ntests.exchanges_mocks
import autotrader_core.exchanges as APIEXCH
import autotrader_core.persistence as PERSIST
import autotrader_lib.cet_util as CETUTIL
import autotrader_lib.config_helper as ATCONF
from autotrader_core.strategy import SlotResponse, Strategy
from six.moves import map
from six.moves import range
from six.moves import zip

log = logging.getLogger(__name__)

EXCHANGE = 'TRAYPORT'
_SEQ_ID = "1"


def path(asset_filename):
    return os.path.join(os.path.dirname(__file__), "assets", "gas_unittest_init_files", asset_filename)


def make_value_list(from_ts, to_ts, val):
    needed_length = (to_ts - from_ts) / COMMON.QUARTER
    if val is None or isinstance(val, numbers.Number):
        return [
            {"begin": ts, "end": ts + COMMON.QUARTER, "value": val}
            for ts in range(from_ts, to_ts, COMMON.QUARTER)
        ]
    elif isinstance(val, list):
        assert len(val) == needed_length, \
            "Needed length: {}, ts length: {}".format(needed_length, len(val))
        return [
            {"begin": ts, "end": ts + COMMON.QUARTER, "value": val[idx]}
            for idx, ts in enumerate(range(from_ts, to_ts, COMMON.QUARTER))
        ]


class TestStrategyBase(unittest.TestCase):

    strategy_id = "TEST_STRAT_ID"
    strategy_package_name = None
    first_delivery_start = None
    last_delivery_start = None
    trayport_config = {}

    def setUp(self, exchange, area_id):
        super(TestStrategyBase, self).setUp()
        # Set the persistence to uninitialized, in case it was initialized in a previous test
        PERSIST.MongoDBConnector().is_initialized = False

        self.area_id = area_id
        self.exchange = exchange
        self.products = []

        setup_by_exchange = {
            COMMON.Exchange.epex: self._setup_epex,
            COMMON.Exchange.nordpool: self._setup_nordpool,
            COMMON.Exchange.trayport: self._setup_trayport,
        }

        #################################
        # setup autotrader and Exchange #
        #################################

        # we use setUp for the autotrader init to get a clean state every test
        self.autotrader = API.AutoTrader(is_parent=False, child_id=0)
        self.autotrader.current_timestamp = time.time()

        setup_by_exchange[exchange]()

        ########################################################
        # setup strategy based on settings of child test class #
        ########################################################
        self.first_delivery_start = self.get_first_delivery_start()
        self.last_delivery_end = self.get_last_delivery_end()
        self.strategy = self.load_strategy()

        self.strat_def = self.get_empty_strat_def(exchange=self.exchange,
                                                  area=self.area_id,
                                                  strategy_id=self.strategy_id,
                                                  packagename=self.strategy_package_name)

        #################################
        # remember calls of place slots #
        #################################
        self.calls = []
        self.original_place_slots = self.strategy.place_slots
        self.strategy.place_slots = self._mock_place_slots

        #####################################################
        # placeholders for timeseries definition and values #
        #####################################################
        #
        # example:
        # self.ts_names_settings = {
        #     COMMON.StrategyJsonKey.TS.limit_buy_price: 40,
        #     COMMON.StrategyJsonKey.TS.limit_buy_vol: 100
        # }
        self.ts_names_settings = {
            COMMON.StrategyJsonKey.TS.limit_buy_price: 1000,
            COMMON.StrategyJsonKey.TS.limit_buy_vol: 1000,
            COMMON.StrategyJsonKey.TS.limit_sell_vol: 1000,
            COMMON.StrategyJsonKey.TS.limit_sell_price: -1000,
        }
        self.user_ts_names_default_settings = {}

    def get_first_delivery_start(self):
        """Get first delivery start, used as starting timestamp to fill strategy timeseries"""
        raise NotImplementedError()

    def get_last_delivery_end(self):
        """Get last delivery start, used as ending timestamp to fill strategy timeseries"""
        raise NotImplementedError()

    def load_strategy(self):  # type: (...) -> Strategy
        """Instantiate strategy object to be tested.

        The content of this method needs to be overwritten by the child, to provide a way to create a strategy object,
        of the class which should be tested.

        Example:
        >>> import own_strategies.flex_strategy_v2.custom_strategy as CS
        >>> return CS.CustomStrategy(self.autotrader, self.strategy_id, self.strategy_id, self.strategy_package_name)

        :rtype: Strategy
        """
        raise NotImplementedError()

    def _setup_epex(self):
        """initialize epex exchange"""
        config = ATCONF.EpexConfig(mock.Mock()).set_configs_from_dict(dict(autotrader_user="TRD001", password="vt"))
        self.autotrader.epex = APIEXCH.Epex(send_func=mock.Mock(), create_dummy_products=True,
                                            allowed=True, exchange_config=config)
        self.autotrader.epex.autotrader_user = "EPEX_USER"
        self.autotrader.epex._short_omt = autotrader_core.i9ntests.exchanges_mocks.RatelimitManagerStub()
        self.autotrader.epex._long_omt = autotrader_core.i9ntests.exchanges_mocks.RatelimitManagerStub()
        self.autotrader.epex.init_files_correlation_ids = {"initialized": True}

    def _setup_nordpool(self):
        """initialize nordpool exchange"""
        config = ATCONF.NordpoolConfig(mock.Mock()).set_configs_from_dict(dict(autotrader_user="TRD001", password="vt"))
        self.autotrader.nordpool = APIEXCH.NordPool(send_func=mock.Mock(), create_dummy_products=True,
                                                    allowed=True, exchange_config=config)
        self.autotrader.nordpool.autotrader_user = "NORDPOOL_USER"
        self.autotrader.nordpool.init_files_correlation_ids = {"initialized": True}

    def _setup_trayport(self):
        """initialize trayport exchange, and load inst properties, definitions and sequence information"""
        if isinstance(self.trayport_config, ATCONF.TrayportConfig):
            trayport_config = self.trayport_config
        elif isinstance(self.trayport_config, dict):
            trayport_config = ATCONF.TrayportConfig(log).set_configs_from_dict(self.trayport_config)
        else:
            trayport_config = ATCONF.TrayportConfig(log).get_defaults()
        self.autotrader.trayport = APIEXCH.Trayport(send_func=mock.Mock(), create_dummy_products=True,
                                                    allowed=True,
                                                    exchange_config=trayport_config)
        self.autotrader.trayport.autotrader_user = "TRAYPORT_USER"
        self.setup_trayport()

    def setup_trayport(self):
        NotImplementedError("Implement in Trayport specific child")

    def fill_ts(self, strat_def, ts_settings, from_ts, to_ts, is_userdefined=False):
        """fill timeseries in strategy"""
        if not is_userdefined:
            for ts_name, val in ts_settings.items():
                strat_def[ts_name] = make_value_list(from_ts, to_ts, val)
        else:
            for ts_name, val in ts_settings.items():
                strat_def["user_defined_timeseries"][ts_name] = make_value_list(from_ts, to_ts, val)
        return strat_def

    def _mock_place_slots(self, *args, **kwargs):
        placed_args = ("log_data", "product", "timestamp", "delivery_area_id", "slots",
                       "stats", "limit_minimum_sales_price", "limit_maximum_purchase_price", "execmode")
        placements = dict(list(zip(placed_args, args)))
        placements.update(kwargs)
        if "stats" in placements:
            placements["stats"] = [" ".join(placements["stats"])] * len(placements["slots"])
        self.calls.append(placements)
        return [SlotResponse(True, COMMON.SlotResponseAction.create, COMMON.SlotResponseReason.ok)] * len(
            placements["slots"])

    def get_slots_stats_by_time(self):
        quantity_vals = collections.defaultdict(lambda: collections.defaultdict(lambda: (0, 0)))
        for call in self.calls:
            for ts in range(call["product"].delivery_start, call["product"].delivery_end, 900):
                for slot in call["slots"]:
                    if slot.direction == COMMON.Direction.buy:
                        quantity_vals[(call["product"].product_id, slot.slot_type)][ts] = (slot.quantity, slot.price)
                    elif slot.direction == COMMON.Direction.sell:
                        quantity_vals[(call["product"].product_id, slot.slot_type)][ts] = (slot.quantity, slot.price)
                    else:
                        quantity_vals[(call["product"].product_id, slot.slot_type)][ts] = (slot.quantity, slot.price)
        return quantity_vals

    @staticmethod
    def shorten_placed_slots(last_placed_slots):
        """Only get the price, quantity, direction and info of :method:`last_placed_slots`

        Get the recorded place slot arguments and return them in a structured dictionary to get the calls for
        each product. Only save the

        :param last_placed_slots: dictionary of slots and stats based with product id and slot type keys
        :type last_placed_slots: dict[(str, str), autotrader_core.strategy.PositionSlot]
        :return: dictionary, with keys: (product_id, slot_name) and values: (price, quantity, direction, info)
        :rtype: dict[(str, str), (float, float, str, str)]
        """
        return {
            (product_id, slot_type): (
                float(slot.price) if slot.price is not None else None,
                float(slot.quantity) if slot.quantity is not None else None,
                slot.direction,
                slot.info
            )
            for (product_id, slot_type), slot in last_placed_slots.items()
        }

    def last_placed_slots(self):
        """Return the recorded calls of place_slots(log_data, product, timestamp, area, slots)

        Get the recorded place slot arguments and return them in a structured dictionary to get the calls for
        each product.

        :return: dictionary, with keys: (product_id, slot_name) and values: slot
        :rtype: dict[(str, str), autotrader_core.strategy.PositionSlot]
        """
        placed_slots = {
            (call["product"].product_id, slot.slot_type): slot
            for call in self.calls
            for slot in call["slots"]
        }
        return placed_slots

    def _forward(self, message):
        self.autotrader.update_from_json(message, {})

    def tearDown(self):
        self.calls = []

    def get_empty_strat_def(self, exchange, area, strategy_id, packagename):
        return {
            "active": True,
            "behavior": "BALANCED",
            "exchange_1": exchange,
            "internal_number": strategy_id,
            "market_area_1": area,
            "maximum_ask": None,
            "maximum_bid": None,
            "maximum_order_book": None,
            "packagename": packagename,
            "risk_affinity": None,
            "short_name": "TRAINING_STRAT",
            "stop_on_limit_violation": False,
            COMMON.StrategyJsonKey.TS.limit_buy_price: [],
            COMMON.StrategyJsonKey.TS.limit_buy_vol: [],
            COMMON.StrategyJsonKey.TS.limit_sell_vol: [],
            COMMON.StrategyJsonKey.TS.limit_sell_price: [],
            COMMON.StrategyJsonKey.TS.pos_sell: [],
            COMMON.StrategyJsonKey.TS.pos_buy: [],
            COMMON.StrategyJsonKey.TS.price_buy: [],
            COMMON.StrategyJsonKey.TS.price_sell: [],
            COMMON.StrategyJsonKey.TS.price_min_spread_buyback: [],
            COMMON.StrategyJsonKey.TS.price_imm_buy: [],
            COMMON.StrategyJsonKey.TS.price_imm_sell: [],
            "trading_end_before_market_closure": 0,
            "user_defined_timeseries": {},
            "valid_from": None,
            "valid_to": None
        }

    @staticmethod
    def get_empty_strat_configuration(exchange, area, strategy_id, packagename):
        return {
            "active": True,
            "exchange_1": exchange,
            "internal_number": strategy_id,
            "market_area_1": area,
            "package_name": packagename,
            "caption": "Test Strategy",
            "description": "A dummy strategy for unit tests"
        }

    def load_ts_data_into_strategy_definition(self):
        """load the defined timeseries values in self.ts_names_settings and self.user_ts_names_default_settings"""
        self.strat_def = self.fill_ts(self.strat_def, self.ts_names_settings, self.first_delivery_start,
                                      self.last_delivery_end, is_userdefined=False)
        self.strat_def = self.fill_ts(self.strat_def, self.user_ts_names_default_settings, self.first_delivery_start,
                                      self.last_delivery_end, is_userdefined=True)

    def send_strategy_data_to_autotrader(self):
        self.strategy.on_strategy_update(self.strat_def)

    def update_user_ts(self, ts_update):
        self.user_ts_names_default_settings.update(ts_update)
        self.strat_def = self.fill_ts(self.strat_def, self.user_ts_names_default_settings, self.first_delivery_start,
                                      self.last_delivery_end, is_userdefined=True)

    def update_ts(self, ts_update):
        self.ts_names_settings.update(ts_update)
        self.strat_def = self.fill_ts(self.strat_def, self.ts_names_settings, self.first_delivery_start,
                                      self.last_delivery_end, is_userdefined=False)

    def send_public_order_to_autotrader(self, ts, product_id, order_id, direction, price, quantity, **kwargs):
        defaults = {}
        if self.exchange == COMMON.Exchange.trayport:
            defaults = dict(term_format_id="1427494634", broker_id=self.broker_id)
            defaults.update(kwargs)

        self._forward(self.create_orderbook_json_msg(
            timestamp=ts, exchange=self.exchange, direction=direction,
            product_id=product_id, order_id=order_id, price=price,
            delivery_area_id=self.area_id, quantity=quantity, **defaults
        ))

    def send_own_trade_to_autotrader(self, ts, product_id, order_id, trade_id, direction, price, quantity, slot_name,
                                     **kwargs):
        defaults = {}
        if self.exchange == COMMON.Exchange.trayport:
            defaults = dict(term_format_id=None,
                            route_id='123',
                            state="ACTI",
                            aggressor=True,
                            other_user_id="COUNTERPARTY_USER_ID",
                            other_trader_id="COUNTERPARTY_TRADER_ID",
                            other_trader_name="COUNTERPARTY_TRADER_NAME",
                            other_company_id="COUNTERPARTY",
                            trader_name="AUTOTRADER_BACKTEST_USER_NAME")
            defaults.update(kwargs)

        txt = product_id + "|" + self.strategy.strategy_id + "|execmode:1|strategy_slot:" + slot_name
        self._forward(self.create_own_trade_msg(
            product_id, trade_id, order_id, txt,
            quantity, price, 1, ts, self.area_id, direction,
            **defaults)
        )

    def send_public_trade_to_autotrader(self, ts, product_id, order_id, trade_id, direction, price, quantity,
                                        **kwargs):

        self._forward(self.create_public_trade(
            product_id, trade_id, order_id,
            quantity, price, 1, ts, self.area_id, direction,
            **kwargs)
        )

    @staticmethod
    def create_orderbook_json_msg(*args, **kwargs):
        raise NotImplementedError("Implement in child")

    def create_own_trade_msg(self):
        raise NotImplementedError("Implement in child")

    @staticmethod
    def create_public_trade(*args, **kwargs):
        raise NotImplementedError("Implement in child")

    def run_strategy_and_get_placed_slots(self, ts, products):
        """Run the strategy.act once and collect all placed slots and stats

        :param ts: timestamp passed to strategy.act
        :type ts: float
        :param products: list of Products to be sent to strategy.act
        :type products: list[autotrader_core.exchange_trading.Products]

        :return: dictionary, with keys: (product_id, slot_name) and values: slot
        :rtype: dict[(str, str), autotrader_core.strategy.PositionSlot]
        """
        self.calls = []
        self.strategy.act(ts, products=products)
        return self.last_placed_slots()


class PowerTestStrategyBase(TestStrategyBase):
    def setUp(self, exchange=COMMON.Exchange.epex, area_id=COMMON.Area.rwe):
        super(PowerTestStrategyBase, self).setUp(exchange=COMMON.Exchange.epex, area_id=area_id)

    def add_product_to_epex(self, product_id, start_ts, end_ts, product_type):
        product_json = self.create_product_json([{
            "delivery_start": start_ts,
            "delivery_end": end_ts,
            "product_type": product_type,
            "product_id": product_id,
        }])

        self._forward(product_json)
        self.products = sorted(self.autotrader.epex.products.get_all(), key=lambda p: p.delivery_start)

    def create_product_json(self, product_defs):
        return {
            "data": [
                {
                    "predefined": True,
                    "delivery_end": product_def["delivery_end"],
                    "trading_phases": {
                        self.area_id: {
                            "start": product_def["delivery_start"] - 24 * COMMON.HOUR,
                            # technically wrong, but enough for the unit test
                            "state": "continuous",
                            "end": product_def["delivery_start"] - 1 * COMMON.HOUR
                        }
                    },
                    "name": CETUTIL.utc_ts2cet_dt(product_def["delivery_start"]).strftime(
                        "%H:%M") + "-" + CETUTIL.utc_ts2cet_dt(product_def["delivery_end"]).strftime("%H:%M"),
                    "delivery_start": product_def["delivery_start"],
                    "delivery_area_states": {
                        self.area_id: {
                            "state": "active"
                        },
                    },
                    "product_type": product_def["product_type"],
                    "product_id": product_def["product_id"]
                } for product_def in product_defs
            ],
            "message_type": "product",
            "timestamp": None,
            "exchange": COMMON.Exchange.epex
        }

    def create_own_trade_msg(self, product_id, trade_id, order_id, txt, quantity, price, revision, execution_time, area,
                             direction):
        return {
            "timestamp": 1,
            "data": [{
                "direction": direction,
                "product_id": product_id,
                "execution_time": execution_time,
                "price": price,
                "order_id": order_id,
                "state": "ACTI",
                "delivery_area": area,
                "trade_id": trade_id,
                "user": self.autotrader.epex.autotrader_user,
                "txt": txt,
                "revision": revision,
                "quantity": quantity}],
            "message_type": "own_trade",
            "exchange": COMMON.Exchange.epex
        }

    @staticmethod
    def create_public_trade(product_id, trade_id, order_id, quantity, price, revision, execution_time, area,
                            direction):
        return {
            "timestamp": 1,
            "data": [{
                "direction": direction,
                "product_id": product_id,
                "execution_time": execution_time,
                "price": price,
                "order_id": order_id,
                "sell_delivery_area": area,
                "buy_delivery_area": area,
                "state": "ACTIVE",
                "trade_id": trade_id,
                "revision": revision,
                "quantity": quantity}],
            "message_type": "public_trade",
            "exchange": COMMON.Exchange.epex
        }

    @staticmethod
    def create_orderbook_json_msg(timestamp=0,
                                  exchange=COMMON.Exchange.epex,
                                  direction=COMMON.Direction.sell,
                                  product_id="10491818",
                                  order_id="1085350626",
                                  price=35.0,
                                  delivery_area_id=COMMON.Area.rwe,
                                  quantity=5,
                                  revision=1):
        return {
            "synchronisation_init": False,
            "exchange": exchange,
            "data": [
                {
                    "direction": direction,
                    "product_id": product_id,
                    "order_id": order_id,
                    "price": price,
                    "delivery_area_id": delivery_area_id,
                    "quantity": quantity,
                    "revision": revision,
                }
            ],
            "message_type": "order_book",
            "timestamp": timestamp
        }


class TestWithEpexProducts(PowerTestStrategyBase):
    def setUp(self, exchange=COMMON.Exchange.epex, area_id=COMMON.Area.rwe, products_start=None, products_end=None,
              _4hour_products=True, hour_products=True, half_hour_products=True, quarter_hour_products=True):
        super(TestWithEpexProducts, self).setUp(exchange, area_id)

        ######################
        # setup base product #
        ######################

        # default setting, if nothing is passed concerning products:
        if products_start is None and products_end is None:
            self._09_10_prod_id = "1000000h"
            self._10_11_prod_id = "1000001h"

            self.add_product_to_epex(self._09_10_prod_id,
                                     self.first_delivery_start,
                                     self.first_delivery_start + COMMON.HOUR,
                                     COMMON.ProductType.ID.XBID_Hour_Power)

            self.add_product_to_epex(self._10_11_prod_id,
                                     self.first_delivery_start + COMMON.HOUR,
                                     self.first_delivery_start + 2 * COMMON.HOUR,
                                     COMMON.ProductType.ID.XBID_Hour_Power)

            ###################################
            # add base products to simulation #
            ###################################

            self.product_09_10 = self.autotrader.epex.products.get_by_id(self._09_10_prod_id)  # first hour product
            self.product_10_11 = self.autotrader.epex.products.get_by_id(self._10_11_prod_id)  # first hour product

        else:
            if products_start is None:
                products_start = self.first_delivery_start
            if products_end is None:
                products_end = self.last_delivery_end

            if hour_products:
                stepsize = COMMON.HOUR
                for idx, ts in enumerate(range(products_start, products_end, stepsize)):
                    self.add_product_to_epex(str(idx).zfill(4) + "HR",
                                             ts,
                                             ts + stepsize,
                                             COMMON.ProductType.ID.XBID_Hour_Power)

            if half_hour_products:
                stepsize = COMMON.HALF
                for idx, ts in enumerate(range(products_start, products_end, stepsize)):
                    self.add_product_to_epex(str(idx).zfill(4) + "HH",
                                             ts,
                                             ts + stepsize,
                                             COMMON.ProductType.ID.XBID_Quarter_Hour_Power)

            if quarter_hour_products:
                stepsize = COMMON.QUARTER
                for idx, ts in enumerate(range(products_start, products_end, stepsize)):
                    self.add_product_to_epex(str(idx).zfill(4) + "QH",
                                             ts,
                                             ts + stepsize,
                                             COMMON.ProductType.ID.XBID_Quarter_Hour_Power)

            if _4hour_products:
                stepsize = 4 * COMMON.HOUR

                start_cet_dt = CETUTIL.utc_ts2cet_dt(products_start)
                starting_hour = int(start_cet_dt.hour // 4 * 4)
                start_cet_dt = datetime.datetime.combine(start_cet_dt.date(), datetime.time(starting_hour))
                start_block = CETUTIL.cet_dt2int_ts(start_cet_dt)

                for idx, ts in enumerate(range(start_block, start_block + products_end - products_start, stepsize)):
                    self.add_product_to_epex(str(idx).zfill(4) + "GB4",
                                             ts,
                                             ts + stepsize,
                                             COMMON.ProductType.ID.GB_4_Hour_Power)
                    self.add_product_to_epex(str(idx).zfill(4) + "EP4",
                                             ts,
                                             ts + stepsize,
                                             COMMON.ProductType.ID.XBID_Hour_Power)


class GasTestStrategyBase(TestStrategyBase):
    longMessage = True

    inst_def_path = path("inst_definitions.jsonl")
    term_formats_path = path("term_formats.jsonl")
    sequence_items_path = path("sequence_items.jsonl")
    user_info_path = path("user_info.json")
    inst_properties_path = path("inst_properties.jsonl")

    seq_id = COMMON.SequenceId.gas_prompt
    item_id = _SEQ_ID
    sequence_ids = [seq_id]
    current_timestamp = CETUTIL.cet_dt2ts(datetime.datetime(2021, 11, 5, 11, 55))
    trayport_config = ATCONF.TrayportConfig(log).get_defaults()
    product_id_wd = COMMON.GasPromptProductId.within_day
    product_id_da = COMMON.GasPromptProductId.day_ahead

    def setUp(self, exchange=COMMON.Exchange.trayport, area_id=COMMON.Area.peg):
        super(GasTestStrategyBase, self).setUp(exchange=exchange, area_id=area_id)
        self.broker_id = self.get_broker_id()
        self.inst_specifier = self.get_inst_specifier(self.area_id, self.seq_id, self.item_id)
        self.test_prod_id = "{}_{}".format(self.seq_id, self.item_id)

        ###########################
        # setup Trayport Exchange #
        ###########################
        self.setup_trayport()
        self.term_format_id = "SIMULATION"

    def get_broker_id(self):
        raise NotImplementedError("Implement in child class")

    def _load_trayport_inst_def(self):
        """load prepared instrument definitions for trayport"""
        with open(self.inst_def_path, "r") as f:
            inst_def_json = json.loads(f.read())
        inst_def_json["timestamp"] = self.current_timestamp
        self._forward(inst_def_json)

    def _load_trayport_term_formats(self):
        """load prepared term formats for trayport"""
        term_formats_json = self.create_term_formats(self.current_timestamp)
        self._forward(term_formats_json)

    def _load_trayport_sequences(self):
        """load prepared sequences for trayport"""
        seq_item_json = self.create_trayport_sequences(self.current_timestamp)
        if self.sequence_items_path:
            with open(self.sequence_items_path, "r") as f:
                seq_item_json["data"].extend(json.loads(f.read())["data"])
        action_rate_limit_data = self.get_action_rate_limit_data()
        broker_config_data = self.get_broker_config_data()

        with mock.patch.object(self.autotrader.trayport, "_read_action_limit_file",
                               return_value=action_rate_limit_data):
            with mock.patch.object(self.autotrader.trayport, "_read_broker_spec_file",
                                   return_value=broker_config_data):
                self._forward(seq_item_json)

    def _load_trayport_user_info(self):
        """load prepared user info for trayport"""
        with open(self.user_info_path, "r") as f:
            user_info_json = json.loads(f.read())
        user_info_json["timestamp"] = self.current_timestamp
        self._forward(user_info_json)

    def _load_trayport_inst_properties(self):
        """load prepared instrument properties for trayport"""
        with open(self.inst_properties_path, "r") as f:
            inst_properties_json = list(map(json.loads, f.readlines()))
        for inst_prop in inst_properties_json:
            inst_prop["timestamp"] = self.current_timestamp
            self._forward(inst_prop)

    def _load_trayport_synthetic_products(self):
        for _, sequence in self.autotrader.trayport.trayport_sequences.items():
            self.autotrader.trayport.generate_synthetic_products(sequence, self.current_timestamp)
        self.autotrader.trayport.update_synthetic_products(self.current_timestamp)

    def setup_trayport(self):
        """setup trayport exchange and all necessary configs"""
        self._load_trayport_inst_def()
        self._load_trayport_term_formats()
        self._load_trayport_sequences()
        self._load_trayport_user_info()
        self._load_trayport_inst_properties()
        self._load_trayport_synthetic_products()

        # Fake that the exchange is initialized
        self.autotrader.trayport.init_files_correlation_ids = {"initialized": True}

        # load some products for easier reference in test
        self.product_wd = self.autotrader.trayport.products.get_by_id(self.product_id_wd)
        self.product_da = self.autotrader.trayport.products.get_by_id(self.product_id_da)
        self.products = self.autotrader.trayport.products.get_all()

        log_text = "Setup Trayport Exchange, with following products: {}".format(
            ",".join([p.name for p in self.products])
        )
        log.debug(log_text)
        print(log_text)

    def create_inst_spec(self, instrument_id=COMMON.Area.cegh, first_sequence_id=_SEQ_ID,
                         first_item_id="2", second_item_id="0",
                         sequence_span="Single", term_format_id="1234567"):
        return {"instrument_id": instrument_id,
                "first_sequence_id": first_sequence_id,
                "first_item_id": first_item_id,
                "second_item_id": second_item_id,
                "sequence_span": sequence_span,
                "term_format_id": term_format_id}

    def get_inst_specifier(self, area_id, first_sequence_id="10000302", first_item_id="2"):
        inst_specifier = self.create_inst_spec()
        inst_specifier["instrument_id"] = area_id
        inst_specifier["first_sequence_id"] = first_sequence_id
        inst_specifier["first_item_id"] = first_item_id
        return inst_specifier

    def make_inst_property_msg(self, timestamp, instrument_id='10642951', first_item_id='1',
                               term_format_id='1427494634', second_item_id='0', sequence_span='Single',
                               first_sequence_id='10000302', exchange='TRAYPORT', broker_id=COMMON.Broker.eexs,
                               aon=True, price_tick=0.025, qty_tick=10.0, min_quantity=240.0, ioc=True, fok=True):
        return {
            'timestamp': timestamp,
            'message_type': 'inst_properties',
            'data': [
                {'inst_specifier': [
                    {'instrument_id': instrument_id,
                     'first_item_id': first_item_id,
                     'term_format_id': term_format_id,
                     'second_item_id': second_item_id,
                     'sequence_span': sequence_span,
                     'first_sequence_id': first_sequence_id}
                ],
                    'broker_id': [{'value': broker_id}],
                    'properties': [{'aon': aon,
                                    'price_tick': price_tick,
                                    'qty_tick': qty_tick,
                                    'min_quantity': min_quantity,
                                    'ioc': ioc,
                                    'fok': fok}]}],
            'exchange': exchange
        }

    def create_term_formats(self, timestamp):
        return {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "term_format",
            "data": [{
                "term": [
                    {"control": [{
                        "control_type": "ComboboxString",
                        "choices": [{"choice": [{"name": "", "value": ""},
                                                {"name": "O", "value": "O"},
                                                {"name": "C", "value": "C"}]
                                     }]
                    }],
                        "label": "Open/Close Code"},
                    {"control": [{"control_type": "Text", "choices": []}], "label": "Text"},
                    {"control": [{"control_type": "Text", "choices": []}], "label": "Customer"},
                    {"control": [{"control_type": "Text", "choices": []}], "label": "Original Order Number"},
                    {"control": [{"control_type": "Text", "choices": []}], "label": "Trade Status"}
                ],
                "term_type": "Market", "term_format_id": "3115920339"},
                {"term": [], "term_type": "Market", "term_format_id": "1427494634"},
                {"term": [], "term_type": "Market", "term_format_id": "SIMULATION"}]
        }

    def create_trayport_sequences(self, timestamp):
        """First Sequence Items necessary for spot trading tests"""
        return {"timestamp": timestamp, "exchange": "TRAYPORT", "message_type": "sequence_items", "data": [
            {"delivery_end": 2051222400, "trading_start": 1009843200, "order_id": "1", "seq_id": "10000302",
             "delivery_start": 1009843200, "trading_end": 2051222400, "item_name": "WD", "item_id": "1",
             "period_weight": "1"},
            {"delivery_end": 2051222400, "trading_start": 1009843200, "order_id": "2", "seq_id": "10000302",
             "delivery_start": 1009843200, "trading_end": 2051222400, "item_name": "DA", "item_id": "2",
             "period_weight": "1"},
            {"delivery_end": 2051222400, "trading_start": 1009843200, "order_id": "3", "seq_id": "10000302",
             "delivery_start": 1009843200, "trading_end": 2051222400, "item_name": "BOW", "item_id": "3",
             "period_weight": "1"},
            {"delivery_end": 2051222400, "trading_start": 1009843200, "order_id": "4", "seq_id": "10000302",
             "delivery_start": 1009843200, "trading_end": 2051222400, "item_name": "W/END", "item_id": "4",
             "period_weight": "1"},
            {"delivery_end": 2051222400, "trading_start": 1009843200, "order_id": "5", "seq_id": "10000302",
             "delivery_start": 1009843200, "trading_end": 2051222400, "item_name": "Saturday", "item_id": "6",
             "period_weight": "1"},
            {"delivery_end": 2051222400, "trading_start": 1009843200, "order_id": "6", "seq_id": "10000302",
             "delivery_start": 1009843200, "trading_end": 2051222400, "item_name": "Sunday", "item_id": "7",
             "period_weight": "1"},
        ]}

    def get_default_action_rate_limit(self):
        return {
            COMMON.Exchange.trayport: {
                COMMON.Broker.eex: {u"action_rate_interval": 30, u"action_rate_limit": 200},
                COMMON.Broker.eexs: {u"avg_action_limit_month": 4, u"avg_pdt_action_limit_month": 2,
                                     u"action_rate_interval": 5, u"action_rate_limit": 100},
                COMMON.Broker.ice: {u"avg_action_limit_month": 4, u"avg_pdt_action_limit_month": 2}
            },
            COMMON.ActionLimits.version: u"1.0"
        }

    def get_default_broker_config(self):
        return {
            COMMON.Exchange.trayport:
                dict.fromkeys([
                    COMMON.Broker.eex, COMMON.Broker.ice, COMMON.Broker.eex_t7_uat, COMMON.Broker.eex_t7_prod
                ], {COMMON.BrokerSpecs.does_combine_public_orders: True}),
            COMMON.BrokerSpecs.version: u"1.0"
        }

    def get_action_rate_limit_data(self, action_rate_limit_update=None):
        if action_rate_limit_update is None:
            action_rate_limit_update = {}
        default = self.get_default_action_rate_limit()
        default.update(action_rate_limit_update)
        return default

    def get_broker_config_data(self, broker_config_data=None):
        if broker_config_data is None:
            broker_config_data = {}
        default = self.get_default_broker_config()
        default.update(broker_config_data)
        return default

    def create_own_trade_msg(self, product_id, trade_id, order_id, txt, quantity, price,
                             revision, timestamp, instrument_id, direction,
                             term_format_id=None, execution_time=None, route_id='123', state="ACTI", aggressor=True,
                             other_user_id="COUNTERPARTY_USER_ID", other_trader_id="COUNTERPARTY_TRADER_ID",
                             other_trader_name="COUNTERPARTY_TRADER_NAME", other_company_id="COUNTERPARTY",
                             trader_name="AUTOTRADER_BACKTEST_USER_NAME"):
        if execution_time is None:
            execution_time = timestamp
        seq_id, item_id = product_id.split("_")
        trade_data = {
            "trade_id": trade_id,
            "order_id": order_id,
            "state": state,
            "txt": txt,
            "revision": revision,
            "execution_time": execution_time,
            "product_id": product_id,
            "price": price,
            "quantity": quantity,
            "aggressor_broker_id": self.broker_id,
            "initiator_broker_id": self.broker_id,
            "aggressor_trading_account": self.broker_id,
            "initiator_trading_account": self.broker_id,
            "route_id": route_id,
            'inst_specifier': [
                {'instrument_id': instrument_id,
                 'first_item_id': item_id,
                 'term_format_id': term_format_id,
                 'second_item_id': '0',
                 'sequence_span': 'Single',
                 'first_sequence_id': seq_id}
            ],
            'terms': [{'text_type': 'double', 'description': 'A strike price', 'value': '10', 'label': 'Strike'},
                      {'text_type': 'string', 'description': 'The vintage', 'value': 'vin02', 'label': 'Vintage'}],
            'product_classification': None,
            'datetime_nanoseconds_part': None,
            'foreign_trade_id': None,
            'last_update_nanoseconds_part': None,
            'annotations': [
                {'note': [{'value': 'Trade is cleared by Clearing House X', 'label': 'ClearingHouse'}]}],
        }

        if direction == COMMON.Direction.buy:
            other_direction = COMMON.Direction.sell
        else:
            other_direction = COMMON.Direction.buy

        if aggressor:
            trade_data["aggressor_action"] = direction
            trade_data["aggressor_user_id"] = self.autotrader.trayport.autotrader_user
            trade_data["aggressor_company"] = self.autotrader.trayport.company_id
            trade_data["aggressor_company_id"] = self.autotrader.trayport.company_id
            trade_data["initiator_company"] = other_company_id
            trade_data["initiator_company_id"] = other_company_id
            trade_data["aggressor_trader_id"] = trade_id
            trade_data["aggressor_trader_name"] = trader_name
            trade_data["initiator_action"] = other_direction
            trade_data["initiator_user_id"] = other_user_id
            trade_data["initiator_trader_id"] = other_trader_id
            trade_data["initiator_trader_name"] = other_trader_name
        else:
            trade_data["initiator_action"] = direction
            trade_data["initiator_user_id"] = self.autotrader.trayport.autotrader_user
            trade_data["initiator_company"] = self.autotrader.trayport.company_id
            trade_data["initiator_company_id"] = self.autotrader.trayport.company_id
            trade_data["aggressor_company"] = other_company_id
            trade_data["aggressor_company_id"] = other_company_id
            trade_data["initiator_trader_id"] = trade_id
            trade_data["initiator_trader_name"] = trader_name
            trade_data["aggressor_action"] = other_direction
            trade_data["aggressor_user_id"] = other_user_id
            trade_data["aggressor_trader_id"] = other_trader_id
            trade_data["aggressor_trader_name"] = other_trader_name

        return {
            'timestamp': timestamp,
            'message_type': 'trade_list',
            'exchange': 'TRAYPORT',
            'data': [trade_data]
        }

    @staticmethod
    def create_orderbook_json_msg(timestamp=1627743480.564,
                                  exchange=COMMON.Exchange.trayport,
                                  direction='buy',
                                  product_id="",
                                  order_id='12345',
                                  price=5.0,
                                  delivery_area_id="",
                                  quantity=5,
                                  term_format_id='1234567',
                                  broker_id=COMMON.Broker.eexs
                                  ):
        """create json message for public orderbook"""
        seq_id, item_id = product_id.split("_")
        return {
            'timestamp': timestamp,
            'message_type': 'order_book',
            'exchange': exchange,
            'data': [
                {'trading_capacity': 'None',
                 'system_rank': '12345',
                 'broker_id': broker_id,
                 'terms': [],
                 # 'txt': 'my_order',
                 'trading_account': '',
                 'user_id': '14',
                 'decision_maker': '',
                 'old_engine_id': '1',
                 'execution_maker': 'None',
                 'product_classification': None,
                 'dea_client_id': '',
                 'state': 'ACTI',
                 'inst_specifier': [{
                     'instrument_id': delivery_area_id,
                     'first_item_id': item_id,
                     'term_format_id': term_format_id,
                     'second_item_id': '0',
                     'sequence_span': 'Single',
                     'first_sequence_id': seq_id,
                 }],
                 'type': 'O',
                 'counter_party_ok': True,
                 'old_broker_id': None,
                 'direction': direction,
                 'initial_order_id': '12345',
                 'datetime_nanoseconds_part': None,
                 'engine_id': '1',
                 'order_id': order_id,
                 'timestamp': timestamp,
                 'price': price,
                 'validity_date': None,
                 'dea': False,
                 'validity_restriction': 'NON',
                 'account': '300',
                 'is_tradable': True,
                 'liquidity_provision': False,
                 'execution_restriction': 'NON',
                 'route_id': '',
                 'implied': False,
                 'foreign_order_id': None,
                 'action': 'ADD',
                 'derivative_indicator': False,
                 'traded': False,
                 'quantity': quantity}]
        }


class TestWithTrayportProducts(GasTestStrategyBase):

    def get_broker_id(self):
        return COMMON.Broker.eexs

    def get_first_delivery_start(self):
        return int(self.product_wd.delivery_start)

    def get_last_delivery_end(self):
        return int(self.product_da.delivery_end)

    def setUp(self, exchange=COMMON.Exchange.trayport, area_id=COMMON.Area.rwe):
        super(TestWithTrayportProducts, self).setUp(exchange, area_id)
        ######################
        # setup base product #
        ######################

        # Fake that the exchange is initialized
        self.autotrader.trayport.init_files_correlation_ids = {"initialized": True}

        # load some products for easier reference in test
        self.product_wd = self.autotrader.trayport.products.get_by_id(self.product_id_wd)
        self.product_da = self.autotrader.trayport.products.get_by_id(self.product_id_da)
        self.products = self.autotrader.trayport.products.get_all()

        log_text = "Setup Trayport Exchange, with following products: {}".format(
            ",".join([p.name for p in self.products])
        )
        log.debug(log_text)
        print(log_text)

    def fill_indicators(self, start_ts=None, product_id=None):
        """
        Simulate some market activity (1 order on both sides of the order book, with history) to fill the indicators.

        At the end of the history, the public orders are: buy 500@39.5, sell 500@40.5

        :param start_ts: The timestamp when the first public order should be placed by this function.
                         (Optional, defaults to 3 hours before self.first_delivery_start)
        :type start_ts: float or None
        :param product_id: The product id of the product where indicators will be filled.
        :type product_id: str
        :return: The timestamp after the market activity has been simulated, 200 seconds after the start ts
        :rtype: float
        """
        if product_id is None:
            product_id = self.product_id_wd
        if start_ts is None:
            start_ts = self.first_delivery_start - 3 * COMMON.HOUR
        for idx in range(20):
            ts = start_ts + idx * 10
            # add public orders
            self.send_public_order_to_autotrader(
                ts=ts,
                product_id=product_id,
                order_id="o1",
                direction=COMMON.Direction.buy,
                price=30 + idx * 0.5,
                quantity=500
            )

            self.send_public_order_to_autotrader(
                ts=ts,
                product_id=product_id,
                order_id="o2",
                direction=COMMON.Direction.sell,
                price=50 - idx * 0.5,
                quantity=500
            )
        return ts

    def placed_slots_to_order_request(self):
        """
        Send the placed slots (as stored in self.calls) through the child process's send_to_exchange machinery

        This converts them to a dict of orderwishes, as would be sent to the parent process
        and may add locks to the product.

        :return: a message (as dict) that would be sent to the parent process.
        :rtype: dict
        """
        for call in self.calls:
            self.original_place_slots(**call)
        with mock.patch.object(self.autotrader, "send_to_parent") as send_to_parent_mock:
            self.autotrader.send_to_exchange(self.autotrader.trayport)
        if send_to_parent_mock.call_args:
            return send_to_parent_mock.call_args[0][0]["data"][0]
        return {}

    @staticmethod
    def to_price_quantity_by_slot(order_request_list):
        """
        Convert a list of order requests to a shorter representation.

        :param order_request_list: A  list of order request,
                                   such as self.placed_slots_to_order_request["modify_orders"]
        :type order_request_list: list
        :return: A dictionary, mapping the slot_name to a Tuple of quantity, price and internal_id
        :rtype: dict
        """
        QtyPrice = collections.namedtuple("QuantityPrice", ["quantity", "price", "internal_id"])
        QtyPrice.__str__ = lambda self: "{}@{}".format(self[0], self[1])
        by_slot = {}
        for order in order_request_list:
            slotname = order["tags"]["strategy_slot"]
            order_info = QtyPrice(order["quantity"], order["price"], order["tags"]["internal_id"])
            if slotname in by_slot:
                raise AssertionError("A duplicate slot was sent to the exchange for the strategy_slot: "
                                     "{}: {} and {}".format(slotname, by_slot[slotname], order_info))
            by_slot[slotname] = order_info
        return by_slot


if __name__ == '__main__':
    unittest.main()
