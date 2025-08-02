#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task to write unit test, setting up orderbook

Fill in all the gaps marked with "# TASK"

"""
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
        self.send_strategy_data_to_autotrader()

        #########################
        # fill public orderbook #
        #########################

        # TASK: Task: send 2 public orders to autotrader, for the product with id: self._09_10_prod_id
        # 1 order: buy, 30€, 5MW
        # 1 order: sell, 50€, 5MW

        #####################
        # call strategy act #
        #####################

        # TASK: Task: run strategy act with "run_strategy_and_get_placed_slots"

        #########################
        # check strategy action #
        #########################

        # TASK: Task: check slots
        # remember that the slotname in the strategy is "front"

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
