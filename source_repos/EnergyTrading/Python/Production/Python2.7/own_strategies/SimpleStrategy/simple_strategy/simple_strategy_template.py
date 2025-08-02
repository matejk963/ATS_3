"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    product_ids = TEMPLATE.StrategyConfigField("List of Product IDs",
                                               "List of Product IDs corresponding to instrument IDs",
                                               list, mandatory="always")

    broker_id = TEMPLATE.StrategyConfigField("Broker ID",
                                             "Broker ID that strategy operates on",
                                             str, mandatory="always", default="14")

    fix_margin = TEMPLATE.StrategyConfigField("Margin",
                                              "Quotation margin",
                                              float, mandatory="always")

    preferred_quantity = TEMPLATE.StrategyConfigField("Preferred Order Size",
                                                      "the maximum size of an order exposed to the quoting market"
                                                      "(for quote orders. The lift orders can be bigger if a unit "
                                                      "conversion is <> 1 set)",
                                                      float, mandatory="always", default=1.0)

    max_quantity = TEMPLATE.StrategyConfigField("Max. Position of strategy",
                                                "the maximum position of a strategy exposed to the market"
                                                "conversion is <> 1 set)",
                                                float, mandatory="always", default=5.0)
