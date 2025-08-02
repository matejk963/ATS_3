import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYBASE


class SimpleSyntheticOrderTwo(SYBASE.SyntheticOrderBase):
    """ This one does nothing but we will use it for illustration """

    def act(self, localview, additional_views, timestamp):
        """ For now we really dont care about the act"""
        pass
