#!/usr/bin/env python
# -*- coding: utf-8 -*-
import datetime
import os
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import custom_strategy as NEW_STRATEGY
import autotrader_core.i9ntests.strategy_tests.strategy_unittest_base as SUTB


class TestWithOrderBook(SUTB.TestWithEpexProducts):
    exchange = COMMON.Exchange.epex
    area_id = COMMON.Area.rwe
    strategy_package_name = os.path.basename(os.path.dirname(__file__))

    def get_first_delivery_start(self):
        return int(CETUTIL.cet_dt2ts(datetime.datetime(2021, 4, 2, 9, 0)))

    def get_last_delivery_end(self):
        return int(CETUTIL.cet_dt2ts(datetime.datetime(2021, 4, 2, 14, 0)))

    def load_strategy(self):
        import custom_strategy as CS
        return CS.CustomStrategy(self.autotrader, self.strategy_id, self.strategy_id, self.strategy_package_name)

    def setUp(self):
        super(TestWithOrderBook, self).setUp(exchange=self.exchange, area_id=self.area_id)

    def test_01_act(self):
        """Run Strategy Act for 2 products

        In this example, only run the test and debug the strategy's custom_act,
        to follow the code and check if the strategy actually acts.
        """
        #####################
        # call strategy act #
        #####################
        # send the current self.strat_def to autotrader to setup the strategy.
        self.send_strategy_data_to_autotrader()

        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_09_10, self.product_10_11]
        )

        # check 9 to 10 product
        res_sell = placements[(self._09_10_prod_id, NEW_STRATEGY.SELL_SLOTNAME)]
        res_buy = placements[(self._09_10_prod_id, NEW_STRATEGY.BUY_SLOTNAME)]

        net_sell = '[i=sell_state:normal||trd:0.0||net_target_pos:0.0||rest:0.0||order:0.0@0.0||fronts:None//None]'
        net_buy = '[i=buy_state:normal||trd:0.0||net_target_pos:0.0||rest:0.0||order:0.0@-0.0||fronts:None//None]'

        self.assertEqual(res_sell.short(True, True), 'S_0.0@0.00 [t=sell_slot] ' + net_sell)
        self.assertEqual(res_buy.short(True, True), 'B_0.0@-0.00 [t=buy_slot] ' + net_buy)

        # check 10 to 11 product
        res_sell = placements[(self._10_11_prod_id, NEW_STRATEGY.SELL_SLOTNAME)]
        res_buy = placements[(self._10_11_prod_id, NEW_STRATEGY.BUY_SLOTNAME)]

        self.assertEqual(res_sell.short(True, True), 'S_0.0@0.00 [t=sell_slot] ' + net_sell)
        self.assertEqual(res_buy.short(True, True), 'B_0.0@-0.00 [t=buy_slot] ' + net_buy)

    def test_02_send_timeseries(self):
        """Send timeseries to the strategy, and check if information arrives in the strategy"""
        ###############################################
        # prepare timeseries and strategy definitions #
        ###############################################
        self.update_user_ts({
            "strategy_unused_value": 1,
        })
        self.update_ts({
            COMMON.StrategyJsonKey.TS.pos_sell: 12,
            COMMON.StrategyJsonKey.TS.pos_buy: 0,
            COMMON.StrategyJsonKey.TS.price_buy: 10,
            COMMON.StrategyJsonKey.TS.price_sell: 50,
        })

        self.send_strategy_data_to_autotrader()

        #####################
        # call strategy act #
        #####################
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_09_10, self.product_10_11]
        )

        #########################
        # check strategy action #
        #########################

        # check 9 to 10 product
        res_sell = placements[(self._09_10_prod_id, NEW_STRATEGY.SELL_SLOTNAME)]
        res_buy = placements[(self._09_10_prod_id, NEW_STRATEGY.BUY_SLOTNAME)]

        net = 'trd:0.0||net_target_pos:-12.0||rest:-12.0||'

        self.assertEqual(res_sell.short(True, True),
                         'S_12.0@50.00 [t=sell_slot] [i=sell_state:normal||'
                         + net + 'order:12.0@50.0||fronts:None//None]')
        self.assertEqual(res_buy.short(True, True),
                         'B_0.0@-0.00 [t=buy_slot] [i=buy_state:normal||'
                         + net + 'order:0.0@-0.0||fronts:None//None]')

        # check 10 to 11 product
        res_sell = placements[(self._10_11_prod_id, NEW_STRATEGY.SELL_SLOTNAME)]
        res_buy = placements[(self._10_11_prod_id, NEW_STRATEGY.BUY_SLOTNAME)]

        net = 'trd:0.0||net_target_pos:-12.0||rest:-12.0||'

        self.assertEqual(res_sell.short(True, True),
                         'S_12.0@50.00 [t=sell_slot] [i=sell_state:normal||'
                         + net + 'order:12.0@50.0||fronts:None//None]')
        self.assertEqual(res_buy.short(True, True),
                         'B_0.0@-0.00 [t=buy_slot] [i=buy_state:normal||'
                         + net + 'order:0.0@-0.0||fronts:None//None]')

    def test_03_with_public_orderbook(self):
        """Simulate public orders in the orderbook and check strategy reaction given on this situation"""
        ###############################################
        # prepare timeseries and strategy definitions #
        ###############################################
        self.update_user_ts({
            "strategy_unused_value": 1,
        })
        self.update_ts({
            COMMON.StrategyJsonKey.TS.pos_sell: 12,
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

        self.send_public_order_to_autotrader(
            ts=ts,
            product_id=self._09_10_prod_id,
            order_id="o1" + self._09_10_prod_id,
            direction=COMMON.Direction.buy,
            price=30,
            quantity=5
        )

        self.send_public_order_to_autotrader(
            ts=ts,
            product_id=self._09_10_prod_id,
            order_id="o2" + self._09_10_prod_id,
            direction=COMMON.Direction.sell,
            price=50,
            quantity=5
        )

        #####################
        # call strategy act #
        #####################
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_09_10, self.product_10_11]
        )

        #########################
        # check strategy action #
        #########################

        # check 9 to 10 product
        res_sell = placements[(self._09_10_prod_id, NEW_STRATEGY.SELL_SLOTNAME)]
        res_buy = placements[(self._09_10_prod_id, NEW_STRATEGY.BUY_SLOTNAME)]

        net = 'trd:0.0||net_target_pos:-12.0||rest:-12.0||'

        self.assertEqual(res_sell.short(True, True),
                         'S_12.0@50.00 [t=sell_slot] [i=sell_state:normal||'
                         + net + 'order:12.0@50.0||fronts:30.0//50.0]')
        self.assertEqual(res_buy.short(True, True),
                         'B_0.0@-0.00 [t=buy_slot] [i=buy_state:normal||'
                         + net + 'order:0.0@-0.0||fronts:30.0//50.0]')

        # check 10 to 11 product
        res_sell = placements[(self._10_11_prod_id, NEW_STRATEGY.SELL_SLOTNAME)]
        res_buy = placements[(self._10_11_prod_id, NEW_STRATEGY.BUY_SLOTNAME)]

        net = 'trd:0.0||net_target_pos:-12.0||rest:-12.0||'

        self.assertEqual(res_sell.short(True, True),
                         'S_12.0@50.00 [t=sell_slot] [i=sell_state:normal||'
                         + net + 'order:12.0@50.0||fronts:None//None]')
        self.assertEqual(res_buy.short(True, True),
                         'B_0.0@-0.00 [t=buy_slot] [i=buy_state:normal||'
                         + net + 'order:0.0@-0.0||fronts:None//None]')

    def test_04_with_own_trades(self):
        """Simulate own trades, to check whether strategy can close left-over positions"""
        ###############################################
        # prepare timeseries and strategy definitions #
        ###############################################
        self.update_user_ts({
            "strategy_unused_value": 1,
        })
        self.update_ts({
            COMMON.StrategyJsonKey.TS.pos_sell: 12,
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

        self.send_public_order_to_autotrader(
            ts=ts,
            product_id=self._09_10_prod_id,
            order_id="o1" + self._09_10_prod_id,
            direction=COMMON.Direction.buy,
            price=30,
            quantity=5
        )

        self.send_public_order_to_autotrader(
            ts=ts,
            product_id=self._09_10_prod_id,
            order_id="o2" + self._09_10_prod_id,
            direction=COMMON.Direction.sell,
            price=50,
            quantity=5
        )

        ################################
        # setup already traded amounts #
        ################################
        execution_time = self.first_delivery_start - COMMON.HOUR * 2

        self.send_own_trade_to_autotrader(
            ts=execution_time,
            product_id=self._09_10_prod_id,
            order_id="o1",
            trade_id="1",
            direction=COMMON.Direction.buy,
            price=20,
            quantity=10,
            slot_name=NEW_STRATEGY.BUY_SLOTNAME
        )

        self.send_own_trade_to_autotrader(
            ts=execution_time,
            product_id=self._10_11_prod_id,
            order_id="o2",
            trade_id="2",
            direction=COMMON.Direction.sell,
            price=20,
            quantity=5,
            slot_name=NEW_STRATEGY.SELL_SLOTNAME
        )

        #####################
        # call strategy act #
        #####################
        # strat on custom act
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_09_10, self.product_10_11]
        )

        #########################
        # check strategy action #
        #########################

        # check 9 to 10 product
        res_sell = placements[(self._09_10_prod_id, NEW_STRATEGY.SELL_SLOTNAME)]
        res_buy = placements[(self._09_10_prod_id, NEW_STRATEGY.BUY_SLOTNAME)]

        net = 'trd:10.0||net_target_pos:-12.0||rest:-22.0||'

        self.assertEqual(res_sell.short(True, True),
                         'S_22.0@50.00 [t=sell_slot] [i=sell_state:normal||'
                         + net + 'order:22.0@50.0||fronts:30.0//50.0]')
        self.assertEqual(res_buy.short(True, True),
                         'B_0.0@-0.00 [t=buy_slot] [i=buy_state:normal||'
                         + net + 'order:0.0@-0.0||fronts:30.0//50.0]')

        # check 10 to 11 product
        res_sell = placements[(self._10_11_prod_id, NEW_STRATEGY.SELL_SLOTNAME)]
        res_buy = placements[(self._10_11_prod_id, NEW_STRATEGY.BUY_SLOTNAME)]

        net = 'trd:-5.0||net_target_pos:-12.0||rest:-7.0||'

        self.assertEqual(res_sell.short(True, True),
                         'S_7.0@50.00 [t=sell_slot] [i=sell_state:normal||'
                         + net + 'order:7.0@50.0||fronts:None//None]')
        self.assertEqual(res_buy.short(True, True),
                         'B_0.0@-0.00 [t=buy_slot] [i=buy_state:normal||'
                         + net + 'order:0.0@-0.0||fronts:None//None]')


if __name__ == '__main__':
    unittest.main()
