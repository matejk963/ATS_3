# -*- coding: utf-8 -*-
import itertools


class SerializationError(Exception):
    pass


class UnsupportedVersion(Exception):

    def __init__(self, version, available):
        super(UnsupportedVersion, self).__init__(
            "message-version {} not supported (available: {})"
            .format(version, ", ".join([x.VERSION for x in available])))


class UnsupportedExchange(Exception):

    def __init__(self, exchange, available):
        super(UnsupportedExchange, self).__init__(
            "exchange {} is not supported (available: {})"
            .format(exchange, ",".join([x.EXCHANGE for x in available])))


def is_incompatible(given, target):
    if not given:
        return True
    try:
        pairs = list(itertools.zip_longest(
            [int(x or 0) for x in given.split(".")],
            [int(x or 0) for x in target.split(".")],
            fillvalue=0)
        )
    except ValueError:
        return True
    # the major version number must be equal:
    given_major, target_major = pairs[0]
    if given_major != target_major:
        return True
    # all other parts are compatible if equal or greater:
    for given_num, target_num in pairs[1:]:
        if given_num < target_num:
            return True
    return False


class Handlers(object):

    def __init__(self, handlers):
        self._handlers = handlers

    def for_version(self, version):
        for handler_cls in self._handlers:
            if not is_incompatible(version, handler_cls.VERSION):
                return handler_cls
        raise UnsupportedVersion(version, self._handlers)

    def for_exchange_and_version(self, exchange, version, rest_mode=False):
        handlers = []
        for handler_cls in self._handlers:
            if handler_cls.EXCHANGE == exchange and getattr(handler_cls, "REST_MODE", False) == rest_mode:
                handlers.append(handler_cls)
        if not handlers:
            raise UnsupportedExchange(exchange, self._handlers)
        for handler_cls in handlers:
            if not is_incompatible(version, handler_cls.VERSION):
                return handler_cls
        raise UnsupportedVersion(version, self._handlers)


class SocketConfigurationError(Exception):
    pass
