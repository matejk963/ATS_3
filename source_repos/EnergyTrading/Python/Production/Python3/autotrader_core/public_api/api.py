from __future__ import absolute_import
from abc import ABCMeta, abstractmethod
import six


class AutoTraderInterface(six.with_metaclass(ABCMeta)):
    @abstractmethod
    def get_exchange(self, name):
        raise NotImplementedError

    @property
    @abstractmethod
    def all_active_exchanges(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def all_exchanges(self):
        raise NotImplementedError
