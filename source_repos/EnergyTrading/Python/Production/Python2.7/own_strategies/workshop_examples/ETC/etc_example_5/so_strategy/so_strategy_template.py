import autotrader_core.strategy_template as ST


class StrategyTemplate(ST.BaseTemplate):
    new_additional_view = ST.StrategyConfigField(caption="New additional view",
                                                 description="Additional view defined as example",
                                                 expected_type=ST.AdditionalViewType, mandatory="never")

    {
        "new_additional_view": ["instrument_id_1", "instrument_id_2"]
    }
