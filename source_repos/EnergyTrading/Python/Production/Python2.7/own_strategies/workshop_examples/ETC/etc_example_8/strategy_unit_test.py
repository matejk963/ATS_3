import unittest
import mock
import autotrader_core.common as COMMON
import so_strategy.so_arbitrage_lead as SAL
import autotrader_synthetic.commingled_view as CV


class SOTest(unittest.TestCase):
    def setUp(self):
        self.so = SAL.ArbitrageOrder(tick_size=0.1,
                                     identifier="so_1",
                                     configuration=dict(market_area=COMMON.Area.ttf,
                                                        broker_id=COMMON.Broker.eexs,
                                                        slot_name="so_1",
                                                        direction=COMMON.Direction.buy,
                                                        quantity=10,
                                                        new_additional_view=COMMON.Area.it_bl))

        self.localview = mock.MagicMock()
        self.localview.current_front_price = lambda x, y: 14 if x == COMMON.Direction.buy else 15
        self.additional_view = mock.MagicMock()
        self.time_mock = mock.MagicMock()
        self.product = mock.MagicMock()


    def test_without_view(self):
        commingled_view = CV.CommingledView(self.product, [COMMON.Area.it_bl], "strategy_id")
        commingled_view.current_front_price = lambda x, y: None
        self.additional_view.get_configured_view = lambda x, y: commingled_view

        slot = self.so.act(self.localview, self.additional_view, self.time_mock)

        self.assertEqual(slot.quantity, 0)

    def test_view_with_high_buy_price(self):
        # local buy 14
        # local sell 15 <--
        # other buy 17 <--
        # other sell 18
        commingled_view = CV.CommingledView(self.product, [COMMON.Area.it_bl], "strategy_id")
        commingled_view.current_front_price = lambda x, y: 17 if x == COMMON.Direction.buy else 18
        self.additional_view.get_configured_view = lambda x, y: commingled_view

        slot = self.so.act(self.localview, self.additional_view, self.time_mock)

        self.assertEqual(slot.direction, COMMON.Direction.buy)
        self.assertEqual(slot.quantity, 10)
        self.assertEqual(slot.price, 15)

    def test_view_with_low_sell_price(self):
        # local buy 14 <--
        # local sell 15
        # other buy 9
        # other sell 10 <--
        commingled_view = CV.CommingledView(self.product, [COMMON.Area.it_bl], "strategy_id")
        commingled_view_ttf = CV.CommingledView(self.product, [COMMON.Area.ttf], "strategy_id")
        commingled_view_ncg = CV.CommingledView(self.product, [COMMON.Area.ncg], "strategy_id")

        commingled_view.current_front_price = lambda x, y: 9 if x == COMMON.Direction.buy else 10

        commingled_view_ttf.current_front_price = lambda x, y: 11 if x == COMMON.Direction.buy else 12
        commingled_view_ncg.current_front_price = lambda x, y: 13 if x == COMMON.Direction.buy else 14

        self.additional_view.get_configured_view = lambda x, y: commingled_view_ttf if x == "view_ttf" else commingled_view_ncg if x == "view_ncg" else commingled_view

        self.additional_view.get_configured_view = lambda x, y: commingled_view

        slot = self.so.act(self.localview, self.additional_view, self.time_mock)

        self.assertEqual(slot.direction, COMMON.Direction.sell)
        self.assertEqual(slot.quantity, 10)
        self.assertEqual(slot.price, 14)
