from __future__ import absolute_import
from abc import ABCMeta, abstractmethod
import six


class ProductInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def exchange(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def product_id(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def delivery_start(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def delivery_end(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def product_type(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def trades(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def orders(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def market_meta_information(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def order_lock(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def trade_lock(self):
        raise NotImplementedError

    @abstractmethod
    def state(self, delivery_area_id):
        raise NotImplementedError

    @abstractmethod
    def trading_phase(self, delivery_area_id):
        raise NotImplementedError

    @abstractmethod
    def is_tradable(self, timestamp, delivery_area_id):
        raise NotImplementedError


class ProductsInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def exchange(self):
        raise NotImplementedError

    @abstractmethod
    def get_total_order_volume(self, products, delivery_area_id, order_filter, portfolio_key, internal_id):
        raise NotImplementedError

    @abstractmethod
    def get_total_traded_volume(self, products, delivery_area_id, trade_filter, portfolio_key, balance):
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, product_id):
        raise NotImplementedError

    @abstractmethod
    def get_by_timerange(self, start, end, product_type):
        raise NotImplementedError

    @abstractmethod
    def get_overlapping_with_timerange(self, start, end):
        raise NotImplementedError

    @abstractmethod
    def get_all_by_delivery_span(self, start, end):
        raise NotImplementedError

    @abstractmethod
    def get_by_delivery_span(self, start, end, product_type):
        raise NotImplementedError

    @abstractmethod
    def get_by_product_name(self, name):
        raise NotImplementedError

    @abstractmethod
    def get_by_market_metadata(self, metainfo_dict):
        raise NotImplementedError

    @abstractmethod
    def get_active_products(self, delivery_area_id):
        raise NotImplementedError

    @abstractmethod
    def get_all(self):
        raise NotImplementedError

    @abstractmethod
    def actions_in_rolling_time(self, broker_id, current_timestamp):
        raise NotImplementedError


class OrderInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def exchange(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def direction(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def product(self):
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
    def visible_quantity(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def clip_quantity(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def delivery_area_id(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def order_type(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def tags(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def execmode(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def state(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def creation_timestamp(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def broker_id(self):
        raise NotImplementedError


class OwnOrderInterface(six.with_metaclass(ABCMeta, OrderInterface)):
    @property
    @abstractmethod
    def execution_restriction(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def validity_restriction(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def validity_date(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def portfolio_key(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def start_timestamp(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def end_timestamp(self):
        raise NotImplementedError


class ComTraderOrderInterface(six.with_metaclass(ABCMeta, OwnOrderInterface)):
    pass


class PublicOrderInterface(six.with_metaclass(ABCMeta, OrderInterface)):
    @property
    @abstractmethod
    def order_id(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def execution_restriction(self):
        raise NotImplementedError


class OrderBookIndicatorsInterface(six.with_metaclass(ABCMeta, list)):
    @property
    @abstractmethod
    def mw_prices(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def eur_quantities(self):
        raise NotImplementedError


# TODO: Does it need an ABC?
class OrderBookIndicatorInterface(six.with_metaclass(ABCMeta)):
    pass


class OrderBookInterface(six.with_metaclass(ABCMeta)):
    @abstractmethod
    def get(self, delivery_area_id, order_filter, portfolio_key):
        raise NotImplementedError

    @abstractmethod
    def indicators(self, delivery_area_id):
        raise NotImplementedError

    @abstractmethod
    def get_volume(self, delivery_area_id, order_filter, internal_id_filter, portfolio_key):
        raise NotImplementedError


class TradeInterface(six.with_metaclass(ABCMeta)):
    @property
    @abstractmethod
    def exchange(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def trade_id(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def state(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def tags(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def product(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def quantity(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def price(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def execution_time(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def sell_delivery_area(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def buy_delivery_area(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def portfolio_key(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def aggressor_broker_id(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def initiator_broker_id(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def annotations(self):
        raise NotImplementedError


class PublicTradeInterface(six.with_metaclass(ABCMeta, TradeInterface)):
    pass


class OwnTradeInterface(six.with_metaclass(ABCMeta, TradeInterface)):
    @property
    @abstractmethod
    def user(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def portfolio_key(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def aggressor(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def counterparty(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def direction(self):
        raise NotImplementedError


# TODO: Perhaps this is API but does not need an ABC
class InternalTradeInterface(six.with_metaclass(ABCMeta, OwnTradeInterface)):
    pass
