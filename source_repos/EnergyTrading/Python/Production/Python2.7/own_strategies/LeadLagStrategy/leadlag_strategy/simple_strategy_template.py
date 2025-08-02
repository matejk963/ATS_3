"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    lead_product_id = TEMPLATE.StrategyConfigField("Product ID of the Lead Product",
                                               "Product ID corresponding to instrument ID",
                                               str, mandatory="always", default=None)

    lag_product_id = TEMPLATE.StrategyConfigField("Product ID of the Lag Product",
                                               "Product ID corresponding to instrument ID",
                                               str, mandatory="always", default=None)

    broker_id= TEMPLATE.StrategyConfigField("Broker ID",
                                             "Broker ID that strategy operates on",
                                             str, mandatory="always", default=None)
######################################################################################################################################################
# main strategy parameters
    max_secs_between_trades = TEMPLATE.StrategyConfigField("Maximum Seconds Between Trades",
                                              "Maximum number of seconds between consecutive trades in order for them to be considered still in one chain of trades",
                                              float, mandatory="always", default=30)

    cluster_trade_num_threshold = TEMPLATE.StrategyConfigField("Cluster trades number threshold",
                                              "The quantity of trades in one chain in the lead market when lag market goes into position",
                                              float, mandatory="always", default=5)

    min_price_movement = TEMPLATE.StrategyConfigField("Minimum price movement",
                                              "Minimum price movement in the lead chain of trades in order for the strategy to go into position",
                                              float, mandatory="always", default=0.1)

######################################################################################################################################################
# auxilliary strategy parameters
    take_profit = TEMPLATE.StrategyConfigField("Take Profit",
                                             "Take profit of the strategy in absolute EUR terms",
                                             float, mandatory="always")

    stop_loss = TEMPLATE.StrategyConfigField("Stop Loss",
                                             "Stop Loss of the strategy in absolute EUR terms",
                                             float, mandatory="always")

    trail_tp_bool = TEMPLATE.StrategyConfigField("Trailing Take Profit switch",
                                             "Switch of the trailing take profit, if on, the take profit is not taken immediately but based on an EMA value",
                                             bool, mandatory="always")

    trailing_tp_tau = TEMPLATE.StrategyConfigField("Trailing Take Profit tau",
                                             "Tau parameter for the trailing take profit EMA",
                                             float, mandatory="always")

    ba_max = TEMPLATE.StrategyConfigField("Bid-Ask spread maximum",
                                             "Maximum value of Bid-Ask spread allowed for the strategy to trade",
                                             float, mandatory="always", default=0.1)
######################################################################################################################################################
# other parameters
    preferred_quantity = TEMPLATE.StrategyConfigField("Preferred Order Size",
                                                      "the maximum size of an order exposed to the quoting market",
                                                      float, mandatory="always", default=1.0)

    max_quantity = TEMPLATE.StrategyConfigField("Max. Position of strategy",
                                                "The maximum position of a strategy exposed to the market",
                                                float, mandatory="always", default=1.0)

    hard_stop_loss = TEMPLATE.StrategyConfigField("Hard Stop Loss",
                                                  "Hard Stop Loss for strategy after which will stop activity",
                                                  float, mandatory="always")

    ql_max = TEMPLATE.StrategyConfigField("Maximal allowed queue lag",
                                                  "Maximal allowed queue lag for strategy",
                                                  float, mandatory="always")

