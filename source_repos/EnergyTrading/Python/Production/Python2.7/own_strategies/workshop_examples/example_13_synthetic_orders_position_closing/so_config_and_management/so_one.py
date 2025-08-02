import numbers

import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYBASE


class SimpleSyntheticOrderOne(SYBASE.SyntheticOrderBase):
    """ We will be registering this synthetic order on various products via the synthetic strategy """

    config_option = SYBASE.CONF.SyntheticOrderConfigField(caption="config_option",
                                                          expected_type=bool,
                                                          description="Explaining what the option does")

    position = SYBASE.CONF.SyntheticOrderConfigField(caption="position",
                                                     expected_type=numbers.Number,
                                                     description="Total position that is desired to be traded")

    def configure(self, incoming_configuration_dict):
        position = incoming_configuration_dict.get("position")
        if position > 10000:
            raise ValueError("This position is way too high!")

        # we want to raise here
        super(SimpleSyntheticOrderOne, self).configure(incoming_configuration_dict)

    def act(self, localview, additional_views, timestamp):
        """ For now we really dont care about the act"""
        pass
