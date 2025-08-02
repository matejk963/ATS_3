"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    product_ids = TEMPLATE.StrategyConfigField("List of Product IDs",
                                               "List of Product IDs corresponding to instrument IDs",
                                               list, mandatory="always", default=None)

    broker_list = TEMPLATE.StrategyConfigField("List of Broker IDs",
                                             "List of Broker IDs that strategy operates on",
                                             list, mandatory="always", default=None)