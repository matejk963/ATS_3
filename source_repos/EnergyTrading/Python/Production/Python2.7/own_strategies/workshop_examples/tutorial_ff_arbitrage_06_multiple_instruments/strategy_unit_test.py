import unittest
import mock

import autotrader_core.common as COMMON
import autotrader_synthetic.commingled_view as CV

import synth_ord_strategy.so_arbitrage_lead as ABSO

DEFAULT_IDENTIFIER = "test_so"


class Tests(unittest.TestCase):
    def setUp(self):
        self.so = ABSO.ArbitrageOrder(tick_size=0.1,
                                      identifier=DEFAULT_IDENTIFIER,
                                      configuration=dict(market_area=COMMON.Area.ttf,
                                                         broker_id=COMMON.Broker.eexs,
                                                         slot_name=DEFAULT_IDENTIFIER,
                                                         direction=COMMON.Direction.buy,
                                                         quantity=10,
                                                         other_instrument_name=COMMON.Area.it_bl))
        self.product_mock = mock.MagicMock()  # Mock out the product since it is irrelevant for the test
        self.time_mock = 342523467657.246
        self.localview = mock.MagicMock()
        # Set the current buy and sell price to 15
        self.localview.current_front_price = lambda x, y: 14 if x == COMMON.Direction.buy else 15
        self.localview.traded_volume_buy = lambda _: 5
        self.localview.traded_volume_sell = lambda _: 10
        self.additional_view = mock.MagicMock()

    def test_without_additional_view(self):
        """Test to check that the spread is not created if the additional view is not defined"""
        test_commingled_view = CV.CommingledView(self.product_mock, [COMMON.Area.it_bl], "test_strategy_id")
        test_commingled_view.current_front_price = lambda x, y: None
        self.additional_view.get_configured_view = lambda x, y: test_commingled_view

        slot_without_additional_views = self.so.act(self.localview, self.additional_view, self.time_mock)
        # Check if the spread is not created if the additional view is not defined
        self.assertEqual(slot_without_additional_views.direction, COMMON.Direction.buy)
        self.assertEqual(slot_without_additional_views.quantity, 0)
        print(slot_without_additional_views.short(True, True))

    def test_additional_view_with_high_buy_price(self):
        """Test to validate that a buy slot is created if the additional view's market area has a better buy price
        than our local area's sell prices (meaning that what we can buy in the local area we can sell with a profit
        on the additional view's area)

                buy     sell
        Local    14      15
        Other    17      18  --> Buying for 15 in a local area and selling it for 17 in the other area = 2 profit
        """
        test_commingled_view = CV.CommingledView(self.product_mock, [COMMON.Area.it_bl], "test_strategy_id")
        # Here we set the buy price of the other market area to 18
        test_commingled_view.current_front_price = lambda x, y: 17 if x == COMMON.Direction.buy else 18
        self.additional_view.get_configured_view = lambda x, y: test_commingled_view

        slot_with_additional_views = self.so.act(self.localview, self.additional_view, self.time_mock)
        self.assertEqual(slot_with_additional_views.direction, COMMON.Direction.buy)
        self.assertEqual(slot_with_additional_views.price, 15)

    def test_additional_view_with_low_sell_price(self):
        """Test to validate that a buy slot is created if the additional view's market area has a lower sell price
        than our local area's buy prices (meaning that what we can buy in the additional view's area we can sell with a
        profit on the local area)

                buy     sell
        Local    14      15
        Other     9      10  --> Buying for 10 in the other area and selling it for 14 in the local = 4 profit
        """
        test_commingled_view = CV.CommingledView(self.product_mock, [COMMON.Area.it_bl], "test_strategy_id")
        test_commingled_view.current_front_price = lambda x, y: 9 if x == COMMON.Direction.buy else 10
        self.additional_view.get_configured_view = lambda x, y: test_commingled_view

        slot_with_additional_views = self.so.act(self.localview, self.additional_view, self.time_mock)
        self.assertEqual(slot_with_additional_views.direction, COMMON.Direction.sell)
        self.assertEqual(slot_with_additional_views.price, 14)


if __name__ == "__main__":
    unittest.main()
