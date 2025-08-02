"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    product_ids = TEMPLATE.StrategyConfigField("List of Product IDs",
                                               "List of Product IDs corresponding to instrument IDs",
                                               list, mandatory="always", default=None)

    broker_list = TEMPLATE.StrategyConfigField("List of Broker IDs",
                                             "List of Broker IDs that strategy operates on",
                                             list, mandatory="always", default=None)

    stop_loss_margin = TEMPLATE.StrategyConfigField("Stop Loss in Leg1 prices",
                                             "Stop Loss for strategy after which position of spread is closed",
                                             float, mandatory="always")

    hard_stop_loss = TEMPLATE.StrategyConfigField("Hard Stop Loss in Leg1 prices",
                                                  "Hard Stop Loss for strategy after which will stop activity",
                                                  float, mandatory="always")

    trd_gap = TEMPLATE.StrategyConfigField("gap between current front price and executed trade",
                                                  "gap between current front price and executed trade",
                                                  float, mandatory="always")

    make_profit_margin = TEMPLATE.StrategyConfigField("margin that is used in make profit closing behavior",
                                                  "margin that is used in make profit closing behavior",
                                                  float, mandatory="always")
    loss_making_thold = TEMPLATE.StrategyConfigField("threshold from open_price against direction to start closing action",
                                                  "threshold from open_price against direction to start closing action",
                                                  float, mandatory="always")

    ql_max = TEMPLATE.StrategyConfigField("Maximal allowed queue lag",
                                                  "Maximal allowed queue lag for strategy",
                                                  float, mandatory="always")

    makeagg_ratio_thold = TEMPLATE.StrategyConfigField("ratio between loss by making and loss by aggress",
                                                  "ratio between loss by making and loss by aggress",
                                                  float, mandatory="always")

    burnout_period = TEMPLATE.StrategyConfigField("time period after which behavior is changed from profit making to closing by making",
                                                  "time period after which behavior is changed from profit making to closing by making",
                                                  float, mandatory="always")

    bid_ask = TEMPLATE.StrategyConfigField("lead bid ask spread thold",
                                                  "lead bid ask spread thold",
                                                  float, mandatory="always")

    max_position = TEMPLATE.StrategyConfigField("max postion",
                                                  "max position",
                                                  float, mandatory="always")

    lead_closing = TEMPLATE.StrategyConfigField("lead closing",
                                                  "lead closing (true|false)",
                                                  bool, mandatory="always")

    thold_dense = TEMPLATE.StrategyConfigField("thold_dense",
                                                  "thold_dense",
                                                  float, mandatory="always")

    thold_sparse = TEMPLATE.StrategyConfigField("thold_sparse",
                                                  "thold_sparse",
                                                  float, mandatory="always")

    # trading_direction = TEMPLATE.StrategyConfigField("trading_dicrection",
    #                                               "trading_dicrection",
    #                                               string, mandatory="always")
