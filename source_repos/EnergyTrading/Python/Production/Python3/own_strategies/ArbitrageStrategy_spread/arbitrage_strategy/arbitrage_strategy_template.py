"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    product_ids = TEMPLATE.StrategyConfigField("List of Product IDs",
                                               "List of Product IDs corresponding to instrument IDs",
                                               list, mandatory="always", default=None)

    broker_ids = TEMPLATE.StrategyConfigField("List of Broker IDs",
                                              "List of Broker IDs that strategy operates on",
                                              list, mandatory="always", default=None)

    exchange_broker_ids = TEMPLATE.StrategyConfigField("List of Exchange venues IDs",
                                                       "List of Broker IDs that strategy operates on",
                                                       list, mandatory="always", default=None)

    broker_ids_main = TEMPLATE.StrategyConfigField("List of Broker IDs for main brokers",
                                                   "List of Broker IDs that strategy operates on, main brokers",
                                                   list, mandatory="always", default=None)

    opt_margin = TEMPLATE.StrategyConfigField("Margin Optimal",
                                              "Quotation margin optimal value",
                                              float, mandatory="always", default=0.1)

    min_margin = TEMPLATE.StrategyConfigField("Margin Min",
                                              "Quotation margin min value",
                                              float, mandatory="always", default=0.1)

    max_margin = TEMPLATE.StrategyConfigField("Margin Max",
                                              "Quotation margin max value",
                                              float, mandatory="always", default=0.1)

    min_margin_aux = TEMPLATE.StrategyConfigField("Margin Min Aux Venues",
                                                  "Quotation margin min value for auxiliar venues",
                                                  float, mandatory="always", default=0.1)

    margin_for_closing = TEMPLATE.StrategyConfigField("Margin for closing",
                                                      "Margin in EUR for closing mishit trades",
                                                      float, mandatory="always", default=0.15)

    closing_in_profit_flag = TEMPLATE.StrategyConfigField("Closing in profit",
                                                          "Closing mishit position in profit allowed?",
                                                          float, mandatory="always", default=1.0)

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

    market_volume_check_flag = TEMPLATE.StrategyConfigField("Market depth check.",
                                                            "Should the strategy check market depth before placing LEAD order?",
                                                            float, mandatory="always")

    ql_max = TEMPLATE.StrategyConfigField("Maximal allowed queue lag",
                                          "Maximal allowed queue lag for strategy",
                                          float, mandatory="always")

    public_update = TEMPLATE.StrategyConfigField("On public trade update lead",
                                                 "Boolean for running lead on public trades",
                                                 bool, mandatory="always", default=True)

    advanced_making = TEMPLATE.StrategyConfigField("Advanced making allowed",
                                                   "Boolean for advanced making of strategy",
                                                   bool, mandatory="always")

    broker_making = TEMPLATE.StrategyConfigField("Broker making allowed",
                                                 "Boolean for broker making of strategy",
                                                 bool, mandatory="always")

    maximum_neg_buyback = TEMPLATE.StrategyConfigField("Flapping behavior number",
                                                       "Flapping behavior of a new/updated order produced by a strategy",
                                                       int, mandatory="always", default=5)

    cons_making = TEMPLATE.StrategyConfigField("Conservative making allowed",
                                               "Boolean for conservative making of strategy",
                                               bool, mandatory="always")

    cons_making_aux = TEMPLATE.StrategyConfigField("Conservative making allowed aux venues",
                                                   "Boolean for conservative making of strategy for auxiliary brokers",
                                                   bool, mandatory="always")

    cons_margin = TEMPLATE.StrategyConfigField("Conservative margin",
                                               "Margin to which conservative bidding applies",
                                               float, mandatory="always", default=0.0)

    cons_min_level = TEMPLATE.StrategyConfigField("Conservative min safe level",
                                                  "Minimal level from lift to which conservative bidding applies",
                                                  float, mandatory="always", default=0.1)

    verbose = TEMPLATE.StrategyConfigField("Extensive logging bool",
                                           "Boolean for logging of strategy",
                                           bool, mandatory="always", default=True)
