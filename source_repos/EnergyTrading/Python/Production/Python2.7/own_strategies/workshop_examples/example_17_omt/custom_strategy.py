import random
import autotrader_core.strategy as STRATEGY
import autotrader_core.exchanges as EXCH
import autotrader_core.common as COMMON
import autotrader_lib.cet_util as CETUTIL


LONG_OMT_THRESHOLD = 90    # %
SHORT_OMT_THRESHOLD = 100  # %


class CustomStrategy(STRATEGY.Strategy):

    def custom_act(self, _, timestamp, products=None):
        if not products:
            return self.debug_log("No products")

        if not isinstance(self.exchange, EXCH.Epex):
            return self.error_log("Not using EPEX, can't use OMT values.")

        if self.exchange.long_omt.l1_percent >= LONG_OMT_THRESHOLD:
            return self.warn_log("Long omt has exceeded threshold ({} >= {}). Do nothing..."
                                 "".format(self.exchange.long_omt.l1_percent, LONG_OMT_THRESHOLD))

        self.debug_log("Short: {}% of L1 reached. Long: {}% of L1 reached."
                       "".format(self.exchange.short_omt.l1_percent, self.exchange.long_omt.l1_percent))

        for product in products:
            # create/update random orders until the threshold is exceeded:
            if self.exchange.short_omt.l1_percent < SHORT_OMT_THRESHOLD:
                self.act_for_product(product, timestamp)

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        self.debug_log(text="Act for product", product=product)

        # Filter only tradable products
        if not product.is_tradable(timestamp, self.delivery_area_id):
            start_ts, end_ts, state = product.trading_phase(self.delivery_area_id)
            self.debug_log(text="skip untradable product. state: {}, interval: {}-{}, now:{}".format(
                state,
                CETUTIL.utc_ts2cet_str(start_ts, True, True),
                CETUTIL.utc_ts2cet_str(end_ts, True, True),
                CETUTIL.utc_ts2cet_str(timestamp, True, True),
            ),
                product=product
            )

        self.debug_log("short omt parameters {}".format(self.exchange.short_omt.to_dict()), product)
        self.debug_log("long omt parameters {}".format(self.exchange.long_omt.to_dict()), product)
        price = random.random() * 100 * self.exchange.tick_size
        slot = STRATEGY.PositionSlot("OMT", COMMON.Direction.buy, 10, price)
        self.debug_log("Placing slot: {} {}@{}".format(slot.direction, slot.quantity, slot.price), product)
        response = self.place_slots({}, product, timestamp, self.delivery_area_id, [slot],
                                    [], None, None, COMMON.InternalExecutionMode.exchange_base_price)
        self.debug_log("placement response: {}".format(response), product)

    def custom_on_order_book_update(self, orders, timestamp):
        self.debug_log("act by on order book update")
        products = set(order.product for order in orders)
        self.act(timestamp, products)

    # Since this strategy already places more than enough orders, the following events are disabled to speed up the
    # backtesting time:

    # def custom_on_trade_update(self, trades, timestamp):
    #     self.debug_log("act by on trade update")
    #     products = set(trade.product for trade in trades)
    #     self.act(timestamp, products)

    # def custom_on_products_update(self, products, timestamp):
    #     self.debug_log("act by on products update")
    #     self.act(timestamp, products)

    # def custom_on_timer(self, timestamp):
    #     self.debug_log("act by on timer")
    #     products = self.exchange.products.get_all()
    #     self.act(timestamp, products)
