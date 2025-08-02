import autotrader_lib.common as COMMON

import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYBASE


class SimpleSO(SYBASE.SyntheticOrderBase):
    """
    Very simple example synthetic order that promptly trades the front buy and front sell public orders.
    (We will be registering this synthetic order on various products via the synthetic strategy.)
    """

    # the only abstract method that needs to be implemented is always the act,
    # which is where the behavioral implementation
    def act(self, localview, additional_views, timestamp):

        front_sell_price = localview.current_front_price(COMMON.Direction.sell)
        front_buy_price = localview.current_front_price(COMMON.Direction.buy)

        if front_sell_price:
            print("Front Sell", front_sell_price)
        if front_buy_price:
            print("Front Buy", front_buy_price)

        if front_buy_price is not None:
            return self.create_slot(direction=COMMON.Direction.sell,
                                    quantity=1000,
                                    price=front_buy_price - 10)

        if front_sell_price is not None:
            return self.create_slot(direction=COMMON.Direction.buy,
                                    quantity=1000,
                                    price=front_sell_price + 10)
