from __future__ import absolute_import
import mock

from autotrader_core import exchange_rate_limiting as ERL


class RatelimitManagerStub(ERL.RateLimitManager):
    _parameter_mock = None

    def __init__(self):
        self._parameter_mock = mock.Mock()
        self._parameter_mock.current_level = 0
        self._parameter_mock.l1_percent = 0
        self._parameter_mock.limit_type = 'mock'
        super(RatelimitManagerStub, self).__init__(self._parameter_mock, 999)

    def calculate_current(self):
        pass

    def increment(self, current_time, n=1):
        pass

    def _oldest_bucket(self):
        pass

    def update_current_omt(self, unused_current_time):
        """Placeholder to allow PositionCloser Strategy to Work"""
        pass
