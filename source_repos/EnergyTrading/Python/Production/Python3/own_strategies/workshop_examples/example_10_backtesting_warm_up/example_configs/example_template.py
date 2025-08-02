import autotrader_core.strategy_template as TEMPLATE

# Template
# please note that in __init__.py we add a reference to the template


class ExampleTemplate(TEMPLATE.BaseTemplate):
    strategy_settings = {"setting_x": 10.,
                         "setting_y": "test",
                         "setting_list": [1, 2, 3, "X"],
                         "setting_dict": dict(algo="BALANCED")}

    # read_only: cannot be changed if the strategy is active
    setting_x = TEMPLATE.StrategyConfigField(caption="Test Float", description="Any number!", expected_type=float,
                                             mandatory="never", read_only="active", default=10.)
    setting_y = TEMPLATE.StrategyConfigField(caption="Test String", description="Any string!", expected_type=str,
                                             mandatory="never", read_only="active", default="test")
    setting_list = TEMPLATE.StrategyConfigField(caption="Test List", description="Any list!", expected_type=list,
                                                mandatory="never", read_only="active", default=[])
    setting_dict = TEMPLATE.StrategyConfigField(caption="Test Dict", description="Any dict!", expected_type=dict,
                                                mandatory="never", read_only="active", default=dict())

    @classmethod
    def get_attribute_groups(cls):
        groups = super(ExampleTemplate, cls).get_attribute_groups()
        groups.append({"caption": "Test Settings",
                       "description": "Some test settings",
                       "config_fields": ["setting_x", "setting_y", "setting_list", "setting_dict"]})
        return groups
