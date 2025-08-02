import numpy as np

class OB_attributes():
    def __init__(self, localview, market_area):
        # order.price, order.broker_id, order.quantity
        self.localview = localview
        self.market_area = market_area
        
        # Access orders from the OrderBook
        market_orders = localview._product.orders.get(market_area)
        
        if market_orders:
            self.bids = sorted([x for x in market_orders if x.is_tradable and x.direction == 'buy'], reverse=True, key=lambda x: x.price)
            self.asks = sorted([x for x in market_orders if x.is_tradable and x.direction == 'sell'], reverse=False, key=lambda x: x.price)
            
        else:
            self.bids = []
            self.asks = []
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
                         if x.price >= b_price - p_depth]) +
                    sum([x.price * x.quantity for x in self.asks
                         if x.price <= a_price + p_depth])) / tot_vol

    def vol_ratio(self, p_depth):
        bid_vol = self.bid_volumeV(p_depth)
        ask_vol = self.ask_volumeV(p_depth)
        tot_vol = bid_vol + ask_vol
        if tot_vol == 0:
            return np.nan
        else:
            return (bid_vol - ask_vol) / tot_vol
