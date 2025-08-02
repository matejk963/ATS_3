import re

import autotrader_core.strategy_template as TEMPLATE


class MarketMakerTemplate(TEMPLATE.MifidTemplate):
    # Set some defaults on mifid fields defined in the base class
    mifid_liquidity_provision = TEMPLATE.MifidTemplate.mifid_liquidity_provision.overridden_with(default=True)
    mifid_execution_maker = TEMPLATE.MifidTemplate.mifid_execution_maker.overridden_with(default="999200100")

    # Add additional configuration fields
    sequence_settings = TEMPLATE.StrategyConfigField("Sequence Settings",
                                                     "Format: Sequence_id,from,until;Sequence_id,from,until; ...",
                                                     str, mandatory="always")

    @sequence_settings.validator
    def sequence_settings(self, value):
        if value != "":
            split_lines = value.split(";")
            for line in split_lines:
                if re.match(r'^\w+,\d+,\d+$', line) is None:
                    raise TEMPLATE.FieldValidationError("Incorrect format in sequence settings: "
                                                        "lines are separated by ';' and they match r'^\\w+,\\d+,\\d+$'")

    buy_discounted_quantity = TEMPLATE.StrategyConfigField("Buy Discounted Quantity",
                                                           "The Synthetic Order looks for the price where one could "
                                                           "buy this amount of Energy (max price)",
                                                           float, mandatory="always")

    @buy_discounted_quantity.validator
    def buy_discounted_quantity(self, value):
        if value <= 0:
            raise TEMPLATE.FieldValidationError("The parameter: buy_discounted_quantity; must be a positive value, "
                                                "given: {}".format(value))

    buy_spread = TEMPLATE.StrategyConfigField("Buy Spread",
                                              "The Synthetic Order places an order on the market with this spread "
                                              "behind the price of the Discounted Quantity",
                                              float, mandatory="always")

    @buy_spread.validator
    def buy_spread(self, value):
        if value <= 0:
            raise TEMPLATE.FieldValidationError("The parameter: buy_spread; must be a positive value, given: {}"
                                                .format(value))

    buy_slot_size = TEMPLATE.StrategyConfigField("Buy Order Quantity",
                                                 "The Synthetic Order places an order with that Quantity on the market",
                                                 float, mandatory="always")

    @buy_slot_size.validator
    def buy_slot_size(self, value):
        if value < 0:
            raise TEMPLATE.FieldValidationError("The parameter: buy_slot_size; must be a non-negative value, given: {}"
                                                .format(value))

    buy_quantity = TEMPLATE.StrategyConfigField("Buy Quantity",
                                                "The maximum quantity that is allowed to be traded",
                                                float, mandatory="always")

    @buy_quantity.validator
    def buy_quantity(self, value):
        if value < 0:
            raise TEMPLATE.FieldValidationError("The parameter: buy_quantity; must not be a negative value, given: {}"
                                                .format(value))

    sell_discounted_quantity = TEMPLATE.StrategyConfigField("Sell Discounted Quantity",
                                                            "The Synthetic Order looks for the price where one could "
                                                            "buy this amount of Energy (max price)",
                                                            float, mandatory="always")

    @sell_discounted_quantity.validator
    def sell_discounted_quantity(self, value):
        if value <= 0:
            raise TEMPLATE.FieldValidationError("The parameter: sell_discounted_quantity; must be a positive value, "
                                                "given: {}".format(value))

    sell_spread = TEMPLATE.StrategyConfigField("Sell Spread",
                                               "The Synthetic Order places an order on the market with this spread "
                                               "behind the price of the Discounted Quantity",
                                               float, mandatory="always")

    @sell_spread.validator
    def sell_spread(self, value):
        if value <= 0:
            raise TEMPLATE.FieldValidationError("The parameter: sell_spread; must be a positive value, given: {}"
                                                .format(value))

    sell_slot_size = TEMPLATE.StrategyConfigField("Sell Order Quantity",
                                                  "The Synthetic Order places an order with that Quantity "
                                                  "on the market",
                                                  float, mandatory="always")

    @sell_slot_size.validator
    def sell_slot_size(self, value):
        if value < 0:
            raise TEMPLATE.FieldValidationError("The parameter: sell_slot_size; must be a non-negative value, given: {}"
                                                .format(value))

    sell_quantity = TEMPLATE.StrategyConfigField("Sell Quantity",
                                                 "The maximum quantity that is allowed to be traded",
                                                 float, mandatory="always")

    @sell_quantity.validator
    def sell_quantity(self, value):
        if value < 0:
            raise TEMPLATE.FieldValidationError("The parameter: sell_quantity; must not be a negative value, given: {}"
                                                .format(value))

    min_bid_ask_spread = TEMPLATE.StrategyConfigField("Min. bid/ask spread",
                                                      "The Synthetic Order only places orders if the bid/ask spread is "
                                                      "bigger than or equal to this value",
                                                      float, mandatory="never", default=None)

    @min_bid_ask_spread.validator
    def min_bid_ask_spread(self, value):
        if value is not None and value <= 0:
            raise TEMPLATE.FieldValidationError("The parameter: min_bid_ask_spread; must be a positive value, given: {}"
                                                .format(value))

    max_bid_ask_spread = TEMPLATE.StrategyConfigField("Max. bid/ask spread",
                                                      "The Synthetic Order only places orders if the bid/ask spread is "
                                                      "smaller than or equal to this value",
                                                      float, mandatory="never", default=None)

    @max_bid_ask_spread.validator
    def max_bid_ask_spread(self, value):
        if value is not None and value <= 0:
            raise TEMPLATE.FieldValidationError("The parameter: max_bid_ask_spread; must be a positive value, given: {}"
                                                .format(value))

    remove_if_traded = TEMPLATE.StrategyConfigField("Remove if (partially) traded",
                                                    "Relevant, if the Synthetic Order gets partially traded: If it is "
                                                    "not set, the Synthetic Order will remove the remaining quantity. "
                                                    "If this is not set, the Synthetic Order will leave the remaining "
                                                    "quantity on the market.",
                                                    bool, mandatory="always", default=False)

    removal_seconds = TEMPLATE.StrategyConfigField("Removal seconds",
                                                   "The order is removed if some part of the Synthetic Order "
                                                   "has been traded within the last x seconds defined by "
                                                   "this parameter and remove_if_traded parameter is set to True.",
                                                   int, mandatory="never", default=0)

    remove_both_sides = TEMPLATE.StrategyConfigField("Remove both sides",
                                                     "The order is removed on both side if remove_if_traded parameter "
                                                     "is set to True and the product is traded "
                                                     "on either side. For example, if it is traded on buy side, "
                                                     "the order is removed on both sides; same for sell.",
                                                     bool, mandatory="always", default=False)

    include_own_manual = TEMPLATE.StrategyConfigField("Include Own Orders",
                                                      "Flag to decide if the own orders should be taken into "
                                                      "consideration when calculating price and bid/ask spread",
                                                      bool, mandatory="always", default=False)

    only_tradable = TEMPLATE.StrategyConfigField("Only Tradable",
                                                 "Flag to decide if only tradable orders should be taken into "
                                                 "consideration when calculating price and bid/ask spread",
                                                 bool, mandatory="always", default=True)

    commingled_instruments = TEMPLATE.StrategyConfigField("Commingled instruments",
                                                          "The list of instrument IDs for commingled view used to "
                                                          "calculate the price",
                                                          TEMPLATE.AdditionalViewType, mandatory="never")

    @classmethod
    def get_attribute_groups(cls):
        groups = super(MarketMakerTemplate, cls).get_attribute_groups()
        # Append the commingled_instruments to the general settings group
        groups[0]["config_fields"].append("commingled_instruments")
        groups.append({"caption": "Calendar Settings",
                       "description": "Settings which calendars / products should be used",
                       "config_fields": ["sequence_settings"]})
        groups.append({"caption": "Order settings",
                       "description": "Settings for the orders on the market",
                       "config_fields": ["buy_discounted_quantity", "buy_spread", "buy_slot_size", "buy_quantity",
                                         "sell_discounted_quantity", "sell_spread", "sell_slot_size", "sell_quantity",
                                         "min_bid_ask_spread", "max_bid_ask_spread",
                                         "remove_if_traded", "removal_seconds", "remove_both_sides",
                                         "include_own_manual", "only_tradable"]})
        return groups
