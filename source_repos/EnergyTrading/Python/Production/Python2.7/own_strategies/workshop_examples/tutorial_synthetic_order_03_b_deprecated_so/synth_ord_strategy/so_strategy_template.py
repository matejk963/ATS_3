"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    so_products = TEMPLATE.StrategyConfigField(
        caption="so_products",
        description="Products (sequence-items) for which the strategy should place synthetic orders",
        expected_type=TEMPLATE.ListOf(str),
        # Setting "always" here would make the call fail.
        mandatory="never",  # could also be "create", "active", "inactive", "always".
        read_only="active",  # could also be "create", "active", "inactive", "always"
        hidden=False,
        default=None
    )
