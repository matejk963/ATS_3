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

    lead_brokers_list= TEMPLATE.StrategyConfigField("List of Broker IDs for lead product",
                                             "List of Broker IDs that strategy operates on",
                                             list, mandatory="always", default=None)
######################################################################################################################################################
# main strategy parameters
#     max_secs_between_trades = TEMPLATE.StrategyConfigField("Maximum Seconds Between Trades",
#                                               "Maximum number of seconds between consecutive trades in order for them to be considered still in one chain of trades",
#                                               float, mandatory="always", default=30)
#
#     cluster_trade_num_threshold = TEMPLATE.StrategyConfigField("Cluster trades number threshold",
#                                               "The quantity of trades in one chain in the lead market when lag market goes into position",
#                                               float, mandatory="always", default=5)
#
#     min_price_movement = TEMPLATE.StrategyConfigField("Minimum price movement",
#                                               "Minimum price movement in the lead chain of trades in order for the strategy to go into position",
#                                               float, mandatory="always", default=0.1)

    MACD_long_threshold = TEMPLATE.StrategyConfigField("Trend MACD long threshold",
                                              "The threshold of MACD trend value for going into long positions",
                                              float, mandatory="always")

    MACD_short_threshold = TEMPLATE.StrategyConfigField("Trend MACD short threshold",
                                              "The threshold of MACD trend value for going into short positions",
                                              float, mandatory="always")

    price_diff_long_threshold = TEMPLATE.StrategyConfigField("price_diff_long_threshold",
                                              "Fair price vs current BA difference long threshold",
                                              float, mandatory="always")

    price_diff_short_threshold = TEMPLATE.StrategyConfigField("price_diff_short_threshold",
                                              "Fair price vs current BA difference short threshold",
                                              float, mandatory="always")

    combined_long_threshold = TEMPLATE.StrategyConfigField("Combined long threshold",
                                              "The threshold of MACD trend + price_diff value for going into long positions",
                                              float, mandatory="always")

    combined_short_threshold = TEMPLATE.StrategyConfigField("Combined short threshold",
                                              "The threshold of MACD trend + price_diff value for going into short positions",
                                              float, mandatory="always")

    reg_model_coef1 = TEMPLATE.StrategyConfigField("reg_model_coef1",
                                              "Intercept coefficient of lead-lag regression model",
                                              float, mandatory="always")

    reg_model_coef2 = TEMPLATE.StrategyConfigField("reg_model_coef2",
                                              "Beta coefficient of lead-lag regression model",
                                              float, mandatory="always")

    combined_mode = TEMPLATE.StrategyConfigField("combined_mode",
                                             "To use simple thresholds or combined threshold",
                                             bool, mandatory="always")

    minimum_intensity = TEMPLATE.StrategyConfigField("minimum_intensity",
                                              "Minimum VII intensity on both elad and lag markets for entering positions",
                                              float, mandatory="always")

######################################################################################################################################################
# auxilliary strategy parameters
    take_profit = TEMPLATE.StrategyConfigField("Take Profit",
                                             "Take profit of the strategy in absolute EUR terms",
                                             float, mandatory="always")

    stop_loss = TEMPLATE.StrategyConfigField("Stop Loss",
                                             "Stop Loss of the strategy in absolute EUR terms",
                                             float, mandatory="always")

    aggloss_thres = TEMPLATE.StrategyConfigField("AGGLOSS threshold",
                                             "Threshold for BA spread in order to AGGLOSS instead of MAKEBEST",
                                             float, mandatory="always")

    hard_stop_loss = TEMPLATE.StrategyConfigField("Hard Stop Loss",
                                                  "Hard Stop Loss for strategy after which will stop activity",
                                                  float, mandatory="always")

    burnout_period = TEMPLATE.StrategyConfigField("Burnout Period",
                                                  "Burnout period for closing position in minutes ",
                                                  float, mandatory="always")

    stop_profit = TEMPLATE.StrategyConfigField("Stop Profit",
                                                  "Stop Profit paramater for Martin's closing",
                                                  float, mandatory="always")

    makeagg_ratio = TEMPLATE.StrategyConfigField("Makeagg Ratio",
                                                  "Makeagg Ratio for Martin's closing",
                                                  float, mandatory="always")

    trail_stop = TEMPLATE.StrategyConfigField("Trailing Stop",
                                                  "When MTM of a position is above this value, the stop loss is shifted by this value -> protecting gains",
                                                  float, mandatory="always")
    #
    # trail_tp_bool = TEMPLATE.StrategyConfigField("Trailing Take Profit switch",
    #                                          "Switch of the trailing take profit, if on, the take profit is not taken immediately but based on an EMA value",
    #                                          bool, mandatory="always")
    #
    # trailing_tp_tau = TEMPLATE.StrategyConfigField("Trailing Take Profit tau",
    #                                          "Tau parameter for the trailing take profit EMA",
    #                                          float, mandatory="always")
    #
    # action_closing = TEMPLATE.StrategyConfigField("Action Closing switch",
    #                                          "Switch of the action closing, if on, strategy is closing positions aggressively according to calculate_action",
    #                                          bool, mandatory="always")

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

