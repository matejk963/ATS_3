import numpy as np


class PriceVol(object):
    _price = 0
    _quantity = 0

    def __init__(self, price, quantity):
        self.price = price
        self.quantity = quantity

    @property
    def price(self):
        return self._price

    @price.setter
    def price(self, value):
        if isinstance(value, (int, float)):
            self._price = value
        else:
            raise ValueError("PriceVol price must be int or float: %s." % value)

    @property
    def quantity(self):
        return self._quantity

    @quantity.setter
    def quantity(self, value):
        if isinstance(value, (int, float)):
            if value < 0:
                raise ValueError("PriceVol quantity cannot be negative: %s." % value)
            self._quantity = value
        else:
            raise ValueError("PriceVol price must be int or float: %s." % value)

    @property
    def attributes_list(self):
        return ['price', 'quantity']

    def __add__(self, other):
        if isinstance(other, PriceVol):
            quantity = self.quantity + other.quantity
            price = (self.price * self.quantity + other.price * other.quantity) / quantity
            return PriceVol(price, quantity)
        else:
            raise ValueError("PriceVol addition parameter must be PriceVol class, instead was: %s." % other)

    def __sub__(self, other):
        if isinstance(other, (int, float)):
            quantity = self.quantity - other
            price = self.price
            return PriceVol(price, quantity)
        elif isinstance(other, PriceVol):
            quantity = self.quantity - other.quantity
            price = self.price
            return PriceVol(price, quantity)
        else:
            raise ValueError("PriceVol subtraction parameter must be int/float/PriceVol class, instead was: %s." % other)

    def __floordiv__(self, other):
        if isinstance(other, (int, float)):
            return self.quantity // other
        else:
            raise ValueError("PriceVol floordiv parameter must be integer or float, instead was: %s." % other)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.attributes_list}

    @classmethod
    def from_dict(cls, value_dict):
        return PriceVol(value_dict['price'], value_dict['quantity'])

    def spread_sub(self, other, c1=1, c2=1):
        if isinstance(other, PriceVol):
            return self.price * c1 - other.price * c2
        else:
            raise ValueError("PriceVol spread subtraction parameter must be PriceVol class, instead was: %s." % other)

    @classmethod
    def cash_sub(cls, this, other, volume):
        if isinstance(this, PriceVol) and isinstance(other, PriceVol):
            return (this.price - other.price) * volume
        else:
            raise ValueError("PriceVol spread subtraction parameter must be PriceVol class, instead was: %s, %s."
                             % (this, other))

    def to_string(self):
        return "%s@%s " % (self.quantity, self.price)