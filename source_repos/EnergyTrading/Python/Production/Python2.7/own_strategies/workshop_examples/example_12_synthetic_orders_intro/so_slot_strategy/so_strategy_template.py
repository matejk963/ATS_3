import autotrader_core.strategy_template as TEMPLATE
import autotrader_lib.package_config_fields as PKG_CONF


class SOTemplate(TEMPLATE.BaseTemplate):
    so_products = TEMPLATE.StrategyConfigField(
        "so_products",
        "Products (sequence-items) for which the strategy should place synthetic orders",
        PKG_CONF.ListOf(str)
    )
