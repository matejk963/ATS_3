#!/usr/bin/python3
# -*- coding: utf-8 -*-
import datetime
import os
import unittest
import custom_strategy as CS
import autotrader_lib.common as COMMON
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
        # TASK: Task: modify the timeseries here and transfer

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

        #####################
        # call strategy act #
        #####################
        placements = self.run_strategy_and_get_placed_slots(
            self.first_delivery_start - (3 * COMMON.HOUR + 5 * COMMON.MINUTE),
            [self.product_09_10, self.product_10_11]
        )
        # check 9 to 10 product
        self.assertEqual(len(placements), 1)
        slot1 = placements[(self._09_10_prod_id, "front")]

        self.assertEqual(slot1.short(True, True), 'S_0.1@30.00 [t=front] [i=placement_info]')

    def get_first_delivery_start(self):
        return int(CETUTIL.cet_dt2ts(datetime.datetime(2021, 4, 2, 9, 0)))

    def get_last_delivery_end(self):
        return int(CETUTIL.cet_dt2ts(datetime.datetime(2021, 4, 2, 14, 0)))

    def load_strategy(self):
        return CS.CustomStrategy(self.autotrader, self.strategy_id, self.strategy_id, self.strategy_package_name)

    def setUp(self):
        super(TestWithOrderBook, self).setUp(exchange=self.exchange, area_id=self.area_id)


if __name__ == '__main__':
    unittest.main()
