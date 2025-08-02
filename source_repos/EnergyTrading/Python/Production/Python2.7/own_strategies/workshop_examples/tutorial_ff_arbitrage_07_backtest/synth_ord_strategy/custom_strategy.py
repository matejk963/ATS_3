import logging

import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT
import so_arbitrage_lead
from constants import TTF_ICE, THE_ICE

log = logging.getLogger("autotrader.tutorial_synthetic_order_07_backtest")


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    # with the default payload, we define fields valid for all synthetic orders used with this strategy
    default_payload = {}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.delivery_areas_additional = [
            TTF_ICE,
            THE_ICE,
        ]
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"ArbitrageOrder": so_arbitrage_lead.ArbitrageOrder}
