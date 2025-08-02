#!/usr/bin/env python
# -*- coding: utf-8 -*-
import datetime
import os
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import autotrader_core.i9ntests.strategy_tests.strategy_unittest_base as SUTB


class TestWithOrderBook(SUTB.TestWithEpexProducts):
    exchange = COMMON.Exchange.epex
    area_id = COMMON.Area.rwe
    strategy_package_name = os.path.basename(os.path.dirname(__file__))

    def test(self):
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

        # add public orders
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
            slot_name="front"
        )

        self.send_own_trade_to_autotrader(
            ts=execution_time,
            product_id=self._10_11_prod_id,
            order_id="o2",
            trade_id="2",
            direction=COMMON.Direction.sell,
            price=20,
            quantity=5,
            slot_name="front"
        )

        #####################
        # call strategy act #
        #####################
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_09_10, self.product_10_11]
        )
        slot_by_prod_and_name = self.shorten_placed_slots(placements)

        #########################
        # check strategy action #
        #########################

        self.assertEqual(len(slot_by_prod_and_name), 4)

        # check 9 to 10 product
        buy_slot_09_10 = slot_by_prod_and_name[(self._09_10_prod_id, "buy")]
        sell_slot_09_10 = slot_by_prod_and_name[(self._09_10_prod_id, "sell")]
        self.assertEqual(buy_slot_09_10, (10.0, 0.0, 'buy', 'placement_info'))
        self.assertEqual(sell_slot_09_10, (50.0, 22.0, 'sell', 'placement_info'))

        # check 10 to 11 product
        buy_slot_10_11 = slot_by_prod_and_name[(self._10_11_prod_id, "buy")]
        sell_slot_10_11 = slot_by_prod_and_name[(self._10_11_prod_id, "sell")]
        self.assertEqual(buy_slot_10_11, (10.0, 0.0, 'buy', 'placement_info'))
        self.assertEqual(sell_slot_10_11, (50.0, 7.0, 'sell', 'placement_info'))

    def get_first_delivery_start(self):
        return int(CETUTIL.cet_dt2ts(datetime.datetime(2021, 4, 2, 9, 0)))

    def get_last_delivery_end(self):
        return int(CETUTIL.cet_dt2ts(datetime.datetime(2021, 4, 2, 14, 0)))

    def load_strategy(self):
        import custom_strategy as CS
        return CS.CustomStrategy(self.autotrader, self.strategy_id, self.strategy_id, self.strategy_package_name)

    def setUp(self):
        super(TestWithOrderBook, self).setUp(exchange=self.exchange, area_id=self.area_id)


if __name__ == '__main__':
    unittest.main()
