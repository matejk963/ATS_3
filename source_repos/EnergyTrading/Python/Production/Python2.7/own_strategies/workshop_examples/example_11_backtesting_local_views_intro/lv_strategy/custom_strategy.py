#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Strategy to test local views"""
import datetime

import collections

import autotrader_core.strategy as STRAT
import logging
import autotrader_synthetic.local_view as LV

log = logging.getLogger('autotrader.example_11.lv_strategy')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log

    def on_strategy_update(self, strategy_json):
        # Example strategy_json input (given as POST data):
        # -------------------------------------------------
        #
        #     "test_lv": {
        #         "product_id": "dummy_10000302_1_20210601-20",
        #         "delivery_area": "10002146",
        #         "from_dt": "2021-06-08 05:00:00",
        #         "to_dt": "2022-06-09 05:00:00",
        #         "broker_id": "20",
        #         ...
        #     }

        if "test_lv" in strategy_json:

            lv_params = strategy_json.get("test_lv")
            test_prod_id = lv_params.get("product_id", "")
            product = self.exchange.products.get_by_id(test_prod_id)
            if not product:
                self.warn_log("Could not find product with ID: {}".format(test_prod_id))
            delivery_area_id = lv_params.get("delivery_area")
            from_dt_str = lv_params.get("from_dt")
            from_dt = datetime.datetime.strptime(from_dt_str, "%Y-%m-%d %H:%M:%S") if from_dt_str else None
            to_dt_str = lv_params.get("to_dt")
            to_dt = datetime.datetime.strptime(to_dt_str, "%Y-%m-%d %H:%M:%S") if to_dt_str else None
            direction = lv_params.get("direction")
            broker_id = lv_params.get("broker_id")

            at_volume_val = lv_params.get("at_volume")
            at_volume = float(at_volume_val) if at_volume_val is not None else None
            only_tradable_str = str(lv_params.get("only_tradable"))
            only_tradable = (only_tradable_str.lower() == "true") if isinstance(only_tradable_str, str) else None

            test_local_view = LV.LocalView(product=product,
                                           market_area=delivery_area_id,
                                           strategy_id="LV_TEST")
            test_local_view.get_trade_statistics(from_dt=from_dt, to_dt=to_dt, broker_id=broker_id)
            self.debug_log("LOCAL_VIEW: {}".format(repr(test_local_view)), product)

            results = {
                "cop_buy": None,
                "cop_sell": None,
                "cod_buy": None,
                "cod_sell": None,
                "cfp_buy": None,
                "cfp_sell": None,
                "cf_buy": None,
                "cf_sell": None,
                "pf_buy": None,
                "pf_sell": None,
                "cfps": None,
                "cfopc_buy": None,
                "cfopc_sell": None
            }

            if not direction:
                results["cop_buy"] = test_local_view.current_order_price(direction="buy", at_volume=at_volume,
                                                                         broker_id=broker_id,
                                                                         only_tradable=only_tradable)
                results["cop_sell"] = test_local_view.current_order_price(direction="sell", at_volume=at_volume,
                                                                          broker_id=broker_id,
                                                                          only_tradable=only_tradable)
                results["cod_buy"] = test_local_view.current_orders_depth(direction="buy", broker_id=broker_id,
                                                                          only_tradable=False)
                results["cod_sell"] = test_local_view.current_orders_depth(direction="sell", broker_id=broker_id,
                                                                           only_tradable=False)
                results["cfp_buy"] = test_local_view.current_front_price(direction="buy", broker_id=broker_id,
                                                                         only_tradable=only_tradable)
                results["cfp_sell"] = test_local_view.current_front_price(direction="sell", broker_id=broker_id,
                                                                          only_tradable=only_tradable)
                results["cf_buy"] = test_local_view.current_front_buy_price(broker_id=broker_id)
                results["cf_sell"] = test_local_view.current_front_sell_price(broker_id=broker_id)
                results["pf_buy"] = test_local_view.previous_front_buy_price(broker_id=broker_id)
                results["pf_sell"] = test_local_view.previous_front_sell_price(broker_id=broker_id)
                results["cfps"] = test_local_view.current_front_price_spread(broker_id=broker_id)

                results["cfopc_buy"] = test_local_view.current_front_order_price_change(direction="buy",
                                                                                        broker_id=broker_id)
                results["cfopc_sell"] = test_local_view.current_front_order_price_change(direction="sell",
                                                                                         broker_id=broker_id)
            else:
                results["cop_" + direction] = test_local_view.current_order_price(direction=direction,
                                                                                  at_volume=at_volume,
                                                                                  broker_id=broker_id,
                                                                                  only_tradable=only_tradable)
                results["cod_" + direction] = test_local_view.current_orders_depth(direction=direction,
                                                                                   broker_id=broker_id,
                                                                                   only_tradable=False)
                results["cfp_" + direction] = test_local_view.current_front_price(direction=direction,
                                                                                  broker_id=broker_id,
                                                                                  only_tradable=only_tradable)
                results["cf_" + direction] = getattr(test_local_view, "current_front_{}_price".format(direction))(
                    broker_id=broker_id)
                results["pf_" + direction] = getattr(test_local_view, "previous_front_{}_price".format(direction))(
                    broker_id=broker_id)
                results["cfps"] = test_local_view.current_front_price_spread(broker_id=broker_id)

                results["cfopc_" + direction] = test_local_view.current_front_order_price_change(direction=direction,
                                                                                                 broker_id=broker_id)
            indicator = test_local_view._product.orders.indicators(test_local_view._market_area)
            self.debug_log("lv buffer item types: {}".format([type(b) for b in indicator.last_front_buy_orders]),
                           product)
            self.debug_log("LOCAL_VIEW FRONT BUFFER BUY: {}".format([
                (getattr(b, "quantity", None), getattr(b, "price", None)) for b in indicator.last_front_buy_orders]),
                product)
            self.debug_log("LOCAL_VIEW FRONT BUFFER SELL: {}".format([
                (getattr(s, "quantity", None), getattr(s, "price", None)) for s in indicator.last_front_sell_orders]),
                product)
            self.debug_log("LOCAL_VIEW METRICS JSON:\n {}".format(collections.OrderedDict(
                [
                    ("current_order_price - BUY", results["cop_buy"]),
                    ("current_front_price - BUY", results["cfp_buy"]),
                    ("current_front_buy_price", results["cf_buy"]),
                    ("previous_front_buy_price", results["pf_buy"]),
                    ("current_front_order_price_change - BUY", results["cfopc_buy"]),
                    ("current_orders_depth - BUY", results["cod_buy"]),
                    ("current_order_price - SELL", results["cop_sell"]),
                    ("current_front_price - SELL", results["cfp_sell"]),
                    ("current_front_sell_price", results["cf_sell"]),
                    ("previous_front_sell_price", results["pf_sell"]),
                    ("current_front_order_price_change - SELL", results["cfopc_sell"]),
                    ("current_orders_depth - SELL", results["cod_sell"]),
                    ("current_front_price_spread", results["cfps"])
                ]
            )), product)
            return dict(status="OK")
        else:
            return super(CustomStrategy, self).on_strategy_update(strategy_json)
