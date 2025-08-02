import logging

import autotrader_core.common as COMMON
import autotrader_core.strategy as STRAT
import autotrader_synthetic.local_view as LV

log = logging.getLogger('autotrader.example_15_germany_baseload')

BROKER_ID = COMMON.Broker.eex
DE_BASELOAD_EEX = COMMON.Area.de_bl


class CustomStrategy(STRAT.GasStrategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log
        self.broker_id = BROKER_ID

        # make a fast check, whether the files are initialised correctly
        # this number can change, by changing the trayport configs
        n_de_baseload_products = len(self.autotrader.trayport.products.get_active_products(DE_BASELOAD_EEX))
        print("Products for DE Baseload: ", n_de_baseload_products)
        assert n_de_baseload_products == 476

    def custom_act(self, log_data, timestamp, products=None):
        for p in products:
            self.act_for_product(p, timestamp)

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        # print out what the act is called for when developing,
        # to double check whether the wanted products actually arrive
        # print("act", timestamp, product.product_id, product.name)
        try:
            prop = self.get_trayport_properties(product_id=product.product_id)
        except KeyError as exc:
            print(exc)
            return
        lv = LV.LocalView(product, DE_BASELOAD_EEX, self.strategy_id)

        best_public_sell = lv.current_front_price(COMMON.Direction.sell, self.broker_id, only_tradable=True)
        best_public_buy = lv.current_front_price(COMMON.Direction.buy, self.broker_id, only_tradable=True)

        info = "t:{}/{}, po:{}/{}".format(lv.traded_volume_buy("f"), lv.traded_volume_buy("f"), best_public_buy,
                                          best_public_sell)
        qty = max(prop.min_quantity, 1)

        # aggressive placements just 1 tick before the front of other side.
        if best_public_sell is not None:
            slot = STRAT.PositionSlot("f", COMMON.Direction.buy, qty, best_public_sell - prop.price_tick, info=info,
                                      broker_id=self.broker_id)
        elif best_public_buy is not None:
            slot = STRAT.PositionSlot("f", COMMON.Direction.sell, qty, best_public_buy + prop.price_tick, info=info,
                                      broker_id=self.broker_id)
        else:
            slot = None

        if slot:
            self.place_slots(log_data, product, timestamp, DE_BASELOAD_EEX, [slot])
            # when starting development, it is very important to always check the return value of the place slots.
            # this can give hints whether a placement worked or not.
            # res = self.place_slots(log_data, product, timestamp, DE_BASELOAD_EEX, [slot])
            # print(slot.short(True, True), res)

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)

    def custom_on_order_book_update(self, orders, timestamp):
        self.act(timestamp, set(o.product for o in orders))

    # def custom_on_timer(self, timestamp):
    #     self.act(timestamp)
