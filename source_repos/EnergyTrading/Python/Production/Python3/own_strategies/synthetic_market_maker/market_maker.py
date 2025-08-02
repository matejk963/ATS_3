import math
import logging

import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRATEGY
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.errors as ERR
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
import autotrader_synthetic.commingled_view as CV
import autotrader_synthetic.factory_view as FV
import autotrader_lib.package_config_fields as PKG_CONF

log = logging.getLogger("synthetic_market_maker.MarketMakerOrder")


class MarketMaker(SYB.SyntheticOrderBase):
    direction = SYNCONF.SyntheticOrderConfigField("direction",
                                                  "The side of the order_book: buy or sell",
                                                  expected_type=PKG_CONF.Enum(allowed_values=["buy", "sell"]),
                                                  mandatory=True)

    slot_size = SYNCONF.SyntheticOrderConfigField("slot_size", "Specifies the size of the orders to be placed in MW",
                                                  expected_type=float, default=5., mandatory=True)

    # Used to handle remove_both_sides:
    other_slot_name = SYNCONF.SyntheticOrderConfigField("other_slot_name",
                                                        "Slot name of the synthetic order on the opposite side of the "
                                                        "order book.",
                                                        expected_type=str, mandatory=True)

    discounted_quantity = SYNCONF.SyntheticOrderConfigField("discounted_quantity",
                                                            "The level of the quantity at which we wish to place an "
                                                            "order behind", expected_type=float, default=1,
                                                            mandatory=True)

    spread = SYNCONF.SyntheticOrderConfigField("spread",
                                               "How much behind the discounted quantity price do we want to be",
                                               expected_type=float,
                                               default=0.2, mandatory=True)

    quantity = SYNCONF.SyntheticOrderConfigField("quantity",
                                                 "The maximum quantity that is allowed to be traded",
                                                 expected_type=float, default=0, mandatory=True)

    min_bid_ask_spread = SYNCONF.SyntheticOrderConfigField("min_bid_ask_spread",
                                                           "Specifies minimum value of spread that allows to place "
                                                           "the orders", expected_type=float, mandatory=False)

    max_bid_ask_spread = SYNCONF.SyntheticOrderConfigField("max_bid_ask_spread",
                                                           "Specifies maximum value of spread that allows to place "
                                                           "the orders", expected_type=float, mandatory=False)

    remove_if_traded = SYNCONF.SyntheticOrderConfigField("remove_if_traded",
                                                         "Specifies if traded part of Synthetic order will be deleted",
                                                         expected_type=bool,
                                                         default=False, mandatory=True)

    removal_seconds = SYNCONF.SyntheticOrderConfigField("removal_seconds",
                                                        "Specifies the seconds that determine the interval to check "
                                                        "if some part of the Synthetic order has been traded "
                                                        "within the last defined seconds", expected_type=int)

    remove_both_sides = SYNCONF.SyntheticOrderConfigField("remove_both_sides",
                                                          "Specifies the possibility to remove the order on both "
                                                          "sides if the product is traded on either side (if it is "
                                                          "traded on buy, the order is removed on both sides; same "
                                                          "for sell)",
                                                          expected_type=bool, mandatory=True,
                                                          default=False)

    include_own_manual = SYNCONF.SyntheticOrderConfigField("include_own_manual",
                                                           "Flag to decide if the own orders should be taken into "
                                                           "consideration when calculating price and bid/ask spread",
                                                           expected_type=bool, mandatory=True,
                                                           default=False)

    only_tradable = SYNCONF.SyntheticOrderConfigField("only_tradable",
                                                      "Flag to decide if only tradable orders should be taken into "
                                                      "consideration when calculating price and bid/ask spread",
                                                      expected_type=bool, mandatory=True, default=True)

    # read only fields, so that the mongo DB values be represented on the screen
    # these values are not only the recent quantities, but the totals
    traded_quantity_buy = SYNCONF.SyntheticOrderConfigField(
        caption="total traded quantity buy",
        description="The already bought quantity.",
        expected_type=float, mandatory=True, default=0.0, read_only=True, include_in_tooltip=True)

    traded_quantity_sell = SYNCONF.SyntheticOrderConfigField(
        caption="total traded quantity sell",
        description="The already sold quantity.",
        expected_type=float, mandatory=True, default=0.0, read_only=True, include_in_tooltip=True)

    remaining_quantity = SYNCONF.SyntheticOrderConfigField(
        caption="remaining quantity",
        description="The remaining quantity (quantity-traded quantity).",
        expected_type=float, mandatory=True, default=0.0, read_only=True, include_in_tooltip=True)

    # region Main Behavior

    def act(self, localview, additional_views, timestamp):
        view = self._get_view(additional_views, localview)
        price = view.current_order_price(self.direction, self.discounted_quantity, only_tradable=self.only_tradable,
                                         include_own_manual=self.include_own_manual)

        if self.removal_seconds:
            timerange = (timestamp - self.removal_seconds, timestamp)
        else:
            timerange = None

        # take into account if we potentially got traded
        traded_volume_recent = (localview.traded_volume_buy(self.slot_name, timerange)
                                if self.direction == COMMON.Direction.buy
                                else localview.traded_volume_sell(self.slot_name, timerange))
        total_traded_volume = (localview.traded_volume_buy(self.slot_name)
                               if self.direction == COMMON.Direction.buy
                               else localview.traded_volume_sell(self.slot_name))

        # calculate the read only fields
        self.traded_quantity_buy = localview.traded_volume_buy(self.slot_name)
        self.traded_quantity_sell = localview.traded_volume_sell(self.slot_name)

        # take into account if we potentially got traded on the other side
        if self.remove_both_sides:
            traded_volume_recent += (localview.traded_volume_buy(self.other_slot_name, timerange)
                                     if self.direction == COMMON.Direction.sell
                                     else localview.traded_volume_sell(self.other_slot_name, timerange))

        # if you change the slot size in between, it should take into account orders already on the market
        exposed_volume = localview.exposed_order_volume(self.slot_name)

        # bid_ask_spread of the front orders of the public orderbook
        bid_ask_spread = view.current_front_price_spread(only_tradable=self.only_tradable,
                                                         include_own_manual=self.include_own_manual)
        self.remaining_quantity = self.quantity - total_traded_volume

        public_buy_depth = view.current_orders_depth(COMMON.Direction.buy, self.broker_id)
        public_sell_depth = view.current_orders_depth(COMMON.Direction.sell, self.broker_id)

        buy_ids = view.get_current_public_order_ids(COMMON.Direction.buy)
        sell_ids = view.get_current_public_order_ids(COMMON.Direction.sell)

        # log for debugging purposes
        log.debug("SETTINGS: slot_size: %s, spread: %s, discounted_quantity: %s, min_bid_ask_spread: %s, "
                  "max_bid_ask_spread: %s, remove_if_traded: %s, removal_seconds: %s, remove_both_side: %s, "
                  "include_own_manual: %s, only_tradable: %s, "
                  "SITUATION: price: %s, total_traded_volume: %s, traded_volume_recent: %s, exposed_volume: %s, "
                  "bid_ask_spread: %s, remaining_quantity: %s, slot_name: %s, other_slot_name: %s, timerange: %s, "
                  "public_buy_depth: %s, public_sell_depth: %s, public_buy_ids: %s, public_sell_ids: %s",
                  self.slot_size, self.spread, self.discounted_quantity, self.min_bid_ask_spread,
                  self.max_bid_ask_spread, self.remove_if_traded, self.removal_seconds, self.remove_both_sides,
                  self.include_own_manual, self.only_tradable, price, total_traded_volume, traded_volume_recent,
                  exposed_volume, bid_ask_spread, self.remaining_quantity, self.slot_name, self.other_slot_name,
                  timerange, public_buy_depth, public_sell_depth, buy_ids, sell_ids)

        if self.remaining_quantity <= 0:
            return self.remove("Remaining quantity {!r} <= 0".format(self.remaining_quantity))

        # Scenario: Spread is lower than defined minimum value of spread, order is removed
        if self.min_bid_ask_spread is not None and bid_ask_spread < self.min_bid_ask_spread:
            log.debug("Front Price Spread %s is lower than specified min_bid_ask_spread %s", bid_ask_spread,
                      self.min_bid_ask_spread)
            return self.remove(
                "Front Price Spread {!r} is lower than specified min_bid_ask_spread {!r}".format(
                    bid_ask_spread, self.min_bid_ask_spread))

        # Scenario: Spread is higher than defined maximum value of spread, order is removed
        if self.max_bid_ask_spread is not None and bid_ask_spread > self.max_bid_ask_spread:
            log.debug("Front Price Spread %s is higher than specified max_bid_ask_spread %s", bid_ask_spread,
                      self.max_bid_ask_spread)
            return self.remove(
                "Front Price Spread {!r} is higher than specified max_bid_ask_spread {!r}".format(
                    bid_ask_spread, self.max_bid_ask_spread))

        # Scenario: Some part of Synthetic order has been traded and the 'remove_if_traded' parameter is set to 'True'
        # so the synthetic order must be removed
        if self.remove_if_traded and traded_volume_recent:
            log.debug("Part of the synthetic order was traded and 'remove_if_traded' parameter is set to True,"
                      "removing orders")
            return self.remove("Part of the synthetic order was traded and 'remove_if_traded' parameter is set to True")

        # Scenario: Slot size is 0, remove exposed orders
        if self.slot_size == 0:
            log.debug("Slot size is 0, removing orders")
            return self.remove("Slot size is 0")

        # Scenario: There are no more orders
        if price is None:
            log.debug("No more orders (or not enough volume) on the market, removing own")
            return self.remove("No more orders (or not enough volume) on the market")

        quantity_to_place = min(self.remaining_quantity, self.slot_size)
        return self.create_slot(self.direction, quantity_to_place, self._adjust_price(price))

    def _adjust_price(self, reference_price):
        """Adjust price with spread, round price away from spread and adjust according to tick size

        :param reference_price: price to be rounded
        :type reference_price: float
        :return: rounded price
        :rtype: float
        """
        if self.direction == COMMON.Direction.buy:
            return round(
                math.floor(round((reference_price - self.spread) / self.tick_size, 4)) * self.tick_size,
                COMMON.MACHINE_ERROR_DIGITS
            )
        else:
            return round(
                math.ceil(round((reference_price + self.spread) / self.tick_size, 4)) * self.tick_size,
                COMMON.MACHINE_ERROR_DIGITS
            )

    # endregion

    # region Configuration Verification

    def _verify_slot_size(self, slot_size):
        if slot_size < 0:
            raise ERR.ConfigurationError("The parameter: slot_size; must be a non-negative value, "
                                         "given: %s" % slot_size)

        # slot size 0 is now used for disabling a sequence
        if 0 < slot_size < self.tick_size:  # TODO: Tick size quantity is not the same
            raise ERR.ConfigurationError("The parameter: slot_size; must be at least %s, given %s" %
                                         (self.tick_size, slot_size))

        if not STRATEGY.is_integer_multiple(slot_size, self.tick_size):
            raise ERR.ConfigurationError(
                "The parameter: slot_size; must be an integer multiple of %s (price tick), but was %s" %
                (self.tick_size, slot_size)
            )

    def _verify_spread(self, spread):
        if spread <= 0:
            raise ERR.ConfigurationError("The parameter: spread; must be a positive value, given: %s" % spread)

        if spread < self.tick_size:
            raise ERR.ConfigurationError("The parameter: spread; must be at least %s, given %s" %
                                         (self.tick_size, spread))

    def _verify_discounted_quantity(self, discounted_quantity):
        if discounted_quantity <= 0:
            raise ERR.ConfigurationError("The parameter: discounted_quantity; must be a positive value, given: %s" %
                                         discounted_quantity)

        if discounted_quantity < self.tick_size:
            raise ERR.ConfigurationError("The parameter: discounted_quantity; must be at least %s, given %s" %
                                         (self.tick_size, discounted_quantity))

    @staticmethod
    def _verify_min_bid_ask_spread(min_bid_ask_spread):
        if min_bid_ask_spread is not None and min_bid_ask_spread <= 0:
            raise ERR.ConfigurationError("The parameter: min_bid_ask_spread; must be a positive value, given: {}"
                                         .format(min_bid_ask_spread))

    @staticmethod
    def _verify_max_bid_ask_spread(max_bid_ask_spread):
        if max_bid_ask_spread is not None and max_bid_ask_spread <= 0:
            raise ERR.ConfigurationError("The parameter: max_bid_ask_spread; must be a positive value, given: {}"
                                         .format(max_bid_ask_spread))

    @staticmethod
    def _verify_remove_if_traded(remove_if_traded):
        if not isinstance(remove_if_traded, bool):
            raise ERR.ConfigurationError("The parameter: remove_if_traded; must be of boolean type, given: {}"
                                         .format(remove_if_traded))

    @staticmethod
    def _get_view(additional_views, localview):
        try:
            if additional_views is not None and isinstance(additional_views, FV.ViewFactory):
                view = additional_views.get_configured_view("commingled_instruments", localview.product_id)
            else:
                view = localview
        except (FV.ViewNotConfigured, CV.EmptyMarketAreas):
            view = localview
        return view

    def configure(self, incoming_configuration_dict):
        # we can do additional verification of the configuration.
        for config_name in ["slot_size", "spread", "discounted_quantity", "min_bid_ask_spread", "max_bid_ask_spread",
                            "remove_if_traded"]:
            if config_name in incoming_configuration_dict:
                verification_func = getattr(self, "_verify_{}".format(config_name))
                verification_func(incoming_configuration_dict.get(config_name))

        super(MarketMaker, self).configure(incoming_configuration_dict)

    # endregion
