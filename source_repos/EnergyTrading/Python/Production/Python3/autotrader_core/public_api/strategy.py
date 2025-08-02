from __future__ import absolute_import
from abc import ABCMeta, abstractmethod

import autotrader_core.public_api.common as PUBLIC_COMMON
import six


class PositionSlotInterface(six.with_metaclass(ABCMeta, object)):
    @abstractmethod
    def __init__(self,
                 slot_type,
                 direction,
                 quantity=None,
                 price=None,
                 price_range_lo=None,
                 price_range_hi=None,
                 execution_restriction=PUBLIC_COMMON.ExecutionRestrictionInterface.non,
                 order_type=PUBLIC_COMMON.OrderTypeInterface.order,
                 clip_quantity=None,
                 price_delta=0.0,
                 tick_size=0.01,
                 quantity_range_lo=None,
                 quantity_range_hi=None,
                 broker_id=None,
                 derivative_indicator=None,
                 decision_maker=None,
                 execution_maker=None,
                 liquidity_provision=None,
                 dea=None,
                 dea_client_id=None,
                 trading_capacity=None,
                 terms=None,
                 ):
        raise NotImplementedError

    @property
    @abstractmethod
    def slot_type(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def direction(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def price(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def quantity(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def price_range_lo(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def price_range_hi(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def tick_size(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def execution_restriction(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def clip_quantity(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def order_type(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def broker_id(self):
        raise NotImplementedError

    @abstractmethod
    def set_prices(self, price, price_range_lo, price_range_hi):
        raise NotImplementedError

    @abstractmethod
    def set_quantity(self, quantity, quantity_range_lo, quantity_range_hi):
        raise NotImplementedError

    @property
    @abstractmethod
    def internal_market_price(self):
        raise NotImplementedError


class StrategyInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def autotrader(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def strategy_id(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def caption(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def delivery_areas(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def strategy_settings(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def valid_from(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def valid_to(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def maximum_neg_buyback(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def neg_buyback_period(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def active(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def halted(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def halt_reason(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def exchange(self):
        raise NotImplementedError

    @abstractmethod
    def remove_my_orders_from_product(self, product):
        raise NotImplementedError

    @abstractmethod
    def custom_act(self, log_data, timestamp, products):
        raise NotImplementedError

    @abstractmethod
    def place_slots(self, log_data, product, timestamp, delivery_area_id, slots, stats, limit_minimum_sales_price,
                    limit_maximum_purchase_price, execmode):
        raise NotImplementedError

    @abstractmethod
    def custom_on_order_book_update(self, orders, timestamp):
        raise NotImplementedError

    @abstractmethod
    def custom_on_trade_update(self, trades, timestamp):
        raise NotImplementedError

    @abstractmethod
    def custom_on_public_trade_update(self, trades, timestamp):
        raise NotImplementedError

    @abstractmethod
    def custom_on_products_update(self, products, timestamp):
        raise NotImplementedError

    @abstractmethod
    def custom_on_products_queue(self, products, timestamp):
        raise NotImplementedError

    @abstractmethod
    def custom_on_timer(self, timestamp):
        raise NotImplementedError

    @abstractmethod
    def custom_on_error(self, errors, timestamp):
        raise NotImplementedError

    @abstractmethod
    def api_export_timeseries(self, timeseries_packets):
        raise NotImplementedError

    @abstractmethod
    def api_export_log_error(self, text, data_object):
        raise NotImplementedError

    @abstractmethod
    def api_export_log_info(self, text, data_object):
        raise NotImplementedError

    @abstractmethod
    def api_export_log_state(self, text, data_object):
        raise NotImplementedError
