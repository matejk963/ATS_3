from __future__ import absolute_import
from abc import ABCMeta, abstractmethod
import six


class ExchangeInterface(six.with_metaclass(ABCMeta)):
    """Abstract BaseClass for Exchanges to define all necessary methods which are called in api.py"""

    @property
    @abstractmethod
    def products(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def market_state(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def connected(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def halted(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def halt_reason(self):
        raise NotImplementedError
