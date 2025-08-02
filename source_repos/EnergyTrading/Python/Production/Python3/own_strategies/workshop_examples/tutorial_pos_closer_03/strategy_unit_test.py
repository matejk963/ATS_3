#!/usr/bin/python3
# -*- coding: utf-8 -*-

import datetime
import os
import unittest
import custom_strategy as CS
import autotrader_lib.common as COMMON
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


if __name__ == '__main__':
    unittest.main()
