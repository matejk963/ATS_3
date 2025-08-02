# -*- coding: utf-8 -*-
"""
This file contains the epex id generator, which will produce consecutive unique order and product ids.
The ids are according to epex formatting convention
"""

import backtesting.exchanges.base_utils as SIMUTIL


class EpexIdGenerator(SIMUTIL.IdGenerator):
    """Class to automatically generate unique incremental product and order ids"""

    @staticmethod
    def _int2order_id(number):
        # type: (int) -> str
        """Convert incremental index of order ids to an epex valid order id"""
        return str(number).zfill(10)

    @staticmethod
    def _int2product_id(number):
        # type: (int) -> str
        """Convert incremental index of order ids to an epex valid product id"""
        return str(number).zfill(8)
