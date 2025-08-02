
import autotrader_core.strategy_template as TEMPLATE
import autotrader_lib.package_config_fields as PKG_CONF


class ExampleTemplate(TEMPLATE.BaseTemplate):
    sequence_item_id = TEMPLATE.StrategyConfigField("sequence_item_id", "The product id where we want to trade", str,
                                                    "active")

    order_type = TEMPLATE.StrategyConfigField("order_type", "The Synthetic Order Type to use",
                                              PKG_CONF.Enum(["SimpleSyntheticOrderOne", "SimpleSyntheticOrderTwo"]),
                                              mandatory="never")

    position = TEMPLATE.StrategyConfigField("position", "The Total Position of the Strategy", int)

    spread = TEMPLATE.StrategyConfigField("spread", "The default spread for all created synthetic orders", float)

    slot_size = TEMPLATE.StrategyConfigField("slot_size", "The default slot size for all created synthetic orders", int)

    config_option = TEMPLATE.StrategyConfigField("config option", "config option example", bool)
