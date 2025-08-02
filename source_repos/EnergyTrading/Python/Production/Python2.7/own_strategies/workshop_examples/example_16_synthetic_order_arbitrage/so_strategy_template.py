"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.TrayportBaseTemplate):
    max_slot_size = TEMPLATE.StrategyConfigField("Max. Order-Size",
                                                 "the maximum size of an order exposed to the quoting market"
                                                 "(for arbitrage orders. The lift orders can be bigger if a unit "
                                                 "conversion is <> 1 set)",
                                                 float, mandatory="always", default=5.0)

    test_param = TEMPLATE.StrategyConfigField("test str", "test str desc", basestring, read_only="always")

    trading_account = TEMPLATE.TrayportBaseTemplate.trading_account.overridden_with(hidden=True)

    @classmethod
    def get_attribute_groups(cls):
        groups = super(StrategyTemplate, cls).get_attribute_groups()
        # what you don't append goes to additional
        groups.append({"caption": "Test Settings",
                       "description": "Some test settings",
                       "config_fields": ["test_param"]})

        return groups
