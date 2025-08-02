import numpy as np

class OB_attributes():
    def __init__(self, localview, market_area):
        # order.price, order.broker_id, order.quantity
        self.localview = localview
        self.market_area = market_area
        self.bids = sorted([x for x in localview._product.orders.get(market_area) if x.is_tradable and x.direction == 'buy'], reverse=True, key=lambda x: x.price)
        self.asks = sorted([x for x in localview._product.orders.get(market_area) if x.is_tradable and x.direction == 'sell'], reverse=False, key=lambda x: x.price)
    def mid_price(self):
        return .5 * (self.bid_price() + self.ask_price())

    def ba_spread(self):
        return self.ask_price() - self.bid_price()

    def bid_price(self):
        try:
            return self.bids[0].price
        except(AttributeError):
            return np.nan

    def ask_price(self):
        try:
            return self.asks[0].price
        except(AttributeError):
            return np.nan

    def bid_volume(self):
        try:
            return self.bids[0].quantity
        except(AttributeError):
            return np.nan

    def ask_volume(self):
        try:
            return self.asks[0].quantity
        except(AttributeError):
            return np.nan

    def bid_broker(self):
        try:
            return self.bids[0].broker_id
        except(AttributeError):
            return np.nan

    def ask_broker(self):
        try:
            return self.asks[0].broker_id
        except(AttributeError):
            return np.nan

    def bid_volumeV(self, p_depth):
        b_price = self.bid_price()
        return sum([x.quantity for x in self.bids if x.price >= b_price - p_depth])

    def ask_volumeV(self, p_depth):
        a_price = self.ask_price()
        return sum([x.quantity for x in self.asks if x.price <= a_price + p_depth])

    def bid_volumeP(self, v_depth):
        vol = 0
        pW = 0
        for x in self.bids:
            v = x.quantity
            p = x.price
            if vol + v < v_depth:
                pW += p * v
                vol += v
            else:
                v_r = v_depth - vol
                pW += p * v_r
                break
        return pW / v_depth

    def ask_volumeP(self, v_depth):
        vol = 0
        pW = 0
        for x in self.asks:
            v = x.quantity
            p = x.price
            if vol + v < v_depth:
                pW += p * v
                vol += v
            else:
                v_r = v_depth - vol
                pW += p * v_r
                break
        return pW / v_depth

    def mid_priceW(self,  p_depth):
        b_price = self.bid_price()
        a_price = self.ask_price()
        bid_vol = self.bid_volumeV(p_depth)
        ask_vol = self.ask_volumeV( p_depth)
        tot_vol = bid_vol + ask_vol
        if bid_vol * ask_vol == 0:
            return np.nan
        else:
            return (sum([x.price * x.quantity for x in self.bids
                         if p >= b_price - p_depth]) +
                    sum([x.price * x.quantity for x in self.asks
                         if p <= a_price + p_depth])) / tot_vol

    def vol_ratio(self, p_depth):
        bid_vol = self.bid_volumeV(ob_class, ord_list_b, p_depth)
        ask_vol = self.ask_volumeV(ob_class, ord_list_a, p_depth)
        tot_vol = bid_vol + ask_vol
        if tot_vol == 0:
            return np.nan
        else:
            return (bid_vol - ask_vol) / tot_vol

    @staticmethod
    def _sparsity_func(order_book):
        _MIN_N_ORDERS = 4
        order_book = np.array(order_book)

        # Calculate differences
        diff = np.diff(order_book)

        # Shift the differences to align with the required positions
        if len(diff) < 1:
            return 2.0

        # diff = diff[:-1]  # Remove last element to align with shifted values

        length = len(diff)
        if length < _MIN_N_ORDERS:
            return 2.0

        # Define the manual kernel and normalize
        manual_kernel = np.array([2, 1.5, 1.25, 1, 1])
        kernel_list = manual_kernel / 2

        # Calculate weighted differences
        sum_w_diff = 0
        for i in range(min(4, length)):  # To handle cases where length is less than 5
            sum_w_diff += kernel_list[i] * abs(diff[i])

        return min(round(sum_w_diff, 2), 1)
