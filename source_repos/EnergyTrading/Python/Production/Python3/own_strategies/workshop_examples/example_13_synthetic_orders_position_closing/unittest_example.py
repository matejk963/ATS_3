
import unittest
import mock

import autotrader_lib.common as COMMON
import own_strategies.workshop_examples.example_13_synthetic_orders_position_closing.position_closing_so.position_closing_so as PCSO  # noqa: E501

DEFAULT_IDENTIFIER = "test_so"


class Tests(unittest.TestCase):
    def test_slot_size_respected(self):
        so = PCSO.PositionClosingBehavior(tick_size=0.1,
                                          identifier=DEFAULT_IDENTIFIER,
                                          configuration=dict(market_area=COMMON.Area.ttf,
                                                             broker_id=COMMON.Broker.eexs,
                                                             slot_name=DEFAULT_IDENTIFIER,
                                                             position=1000,
                                                             slot_size=10,
                                                             spread=0.1))

        timestamp_mock = 342523467657.246
        local_view_mock = mock.MagicMock()
        local_view_mock.traded_volume_buy = lambda _: 0.
        local_view_mock.traded_volume_sell = lambda _: 0.
        local_view_mock.current_front_price = lambda x: 5. if x == COMMON.Direction.buy else 6.

        returned_slot = so.act(local_view_mock, timestamp_mock)

        self.assertEqual(returned_slot.quantity, 10.)
        self.assertAlmostEqual(returned_slot.price, 6.1)
        self.assertEqual(returned_slot.direction, COMMON.Direction.buy)

    def test_closes_position(self):
        so = PCSO.PositionClosingBehavior(tick_size=0.1,
                                          identifier=DEFAULT_IDENTIFIER,
                                          configuration=dict(market_area=COMMON.Area.ttf,
                                                             broker_id=COMMON.Broker.eexs,
                                                             slot_name=DEFAULT_IDENTIFIER,
                                                             position=1000,
                                                             slot_size=10,
                                                             spread=0.1))

        timestamp_mock = 342523467657.246
        local_view_mock = mock.MagicMock()
        local_view_mock.traded_volume_buy = lambda _: 995.
        local_view_mock.traded_volume_sell = lambda _: 0.
        local_view_mock.current_front_price = lambda x: 5. if x == COMMON.Direction.buy else 6.

        returned_slot = so.act(local_view_mock, timestamp_mock)

        self.assertEqual(returned_slot.quantity, 5.)
        self.assertAlmostEqual(returned_slot.price, 6.1)
        self.assertEqual(returned_slot.direction, COMMON.Direction.buy)

    def test_buybacks(self):
        so = PCSO.PositionClosingBehavior(tick_size=0.1,
                                          identifier=DEFAULT_IDENTIFIER,
                                          configuration=dict(market_area=COMMON.Area.ttf,
                                                             broker_id=COMMON.Broker.eexs,
                                                             slot_name=DEFAULT_IDENTIFIER,
                                                             position=1000,
                                                             slot_size=10,
                                                             spread=0.1))

        timestamp_mock = 342523467657.246
        local_view_mock = mock.MagicMock()
        local_view_mock.traded_volume_buy = lambda _: 1200.
        local_view_mock.traded_volume_sell = lambda _: 100.
        local_view_mock.current_front_price = lambda x: 5. if x == COMMON.Direction.buy else 6.

        returned_slot = so.act(local_view_mock, timestamp_mock)

        self.assertEqual(returned_slot.quantity, 10.)
        self.assertAlmostEqual(returned_slot.price, 4.9)
        self.assertEqual(returned_slot.direction, COMMON.Direction.sell)

    def test_no_orders_on_market(self):
        pass


if __name__ == "__main__":
    unittest.main()
