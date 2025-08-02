"""Here we define, what fields have to be sent via REST Api, when the strategy is configured"""

import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplate(TEMPLATE.BaseTemplate):
    custom_named_additional_view = TEMPLATE.StrategyConfigField("Additional view",
                                                                "An additional view defined as an example",
                                                                TEMPLATE.AdditionalViewType, mandatory="never")

    view_italy = TEMPLATE.StrategyConfigField("Additional View", "View on italy", TEMPLATE.AdditionalViewType)
    view_ncg = TEMPLATE.StrategyConfigField("Additional View", "View on ncg", TEMPLATE.AdditionalViewType)
    view_ttf = TEMPLATE.StrategyConfigField("Additional View", "View on ttf", TEMPLATE.AdditionalViewType)

    @classmethod
    def get_attribute_groups(cls):
        """This will add these parameters into a new tab on the joule screen"""
        groups = super(StrategyTemplate, cls).get_attribute_groups()
        groups.append({"caption": "Additional Views",
                       "description": "Some test settings",
                       "config_fields": ["view_italy", "view_ncg", "view_ttf"]})
        return groups
