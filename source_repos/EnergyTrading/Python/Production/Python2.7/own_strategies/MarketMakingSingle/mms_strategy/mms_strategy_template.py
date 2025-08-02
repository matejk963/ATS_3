"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    product_ids = TEMPLATE.StrategyConfigField("List of Product IDs",
                                               "List of Product IDs corresponding to instrument IDs",
                                               list, mandatory="always")

    leg_clip = TEMPLATE.StrategyConfigField("Spread Clip",
                                             "Volume of a clip for Instrument 1",
                                             float, mandatory="always")

    broker_ids = TEMPLATE.StrategyConfigField("List of Broker IDs",
                                              "List of Broker IDs that strategy operates on, first is main",
                                              list, mandatory="always", default="14")

    fix_margin = TEMPLATE.StrategyConfigField("Margin",
                                              "Quotation margin",
                                              float, mandatory="always")

    preferred_clips = TEMPLATE.StrategyConfigField("Preferred Order Size in clips",
                                                   "the maximum size of an order exposed to the quoting market"
                                                   "(for quote orders. The lift orders can be bigger if a unit "
                                                   "conversion is <> 1 set)",
                                                   float, mandatory="always")

    max_clips = TEMPLATE.StrategyConfigField("Max. Position of strategy in clips",
                                             "the maximum position of a strategy exposed to the market"
                                             "conversion is <> 1 set)",
                                             float, mandatory="always")

    take_profit = TEMPLATE.StrategyConfigField("Take Profit in Leg1 prices",
                                             "Take Profit for strategy after which position of spread is closed",
                                             float, mandatory="always")

    stop_loss = TEMPLATE.StrategyConfigField("Stop Loss in Leg1 prices",
                                             "Stop Loss for strategy after which position of spread is closed",
                                             float, mandatory="always")

    bo_max = TEMPLATE.StrategyConfigField("Max bid ask spread in Leg1 prices",
                                          "Max bid ask spread level when stop loss is accepted",
                                          float, mandatory="always", default=4.0)

    idle_thres = TEMPLATE.StrategyConfigField("Min price movement threshold for quoting orders",
                                              "Minimal price movement threshold for quoting orders to update",
                                              float, mandatory="always", default=0.03)

    hard_stop_loss = TEMPLATE.StrategyConfigField("Hard Stop Loss in Leg1 prices",
                                                  "Hard Stop Loss for strategy after which will stop activity",
                                                  float, mandatory="always")

    mtm_bool = TEMPLATE.StrategyConfigField("MtM Quoting enabled",
                                            "Quoting based on MtM related to take profit or stop loss",
                                            bool, mandatory="always")

    model_type = TEMPLATE.StrategyConfigField("Model Type for Strategy",
                                              "Model Type for strategy by which evaluates prices,"
                                              "choose between MID, EMA, MSTD_x, MSTD_t",
                                              str, mandatory="always", default="EMA")

    model_params = TEMPLATE.StrategyConfigField("Parameters for Model",
                                                "List of Parameters that model uses: tau, tolerance",
                                                list, mandatory="always")

    eql_weight = TEMPLATE.StrategyConfigField("Weight for Equilibrium Model",
                                              "Value by which is making steered to Equilibrium Model",
                                              float, mandatory="always")

    eql_price = TEMPLATE.StrategyConfigField("Price for Equilibrium Model",
                                             "Price value of the Equilibrium Model",
                                             float, mandatory="always")

    mrg_weight = TEMPLATE.StrategyConfigField("Weight for Margin",
                                              "Weight Distribution between Margin and STD",
                                              float, mandatory="always")

    std_weight = TEMPLATE.StrategyConfigField("Weight for STD",
                                              "Weight for STD can be bigger than 1",
                                              float, mandatory="always")
