import autotrader_core.strategy_template as ST


class StrategyTemplate(ST.BaseTemplate):
    new_additional_view = ST.StrategyConfigField(caption="New additional view",
                                                 description="Additional view defined as example",
                                                 expected_type=ST.AdditionalViewType, mandatory="never")

    view_ttf = ST.StrategyConfigField(caption="New additional view",
                                      description="Additional view defined as example",
                                      expected_type=ST.AdditionalViewType, mandatory="never")

    view_ncg = ST.StrategyConfigField(caption="New additional view",
                                      description="Additional view defined as example",
                                      expected_type=ST.AdditionalViewType, mandatory="never")

    @classmethod
    def get_attribute_groups(cls):
        groups = super(StrategyTemplate, cls).get_attribute_groups()
        groups.append({"caption": "Additional views",
                       "description": "Additional views",
                       "config_fields": ["view_ttf", "view_ncg"]})
