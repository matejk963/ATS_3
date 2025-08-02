#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
This file is for reference to find examples how to run unittests for PEG or TTF Spot Gas Strategies

In here you can find examples on how to:
- start a strategy
- add timeseries to the strategy
- add public orders, to simulate market conditions
- add own trades, to simulate reaction to left-over positions

Each gas Strategy Test class has to define a few methods,
so that the base class can find the correct values to initialize:
- get_broker_id: broker for this simulation, used when inserting orders and trades
- get_package_name: folder name, where the strategy is in
- get_first_delivery_start: first timestamp to simulate, this is important for filling the timeseries in the strategy
- get_last_delivery_end: last timestamp to simulate, this is important for filling the timeseries in the strategy
- load_strategy: load here the CustomStrategy class of the strategy module you want to simulate
"""

import os
import unittest
import custom_strategy
import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import autotrader_core.i9ntests.strategy_tests.strategy_unittest_base as SUTB

SELL_SLOTNAME = "sell_slot"
BUY_SLOTNAME = "buy_slot"


class TestStratStoragePEG(SUTB.TestWithTrayportProducts):
    """Test for Gas Strategy Development Training

    The base class takes care of setting up autotrader with a trayport exchange,
    and set some properties ad instant definitions to trade with.

    2 products available are:
    - WD-Product: Nov 5th, 15:00- Nov 6th, 06:00
    - DA-Product: Nov 6th, 06:00- Nov 7th, 06:00

    the first timestamp to be run is set to about 11:55

    Area is PEG, code: '10642951'

    With each test, the flow and calls of code in the strategy should be followed and understood.
    Apart from Strategy, the goal is also to be able to setup a specific situation,
    and check how the strategy would place slots in that situation with:
    - given timeseries by periotheus
    - public orderbook
    - already made own-trades

    after the strategy-act is called, these test should teach how to check the placed slots,
    to verify strategy behaviour
    """
    strategy_package_name = os.path.basename(os.path.dirname(__file__))

    def get_broker_id(self):
        return COMMON.Broker.eexs

    def get_first_delivery_start(self):
        return int(self.product_wd.delivery_start)

    def get_last_delivery_end(self):
        return int(self.product_da.delivery_end)

    def load_strategy(self):
        return custom_strategy.CustomStrategy(
            self.autotrader, self.strategy_id, self.strategy_id, self.strategy_package_name
        )

    def setUp(self):
        super(TestStratStoragePEG, self).setUp(exchange=COMMON.Exchange.trayport, area_id=COMMON.Area.ttf)

        print("simulation duration from wd delivery start: {} ({}) to da delivery end: {}({})".format(
            self.product_wd.delivery_start, CETUTIL.utc_ts2cet_str(self.product_wd.delivery_start, True, True),
            self.product_da.delivery_end, CETUTIL.utc_ts2cet_str(self.product_da.delivery_end, True, True)
        ))

    def test_01_act(self):
        """Run Strategy Act for 2 products"""
        #####################
        # call strategy act #
        #####################
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_wd, self.product_da]
        )
        # check 9 to 10 product
        self.assertEqual(len(placements), 0)

    def test_02_send_timeseries(self):
        """Send timeseries to the strategy, and check if information arrives in the strategy"""

        ###############################################
        # prepare timeseries and strategy definitions #
        ###############################################
        self.update_user_ts({
            "strategy_unused_value": 1,
        })
        self.update_ts({
            COMMON.StrategyJsonKey.TS.pos_sell: 720,
            COMMON.StrategyJsonKey.TS.pos_buy: 0,
            COMMON.StrategyJsonKey.TS.price_buy: 10,
            COMMON.StrategyJsonKey.TS.price_sell: 50,
        })

        self.send_strategy_data_to_autotrader()

        #####################
        # call strategy act #
        #####################
        # run first callback 3 hours before first product delivery start
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_wd, self.product_da]
        )
        slot_by_prod_and_name = self.shorten_placed_slots(placements)

        #########################
        # check strategy action #
        #########################

        # validate placed slots
        res_sell = slot_by_prod_and_name[(self.product_id_wd, SELL_SLOTNAME)]
        res_buy = slot_by_prod_and_name[(self.product_id_wd, BUY_SLOTNAME)]

        self.assertEqual(res_sell, (
            50.0, 720., "sell",
            "sell_state:normal||trd:0.0||net_target_pos:-720.0||rest:-720.0||fronts:None//None"))
        self.assertEqual(res_buy, (
            0.0, 0.0, "buy",
            'buy_state:normal||trd:0.0||net_target_pos:-720.0||rest:-720.0||fronts:None//None'))

        res_sell = slot_by_prod_and_name[(self.product_id_da, SELL_SLOTNAME)]
        res_buy = slot_by_prod_and_name[(self.product_id_da, BUY_SLOTNAME)]

        self.assertEqual(res_sell, (
            50.0, 720., "sell",
            "sell_state:normal||trd:0.0||net_target_pos:-720.0||rest:-720.0||fronts:None//None"))
        self.assertEqual(res_buy, (
            0.0, 0.0, "buy",
            'buy_state:normal||trd:0.0||net_target_pos:-720.0||rest:-720.0||fronts:None//None'))

    def test_03_with_public_orderbook(self):
        """Simulate public orders in the orderbook and check strategy reaction given on this situation"""

        ###############################################
        # prepare timeseries and strategy definitions #
        ###############################################
        self.update_user_ts({
            "strategy_unused_value": 1,
        })
        self.update_ts({
            COMMON.StrategyJsonKey.TS.pos_sell: 720,
            COMMON.StrategyJsonKey.TS.pos_buy: 0,
            COMMON.StrategyJsonKey.TS.price_buy: 10,
            COMMON.StrategyJsonKey.TS.price_sell: 50,
        })

        self.send_strategy_data_to_autotrader()

        #########################
        # fill public orderbook #
        #########################
        # run first callback 3 hours before first product delivery start
        ts = self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE)
        # add public orders
        self.send_public_order_to_autotrader(
            ts=ts,
            product_id=self.product_id_wd,
            order_id="o1",
            direction=COMMON.Direction.buy,
            price=30,
            quantity=500
        )

        self.send_public_order_to_autotrader(
            ts=ts,
            product_id=self.product_id_wd,
            order_id="o2",
            direction=COMMON.Direction.sell,
            price=50,
            quantity=500
        )
        #####################
        # call strategy act #
        #####################
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_wd, self.product_da]
        )
        slot_by_prod_and_name = self.shorten_placed_slots(placements)

        #########################
        # check strategy action #
        #########################

        res_sell = slot_by_prod_and_name[(self.product_id_wd, SELL_SLOTNAME)]
        res_buy = slot_by_prod_and_name[(self.product_id_wd, BUY_SLOTNAME)]

        self.assertEqual(res_sell, (
            50.0, 720., "sell",
            "sell_state:normal||trd:0.0||net_target_pos:-720.0||rest:-720.0||fronts:30.0//50.0"))
        self.assertEqual(res_buy, (
            0.0, 0.0, "buy",
            "buy_state:normal||trd:0.0||net_target_pos:-720.0||rest:-720.0||fronts:30.0//50.0"))

        res_sell = slot_by_prod_and_name[(self.product_id_da, SELL_SLOTNAME)]
        res_buy = slot_by_prod_and_name[(self.product_id_da, BUY_SLOTNAME)]

        self.assertEqual(res_sell, (
            50.0, 720., "sell",
            "sell_state:normal||trd:0.0||net_target_pos:-720.0||rest:-720.0||fronts:None//None"))
        self.assertEqual(res_buy, (
            0.0, 0.0, "buy",
            "buy_state:normal||trd:0.0||net_target_pos:-720.0||rest:-720.0||fronts:None//None"))

    def test_04_with_own_trades(self):
        """Simulate own trades, to check whether strategy can close left-over positions"""

        ###############################################
        # prepare timeseries and strategy definitions #
        ###############################################
        self.update_user_ts({
            "strategy_unused_value": 1,
        })
        self.update_ts({
            COMMON.StrategyJsonKey.TS.pos_sell: 720,
            COMMON.StrategyJsonKey.TS.pos_buy: 0,
            COMMON.StrategyJsonKey.TS.price_buy: 10,
            COMMON.StrategyJsonKey.TS.price_sell: 50,
        })

        self.send_strategy_data_to_autotrader()

        #########################
        # fill public orderbook #
        #########################
        # run first callback 3 hours before first product delivery start
        ts = self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE)

        # add public orders
        self.send_public_order_to_autotrader(
            ts=ts,
            product_id=self.product_id_wd,
            order_id="o1",
            direction=COMMON.Direction.buy,
            price=30,
            quantity=500
        )

        self.send_public_order_to_autotrader(
            ts=ts,
            product_id=self.product_id_wd,
            order_id="o2",
            direction=COMMON.Direction.sell,
            price=50,
            quantity=500
        )

        ################################
        # setup already traded amounts #
        ################################

        self.send_own_trade_to_autotrader(
            ts=ts,
            product_id=self.product_id_wd,
            order_id="o1",
            trade_id="t1",
            direction=COMMON.Direction.buy,
            price=20,
            quantity=480,
            slot_name=BUY_SLOTNAME,
            term_format_id=self.term_format_id,
        )

        self.send_own_trade_to_autotrader(
            ts=ts,
            product_id=self.product_id_da,
            order_id="o2",
            trade_id="t2",
            direction=COMMON.Direction.sell,
            price=20,
            quantity=240,
            slot_name=SELL_SLOTNAME,
            term_format_id=self.term_format_id,
        )

        #####################
        # call strategy act #
        #####################
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_wd, self.product_da]
        )
        slot_by_prod_and_name = self.shorten_placed_slots(placements)

        #########################
        # check strategy action #
        #########################

        res_sell = slot_by_prod_and_name[(self.product_id_wd, SELL_SLOTNAME)]
        res_buy = slot_by_prod_and_name[(self.product_id_wd, BUY_SLOTNAME)]

        self.assertEqual(
            res_sell,
            (
                50.0, 1200.0, "sell",
                "sell_state:normal||trd:480.0||net_target_pos:-720.0||rest:-1200.0||fronts:30.0//50.0"
            )
        )
        self.assertEqual(res_buy, (
            0.0, 0.0, "buy",
            "buy_state:normal||trd:480.0||net_target_pos:-720.0||rest:-1200.0||fronts:30.0//50.0"))

        res_sell = slot_by_prod_and_name[(self.product_id_da, SELL_SLOTNAME)]
        res_buy = slot_by_prod_and_name[(self.product_id_da, BUY_SLOTNAME)]

        self.assertEqual(res_sell, (
            50.0, 480.0, "sell",
            "sell_state:normal||trd:-240.0||net_target_pos:-720.0||rest:-480.0||fronts:None//None"))
        self.assertEqual(res_buy, (
            0.0, 0.0, "buy",
            "buy_state:normal||trd:-240.0||net_target_pos:-720.0||rest:-480.0||fronts:None//None"))


class TestStratStorageTTF(SUTB.TestWithTrayportProducts):
    strategy_package_name = os.path.basename(os.path.dirname(__file__))

    def get_broker_id(self):
        return COMMON.Broker.eexs

    def get_first_delivery_start(self):
        return int(self.product_wd.delivery_start)

    def get_last_delivery_end(self):
        return int(self.product_da.delivery_end)

    def load_strategy(self):
        return custom_strategy.CustomStrategy(
            self.autotrader, self.strategy_id, self.strategy_id, self.strategy_package_name
        )

    def setUp(self):
        super(TestStratStorageTTF, self).setUp(exchange=COMMON.Exchange.trayport, area_id=COMMON.Area.ttf)

        print(("simulation duration from wd delivery start: {} ({}) to da delivery end: {}({})".format(
            self.product_wd.delivery_start, CETUTIL.utc_ts2cet_str(self.product_wd.delivery_start, True, True),
            self.product_da.delivery_end, CETUTIL.utc_ts2cet_str(self.product_da.delivery_end, True, True)
        )))

    def test_01_act(self):
        """TTF can place slots smaller than 240MW"""
        ###############################################
        # prepare timeseries and strategy definitions #
        ###############################################
        self.update_user_ts({
            "strategy_unused_value": 1,
        })
        self.update_ts({
            COMMON.StrategyJsonKey.TS.pos_sell: 12,
            COMMON.StrategyJsonKey.TS.pos_buy: 0,
            COMMON.StrategyJsonKey.TS.price_buy: 10.025,
            COMMON.StrategyJsonKey.TS.price_sell: 50.025,
        })

        self.send_strategy_data_to_autotrader()

        #####################
        # call strategy act #
        #####################
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_wd, self.product_da]
        )
        slot_by_prod_and_name = self.shorten_placed_slots(placements)

        #########################
        # check strategy action #
        #########################

        res_sell = slot_by_prod_and_name[(self.product_id_wd, SELL_SLOTNAME)]
        res_buy = slot_by_prod_and_name[(self.product_id_wd, BUY_SLOTNAME)]

        self.assertEqual(res_sell, (
            50.025, 12.0, "sell",
            "sell_state:normal||trd:0.0||net_target_pos:-12.0||rest:-12.0||fronts:None//None"))
        self.assertEqual(res_buy, (
            0.0, 0.0, "buy",
            "buy_state:normal||trd:0.0||net_target_pos:-12.0||rest:-12.0||fronts:None//None"))

        res_sell = slot_by_prod_and_name[(self.product_id_da, SELL_SLOTNAME)]
        res_buy = slot_by_prod_and_name[(self.product_id_da, BUY_SLOTNAME)]

        self.assertEqual(res_sell, (
            50.025, 12.0, "sell",
            "sell_state:normal||trd:0.0||net_target_pos:-12.0||rest:-12.0||fronts:None//None"))
        self.assertEqual(res_buy, (
            0.0, 0.0, "buy",
            "buy_state:normal||trd:0.0||net_target_pos:-12.0||rest:-12.0||fronts:None//None"))


if __name__ == '__main__':
    unittest.main()
