import numpy as np
import autotrader_lib.common as COMMON
 
 
class ArtTrade(object):
    __direction = None
    __price = 0.0
    __quantity = 0.0
    __execution_time = None
    __tags = None

    def __init__(self, direction, priceVol_class, execution_time, slot_name=''):
        self.direction = direction
        self.price = priceVol_class.price
        self.quantity = priceVol_class.quantity
        self.execution_time = execution_time
        self.tags = {'strategy_slot': slot_name}

    @property
    def price(self):
        return self.__price

    @price.setter
    def price(self, value):
        if isinstance(value, (int, float)):
            self.__price = value
        else:
            raise ValueError("PriceVol price must be int or float: %s." % value)

    @property
    def quantity(self):
        return self.__quantity

    @quantity.setter
    def quantity(self, value):
        if isinstance(value, (int, float)):
            if value < 0:
                raise ValueError("PriceVol quantity cannot be negative: %s." % value)
            self.__quantity = value
        else:
            raise ValueError("PriceVol price must be int or float: %s." % value)

    @property
    def direction(self):
        return self.__direction

    @direction.setter
    def direction(self, value):
        if value in [COMMON.Direction.buy, COMMON.Direction.sell]:
            self.__direction = value
        else:
            raise ValueError("PriceVol direction must be 'buy' or 'sell': %s." % value)

    @property
    def slot_name(self):
        return self.__tags['strategy_slot']

    @slot_name.setter
    def slot_name(self, value):
        if isinstance(value, str):
            self.__tags['strategy_slot'] = value
        else:
            raise ValueError("PriceVol slot_name must be str: %s." % value)

    @property
    def tags(self):
        return self.__tags

    @tags.setter
    def tags(self, value):
        if isinstance(value, dict):
            self.__tags = value
        else:
            raise ValueError("Tags must be a dictionary: %s." % value)

    @property
    def execution_time(self):
        return self.__execution_time

    @execution_time.setter
    def execution_time(self, value):
        if isinstance(value, (int, float)):
            self.__execution_time = value
        else:
            raise ValueError("Execution time must be int or float: %s." % value)
