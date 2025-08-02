"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    product_ids = TEMPLATE.StrategyConfigField("List of Product IDs",
                                               "List of Product IDs corresponding to instrument IDs",
                                               list, mandatory="always", default=None)

    broker_list = TEMPLATE.StrategyConfigField("List of Broker IDs",
                                             "List of Broker IDs that strategy operates on",
                                             list, mandatory="always", default=None)

    hard_stop_loss = TEMPLATE.StrategyConfigField("Hard Stop Loss in Leg1 prices",
                                                  "Hard Stop Loss for strategy after which will stop activity",
                                                  float, mandatory="always")


    ql_max = TEMPLATE.StrategyConfigField("Maximal allowed queue lag",
                                                  "Maximal allowed queue lag for strategy",
                                                  float, mandatory="always")



    max_position = TEMPLATE.StrategyConfigField("max postion",
                                                  "max position",
                                                  float, mandatory="always")

    lead_closing = TEMPLATE.StrategyConfigField("lead closing",
                                                  "lead closing (true|false)",
                                                  bool, mandatory="always")

    instrument_map = TEMPLATE.StrategyConfigField("instrument map",
                                                  "mapping",
                                                  dict, mandatory="always")
    fair_price_buffer_size = TEMPLATE.StrategyConfigField("buffer size",
                                                          "buffer size",
                                                          int, mandatory="always")