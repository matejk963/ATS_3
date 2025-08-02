""" autoTRADER Synthetic Workshop

Example 1: Exploring LocalViews

With this example we are not really trying to create some trading behavior but we would rather show
how LocalViews can be leveraged to explore the market situation and the orderbook

"""
import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as CETUTIL

import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYBASE


class SimpleSyntheticOrder(SYBASE.SyntheticOrderBase):
    """ We will be registering this synthetic order on various products via the synthetic strategy """

    # the only abstract method that needs to be implemented is always the act,
    # which is where the behavioral implementation is
    def act(self, localview, additional_views, timestamp):

        front_sell_price = localview.current_front_price(COMMON.Direction.sell)
        front_buy_price = localview.current_front_price(COMMON.Direction.buy)
        exposed_volume = localview.exposed_order_volume(self.slot_name)
        traded_volume = localview.traded_volume_buy(self.slot_name)

        if front_buy_price and front_sell_price:
            spread = abs(front_sell_price - front_buy_price)

            # based on what the spread is we could place or not place
            if spread > 0.8:

                # we can hardcode a volume, but there is a better way which we will show in a later example
                if exposed_volume < 100:

                    # we can manipulate the quantity and the price and then observe it in the traded and exposed volume
                    return self.create_slot(direction=COMMON.Direction.buy, quantity=10, price=front_buy_price + 1)

            if exposed_volume:
                print("{}, prod_id: {}, area: {}, front: {}//{}, exposed_volume: {}, traded_vol: {}"
                      .format(CETUTIL.utc_ts2cet_str(timestamp, True), localview._product.product_id,
                              localview._market_area, front_buy_price, front_sell_price, exposed_volume, traded_volume))
