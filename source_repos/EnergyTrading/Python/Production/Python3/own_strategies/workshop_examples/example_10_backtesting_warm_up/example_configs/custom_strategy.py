""" Helper strategy, not relevant to the workshop example """
import logging

import autotrader_core.strategy as STRAT

log = logging.getLogger("autotrader.example_strategy")


class CustomStrategy(STRAT.Strategy):
    """ This is just a placeholder strategy """
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

        print("\n------------------------")
        print("Getting an update call!")
        print("------------------------ \n")

        for key in self.strategy_settings:
            if "setting" in key:
                print((self.strategy_settings[key]))

        print("\nStrategy is active:")
        print((self.strategy_settings["active"]))
        print("\n")
