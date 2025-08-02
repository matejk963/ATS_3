import unittest
import mock
import autotrader_core.common as COMMON
import so_strategy.so_arbitrage_lead as SAL


class SOTest(unittest.TestCase):
    def test_check_price(self):
        so = SAL.ArbitrageOrder(tick_size=0.1,
                                identifier="so_1",
                                configuration=dict(market_area=COMMON.Area.ttf,
                                                   broker_id=COMMON.Broker.eexs,
                                                   slot_name="so_1",
                                                   direction=COMMON.Direction.buy,
                                                   quantity=10))
        localview = mock.MagicMock()
        localview.traded_volume_buy = lambda x: 5
        localview.traded_volume_sell = lambda x: 10
        localview.current_front_price = lambda x, y: 5

        additional_views = mock.MagicMock()
        timestamp = mock.MagicMock()
        slot = so.act(localview, additional_views, timestamp)
        self.assertEqual(slot.direction, COMMON.Direction.buy)
        self.assertEqual(slot.quantity, 5)
        self.assertEqual(slot.price, 5)

        self.assertEqual(slot.short(), "B_5.0@5.00 [t=so_1]")

        print(slot.short(True, True))


if __name__ == '__main__':
    unittest.main()
