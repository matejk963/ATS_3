#!/usr/bin/python3
# -*- coding: utf-8 -*-

import autotrader_core.strategy as STRAT
import logging


log = logging.getLogger('autotrader.new_position_closer')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log
