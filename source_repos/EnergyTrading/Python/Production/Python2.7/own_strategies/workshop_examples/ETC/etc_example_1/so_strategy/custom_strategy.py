import logging
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB


log = logging.getLogger("example_1")


class CustomStrategy(SYSB.SyntheticOrderStrategyBase):
    default_payload = {}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

    @classmethod
    def get_available_synthetic_order_types(cls):
        pass

