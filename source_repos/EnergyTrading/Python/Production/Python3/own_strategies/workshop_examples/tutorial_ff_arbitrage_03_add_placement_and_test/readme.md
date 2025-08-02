# Forwards and Futures Arbitrage Strategy - Part 3 - Unittest

Unit testing is a perfect way to verify the desired behaviour of your synthetic orders without using a test system with outside dependencies.

As a first basic unittest we will check what will be the result of the synthetic order's `act()` function

Import `unittest` and `mock` packages to create the python environment for unit testing
```python
import unittest
import mock
```
Import the Common module from autoTrader along with the arbitrage lead synthetic order module
```python
import autotrader_lib.common as COMMON
import synth_ord_strategy.so_arbitrage_lead as ABSO  # noqa: E501
```
Create the class with the `unittest.TestCase` as parent class
```python
class Tests(unittest.TestCase):
```
In that, define the first test case where we will only check the created slot's main parameters (based on a local view which will be mocked)
```python
    def test_check_price(self):
```
Create an object called `so` (as synthetic order) from the class defined in `so_arbitrage_lead.py`
```python
        so = ABSO.ArbitrageOrder(tick_size=0.1,
                                 identifier=DEFAULT_IDENTIFIER,
                                 configuration=dict(market_area=COMMON.Area.ttf,
                                                    broker_id=COMMON.Broker.eexs,
                                                    slot_name=DEFAULT_IDENTIFIER,
                                                    direction=COMMON.Direction.buy,
                                                    quantity=10))
```
Simulate or "Mock" the environment around the features that we want to check
```python
        localview = mock.MagicMock()
        localview.current_front_price = lambda x, y: 15
        localview.traded_volume_buy = lambda _: 5
        localview.traded_volume_sell = lambda _: 10

        additional_view = mock.MagicMock()
        time_mock = mock.MagicMock()
```
Call the `act()` function with the mocked parameters
```python
        slot = so.act(localview, additional_view, time_mock)
```
Assert the slot values with the expected ones
```python
        self.assertEqual(slot.direction, COMMON.Direction.buy)
        self.assertEqual(slot.quantity, 5)
        self.assertEqual(slot.price, 15)

        # alternative, check string representation of most important values
        self.assertEqual(slot.short(), "B_5.0@15.00 [t=test_so]")

        # alternatively, also print out
        print(slot.short(True, True))
```
