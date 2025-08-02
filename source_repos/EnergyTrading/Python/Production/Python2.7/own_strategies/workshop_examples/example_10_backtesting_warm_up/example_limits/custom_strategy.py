""" Helper strategy, not relevant to the workshop example """
import autotrader_core.strategy as STRAT


class CustomStrategy(STRAT.Strategy):
    """ This is just a placeholder strategy """

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

        if self.strategy_settings["active"]:
            print("\n")
            print(self.per_product_limits)
            print("\n")
