import unittest
import mock

import autotrader_core.common as COMMON

import synth_ord_strategy.so_arbitrage_lead as ABSO  # noqa: E501

DEFAULT_IDENTIFIER = "test_so"


class Tests(unittest.TestCase):
    def test_check_price(self):
        so = ABSO.ArbitrageOrder(tick_size=0.1,
                                 identifier=DEFAULT_IDENTIFIER,
                                 configuration=dict(market_area=COMMON.Area.ttf,
                                                    broker_id=COMMON.Broker.eexs,
                                                    slot_name=DEFAULT_IDENTIFIER,
                                                    direction=COMMON.Direction.buy,
                                                    quantity=10))
        localview = mock.MagicMock()
        localview.current_front_price = lambda x, y: 15
        localview.traded_volume_buy = lambda _: 5
        localview.traded_volume_sell = lambda _: 10

        additional_view = mock.MagicMock()
        time_mock = mock.MagicMock()
        slot = so.act(localview, additional_view, time_mock)
        self.assertEqual(slot.direction, COMMON.Direction.buy)
        self.assertEqual(slot.quantity, 5)
        self.assertEqual(slot.price, 15)

        # alternative, check string representation of most important values
        self.assertEqual(slot.short(), "B_5.0@15.00 [t=test_so]")

        # alternatively, also print out
        print(slot.short(True, True))


if __name__ == "__main__":
    unittest.main()
