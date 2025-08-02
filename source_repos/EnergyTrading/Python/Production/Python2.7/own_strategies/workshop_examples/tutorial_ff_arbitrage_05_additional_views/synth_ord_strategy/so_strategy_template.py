"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    custom_named_additional_view = TEMPLATE.StrategyConfigField("Additional view",
                                                                "An additional view defined as an example",
                                                                TEMPLATE.AdditionalViewType, mandatory="never")
