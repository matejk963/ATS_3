#!/usr/bin/env python
# -*- coding: utf-8 -*-
import datetime
import os
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import autotrader_core.i9ntests.strategy_tests.strategy_unittest_base as SUTB


class TestPosCloser(SUTB.TestWithEpexProducts):
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
        super(TestPosCloser, self).setUp(exchange=self.exchange, area_id=self.area_id)

    def test(self):
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

        pos_long_09_10 = self.strategy.strategy_position_tradable_position_long.get(
            (self.product_09_10.delivery_start, self.product_09_10.delivery_end)
        )
        pos_short_09_10 = self.strategy.strategy_position_tradable_position_short.get(
            (self.product_09_10.delivery_start, self.product_09_10.delivery_end)
        )
        prc_buy_09_10 = self.strategy.strategy_price_purchase.get(
            (self.product_09_10.delivery_start, self.product_09_10.delivery_end)
        )
        prc_sell_09_10 = self.strategy.strategy_price_sales.get(
            (self.product_09_10.delivery_start, self.product_09_10.delivery_end)
        )

        self.assertEqual(pos_long_09_10, 12)
        self.assertEqual(pos_short_09_10, 0)
        self.assertEqual(prc_buy_09_10, 10)
        self.assertEqual(prc_sell_09_10, 50)

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
        # strat on custom act
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_09_10, self.product_10_11]
        )

        #########################
        # check strategy action #
        #########################

        # check exactly 2 placed slots, since each product should have 1
        self.assertEqual(len(placements), 2)

        # check 9 to 10 product
        placed_slot = placements[(self._09_10_prod_id, "front")]
        self.assertEqual(
            placed_slot.short(True, True),
            "S_0.1@49.90 [t=front] [i=net_target_pos: -22.0|| fronts: 30.0//50.0]"
        )

        # check 10 to 11 product
        placed_slot = placements[(self._10_11_prod_id, "front")]
        self.assertEqual(
            placed_slot.short(True, True),
            "S_0.1@50.00 [t=front] [i=net_target_pos: -7.0|| fronts: None//None]"
        )


if __name__ == '__main__':
    unittest.main()
