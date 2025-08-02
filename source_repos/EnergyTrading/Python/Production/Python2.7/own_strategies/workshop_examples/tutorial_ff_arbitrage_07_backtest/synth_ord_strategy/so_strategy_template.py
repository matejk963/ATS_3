"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    max_slot_size = TEMPLATE.StrategyConfigField("Max. Order-Size",
                                                 "the maximum size of an order exposed to the quoting market"
                                                 "(for arbitrage orders. The lift orders can be bigger if a unit "
                                                 "conversion is <> 1 set)",
                                                 float, mandatory="always", default=5.0)
