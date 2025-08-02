"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    product_ids = TEMPLATE.StrategyConfigField("List of Product IDs",
                                               "List of Product IDs corresponding to instrument IDs",
                                               list, mandatory="always", default=None)

    broker_ids = TEMPLATE.StrategyConfigField("List of Broker IDs",
                                             "List of Broker IDs that strategy operates on",
                                             list, mandatory="always", default=None)

    fix_margin = TEMPLATE.StrategyConfigField("Margin",
                                              "Quotation margin",
                                              float, mandatory="always", default=0.1)

    preferred_quantity = TEMPLATE.StrategyConfigField("Preferred Order Size",
                                                      "the maximum size of an order exposed to the quoting market"
                                                      "(for quote orders. The lift orders can be bigger if a unit "
                                                      "conversion is <> 1 set)",
                                                      float, mandatory="always", default=1.0)

    max_quantity = TEMPLATE.StrategyConfigField("Max. Position of strategy",
                                                "the maximum position of a strategy exposed to the market"
                                                "conversion is <> 1 set)",
                                                float, mandatory="always", default=5.0)

    stop_loss = TEMPLATE.StrategyConfigField("Stop Loss in Leg1 prices",
                                             "Stop Loss for strategy after which position of spread is closed",
                                             float, mandatory="always")


    idle_thres = TEMPLATE.StrategyConfigField("Min price movement threshold for quoting orders",
                                              "Minimal price movement threshold for quoting orders to update",
                                              float, mandatory="always", default=0.03)

    hard_stop_loss = TEMPLATE.StrategyConfigField("Hard Stop Loss in Leg1 prices",
                                                  "Hard Stop Loss for strategy after which will stop activity",
                                                  float, mandatory="always")

    stop_loss = TEMPLATE.StrategyConfigField("Stop Loss in Leg1 prices",
                                             "Stop Loss for strategy after which position of spread is closed",
                                             float, mandatory="always")

    idle_thres = TEMPLATE.StrategyConfigField("Min price movement threshold for quoting orders",
                                              "Minimal price movement threshold for quoting orders to update",
                                              float, mandatory="always", default=0.03)

    hard_stop_loss = TEMPLATE.StrategyConfigField("Hard Stop Loss in Leg1 prices",
                                                  "Hard Stop Loss for strategy after which will stop activity",
                                                  float, mandatory="always")

    market_volume_check_flag = TEMPLATE.StrategyConfigField("Market depth check.",
                                                  "Should the strategy check market depth before placing LEAD order?",
                                                  float, mandatory="always")

    ql_max = TEMPLATE.StrategyConfigField("Maximal allowed queue lag",
                                                  "Maximal allowed queue lag for strategy",
                                                  float, mandatory="always")