#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import unittest
import os.path
import os
import autotrader_core.i9ntests.simulation_definition_executor as SDE


def path(filename):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "assets", filename)


class BasicPositionTest(unittest.TestCase):
    def setUp(self):
        self.simulate = SDE.simulate

    def test(self):
        self.simulate(path("manual_epex_quarterly_double_internal_exec.xlsx"))


if __name__ == "__main__":
    unittest.main()
