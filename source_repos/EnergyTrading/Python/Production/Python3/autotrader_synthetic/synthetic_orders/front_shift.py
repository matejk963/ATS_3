from __future__ import absolute_import
import numbers
import six
if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG
import autotrader_lib.common as COMMON

import autotrader_synthetic.config_util as CONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

LOGGER_NAME = "synthetic_orders.front_shift"
log = FLOG.getLogger(LOGGER_NAME)


class SimpleFrontShift(SYB.SyntheticOrderBase):
    """
    Place an order with a fixed shift relative to the front.
    """
    # positive = buy energy, negative: sell energy
    position = CONF.ConfigOptionDescriptor("position", numbers.Number, "Total position to buy or sell", required=True)

    # Absolute quantity
    slot_size = CONF.ConfigOptionDescriptor("slot_size", numbers.Number, "Size of the slot", required=True)

    # Positive means in front, negative means behind the front
    shift = CONF.ConfigOptionDescriptor("shift", numbers.Number, "Shift from the front", required=True)

    # in EUR
    min_spread = CONF.ConfigOptionDescriptor("min_spread", numbers.Number,
                                             "Minimum safety distance to the other side of the orderbook")

    # in % of historic spread. E.g. 0.6 means at least stay 60% of the historic spread away from the other side.
    min_spread_percent_historic = CONF.ConfigOptionDescriptor("min_spread_percent_historic", numbers.Number,
                                                              "Minimum safety distance to the other side of the "
                                                              "orderbook, in percent of the historic spread")

    # the historic spread is calculated from the spreads between historic seconds in the past and now.
    # Note that the historic data is only stored in 10 seconds raster, so the actual used historic data might
    # deviate +-10 seconds from the configured value, depending on the time of slot placement.
    # Only data for at most 5 minutes in the past is available.
    historic_spread_seconds = CONF.ConfigOptionDescriptor("historic_spread_seconds", int,
                                                          "Number of seconds to use of the historic spread calculation")

    # avg or max
    historic_spread_method = CONF.ConfigOptionDescriptor("historic_spread_method", str,
                                                         "Method with which to aggregate the spread")

    # small front order then you place a smaller quantity depending on its size
    max_volume_front_percent = CONF.ConfigOptionDescriptor("max_volume_front_percent", numbers.Number,
                                                           "If you place in front of a small public order, place at "
                                                           "most that many percent of the quantity of the front order")

    # On EPEX, making too tiny trades counts as OTR violation, so we allow configuring a minimum volume
    min_volume = CONF.ConfigOptionDescriptor(name="min_volume", config_type=numbers.Number,
                                             description="Minimum volume for orders (Only triggered in "
                                                         "combination with max_volume_front_percent)", default=1.)

    def act(self, localview, additional_views, timestamp):
        remaining_volume = self.position - self.traded_volume(localview)
        direction = COMMON.Direction.buy if remaining_volume > 0 else COMMON.Direction.sell

        # GET THE VOLUME

        slot_volume = abs(remaining_volume)

        if slot_volume == 0:
            log.debug("The position is filled")
            return self.remove(status_text="The position is filled")

        if self.max_volume_front_percent is not None:
            public_front_volume = localview.current_front_volume(direction, only_tradable=False)
            slot_volume = min(slot_volume, public_front_volume * self.max_volume_front_percent)
            if self.min_volume is not None:
                slot_volume = max(slot_volume, self.min_volume)
        else:
            public_front_volume = None

        slot_volume = min(slot_volume, abs(remaining_volume), self.slot_size)

        # GET THE PRICE

        sign = 1 if direction == COMMON.Direction.buy else -1
        capped = min if direction == COMMON.Direction.buy else max

        front_price = localview.current_front_price(direction)
        other_front_price = localview.current_front_price("sell" if direction == COMMON.Direction.buy else "buy")

        target_price = front_price + self.shift * sign

        # Use the spread_safety mechanism to prevent us from placing too aggressively
        if self.min_spread is not None and other_front_price is not None:
            limit_price_from_min_spread = other_front_price - self.min_spread * sign
        else:
            limit_price_from_min_spread = None

        if (self.historic_spread_seconds is not None
                and self.historic_spread_method is not None
                and self.min_spread_percent_historic is not None):
            historic_spread = localview._get_aggregated_historic_spread(self.historic_spread_seconds,
                                                                        self.historic_spread_method)
            limit_price_from_historic_spread = (other_front_price
                                                - historic_spread * self.min_spread_percent_historic * sign)
        else:
            limit_price_from_historic_spread = None

        final_price = target_price
        if limit_price_from_min_spread:
            final_price = capped(final_price, limit_price_from_min_spread)
        if limit_price_from_historic_spread:
            final_price = capped(final_price, limit_price_from_historic_spread)

        # Think about logging here
        # Have an automatic log mechanism
        log.debug("SimpleFrontShift: remaining_volume: %s, slot_volume: %s (%s), public_front_volume: %s"
                  " front_prices: %s and %s, target_price: %s,"
                  " limit_price_from_min_spread: %s, limit_price_from_historic_spread: %s, final_price: %s",
                  remaining_volume, slot_volume, direction, public_front_volume,
                  front_price, other_front_price, target_price,
                  limit_price_from_min_spread, limit_price_from_historic_spread, final_price)
        return self.create_slot(direction, quantity=slot_volume, price=final_price)


if __name__ == "__main__":
    raise RuntimeError("Tis module should ne be directly executed")  # pragma: no cover
