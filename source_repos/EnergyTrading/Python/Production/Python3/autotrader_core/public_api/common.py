from __future__ import absolute_import
from abc import ABCMeta, abstractmethod
import six

# TODO: These were marked as API, but this would be best described in just documentation
MINUTE = 60
QUARTER = 15 * 60
HOUR = 60 * 60


class DirectionInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def bid(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def buy(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def ask(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def sell(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def none(self):
        raise NotImplementedError


class ExchangeInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def nordpool(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def epex(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def periotheus(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def autotrader(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def trayport(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def parent(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def children(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def persistence(self):
        raise NotImplementedError


# TODO: Can be added so that later it can be well documented
class AreaInterface(six.with_metaclass(ABCMeta, object)):
    pass


class OrderTypeInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def order(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def block(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def iceberg(self):
        raise NotImplementedError


class MarketStateInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def active(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def hibernated(self):
        raise NotImplementedError


class TradingPhaseInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def closed(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def continuous(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def auction(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def balancing(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def same_area(self):
        raise NotImplementedError


class DeliveryAreaStateInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def active(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def inactive(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def hibernated(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def standby(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def none(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def balancing(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def deleted(self):
        raise NotImplementedError


class AggressorTypeInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def aggressor(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def originator(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def unknown(self):
        raise NotImplementedError


class InternalExecutionModeInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def skip(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def no(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def exchange_base_price(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def average_price(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def internal_only(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def default(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def available_execmodes(self):
        raise NotImplementedError


class ExecutionRestrictionInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def non(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def fok(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def ioc(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def aon(self):
        raise NotImplementedError


class ValidityRestrictionInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def non(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def gfs(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def gtd(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def gfd(self):
        raise NotImplementedError


class OrderStateInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def hibe(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def acti(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def iact(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def pending(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def rejected(self):
        raise NotImplementedError


class TrayportOrderStateInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def hibe(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def acti(self):
        raise NotImplementedError


class TradeStateInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def cancelled(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def recall_request_rejected(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def recall_granted(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def recall_requested(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def active(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def cancel_requested(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def cancel_rejected(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def request_approval(self):
        raise NotImplementedError


class TradeFilterInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def own(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def own_exchange(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def public(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def internal(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def own_buy(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def own_sell(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def own_exchange_sell(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def own_exchange_buy(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def internal_buy(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def internal_sell(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def no_filter(self):
        raise NotImplementedError


class OrderFilterInterface(six.with_metaclass(ABCMeta, object)):
    @property
    @abstractmethod
    def own(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def com_trader(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def public(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def own_buy(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def public_buy(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def own_sell(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def public_sell(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def com_sell(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def com_buy(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def buy(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def sell(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def no_filter(self):
        raise NotImplementedError
