import collections
import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.errors as ERR
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT

from . import market_maker


log = logging.getLogger("SyntheticMarketMaker")

product_span = collections.namedtuple("product_span", ["span_from", "span_until"])
BOTH_DIRECTIONS = (COMMON.Direction.buy, COMMON.Direction.sell)
PARAMETERS = ("buy_slot_size", "buy_spread", "buy_discounted_quantity", "buy_quantity", "sell_slot_size",
              "sell_spread", "sell_discounted_quantity", "sell_quantity", "remove_if_traded",
              "min_bid_ask_spread", "max_bid_ask_spread", "removal_seconds", "remove_both_sides",
              "include_own_manual", "only_tradable")


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    # We allow the user to reconfigure our synthetic orders,
    # but not to delete/ create synthetic orders.
    allowed_synthetic_order_operations = [COMMON.SyntheticOrderOperations.modify]

    # region Strategy Settings & Configuration

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        COMMON.OTR = 100000000000000000

        self.broker_id = None
        self._sequence_settings = dict()
        self._valid_products = set()

        self.buy_slot_size = None
        self.buy_discounted_quantity = None
        self.buy_spread = None
        self.buy_quantity = None
        self.sell_slot_size = None
        self.sell_discounted_quantity = None
        self.sell_spread = None
        self.sell_quantity = None

        self.min_bid_ask_spread = None
        self.max_bid_ask_spread = None
        self.remove_if_traded = False
        self.removal_seconds = None
        self.remove_both_sides = False
        self.include_own_manual = False
        self.only_tradable = True

    def get_current_time(self):
        """
        Get the current time in a way that works on production and backtesting.
        """
        return self.autotrader.current_timestamp

    def on_strategy_configuration_update(self, strategy_json):
        """
        Called when we receive a new configuration from the REST-API.
        """
        log.debug("Running on_strategy_configuration_update")
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        self.broker_id = str(strategy_json["broker_id"])

        if "sequence_settings" in strategy_json and strategy_json["sequence_settings"] is not None:
            parsed_settings = self._parse_sequence_settings(strategy_json["sequence_settings"])
            self._set_sequence_settings(parsed_settings)

        self._set_default_parameters(strategy_json)

        self._reevaluate_products(self.get_current_time())

        self.act(timestamp=self.get_current_time(),
                 products=self.exchange.products.get_active_products(self.delivery_area_id))

    @staticmethod
    def _parse_sequence_settings(setting_string):
        log.debug("Received sequence settings string: %s", setting_string)
        result = list()
        if setting_string == "":
            return result

        split_lines = setting_string.split(";")
        for line in split_lines:
            seq_id, from_rel, until_rel = line.split(",")
            result.append({"sequence_id": str(seq_id),
                           "sequence_item_from_relative": int(from_rel),
                           "sequence_item_until_relative": int(until_rel)})
        log.debug("Parsed sequence settings string into: %s", result)
        return result

    def _set_sequence_settings(self, incoming_sequence_settings_json):
        new_sequence_settings = dict()
        for line in incoming_sequence_settings_json:
            new_sequence_settings[line["sequence_id"]] = product_span(line["sequence_item_from_relative"],
                                                                      line["sequence_item_until_relative"])
        self._sequence_settings = new_sequence_settings

    def _set_default_parameters(self, strategy_json):
        for parameter in PARAMETERS:
            parameter_value = strategy_json.get(parameter)
            setattr(self, parameter, parameter_value)

    # endregion

    # region Product Management

    def custom_on_products_update(self, products, timestamp):
        """
        When new products become available, we immediately register a synthetic order,
        which will become active at a certain time.
        """
        self._reevaluate_products(timestamp)
        self.act(timestamp, products)

    def _reevaluate_products(self, timestamp):
        # first establish correct validities
        self._set_valid_products(timestamp)
        log.debug("Re-evaluating products, current mapping %s" % self._product_synthetic_order_mapping)

        # First, delete all Synthetic orders from sequences that are no longer configured.
        for product_id, so_dict in self.product_synthetic_order_mapping.items():
            parts = product_id.split("_")
            seq_id = parts[1] if parts[0] == "dummy" else parts[0]
            if seq_id not in self._sequence_settings:
                log.debug("Deleting SOs for {} because sequence_id {} is not configured".format(product_id, seq_id))
                for synth_order in so_dict.values():
                    synth_order.delete(
                        status_text="sequence_id {!r} is not configured for product {!r}".format(seq_id, product_id))

        # now iterate over all the products
        for product in self.exchange.products.iter_by_sequence_ids(self._sequence_settings):
            current_product_id = product.product_id
            log_text = "Re-evaluating Product: {} ({})".format(product.name, current_product_id)
            appended_log_text = None

            # find any product that already has a registered synthetic order
            orders_by_identifier = self._product_synthetic_order_mapping.get(current_product_id, {})
            if orders_by_identifier:  # and we have some values

                # if the product is no longer valid, mark the synthetic order for deletion
                if current_product_id not in self._valid_products:
                    for synth_ord in orders_by_identifier.values():
                        synth_ord.delete(status_text="Product is no longer valid")
                    appended_log_text = "Product is no longer valid! Marking both synthetic orders for deletion."

                # if an existing product is still valid, update its settings
                else:
                    log.debug("Modifying %s" % current_product_id)
                    # modify both sides
                    for direction in BOTH_DIRECTIONS:
                        so_config = self.get_synth_order_config(direction)
                        identifier = so_config["identifier"]
                        try:
                            self.on_synthetic_order_modify(current_product_id, so_config)
                        except ERR.ConfigurationError as err:
                            self.warn_log("Could not reconfigure Synthetic order {} due to error: "
                                          "{}. Deleting it".format(identifier, err))
                            self.on_synthetic_order_delete(current_product_id, {"identifier": identifier})
                    appended_log_text = "Product still valid! Modifying both synthetic orders."

            # if the product is not yet registered
            else:

                # if the product is valid register new ones
                if product.product_id in self._valid_products:
                    for direction in BOTH_DIRECTIONS:
                        try:
                            self.on_synthetic_order_register(current_product_id, self.get_synth_order_config(direction))
                        except ERR.ConfigurationError as err:
                            self.warn_log("Cannot register synthetic order. Reason: {}".format(err), product)

                    appended_log_text = "New product valid! Registering buy and sell side synthetic orders."

            # do not log the skipped ones so the logs are not flooded
            if appended_log_text:
                log.debug(" ".join([log_text, appended_log_text]))

    def _set_valid_products(self, current_timestamp):
        """ This helper function establishes which products should currently be traded on

        IMPORTANT: This function should be run everytime the settings change,
        any everytime products change to ensure integrity

        :param current_timestamp:
        :return: None
        """
        configured_products = collections.defaultdict(list)
        for product in self.exchange.products.iter_by_sequence_ids(self._sequence_settings):
            sequence_id = product.product_id.split("_")[0]
            if sequence_id in self._sequence_settings:
                configured_products[sequence_id].append(product)

        valid_product_ids = set()
        for curr_seq_id, products_list in configured_products.items():
            future_products = [product for product in products_list if product.delivery_start >= current_timestamp]
            future_products.sort(key=lambda p: (p.delivery_start, p.delivery_end))
            prod_span = self._sequence_settings[curr_seq_id]

            products_within_span = future_products[prod_span.span_from:prod_span.span_until + 1]  # last is inclusive
            valid_product_ids.update(p.product_id for p in products_within_span)

        self._valid_products = valid_product_ids
        log.debug("The currently valid product ids are: %s", valid_product_ids)

    # endregion

    # region Synthetic Order Settings

    def get_synth_order_config(self, direction):
        """
        Get the default config of the synthetic orders, based on the strategy config.
        """
        is_buy = direction == COMMON.Direction.buy
        config = {"broker_id": self.broker_id,
                  "slot_name": "{}_synthetic_order".format(direction),
                  "other_slot_name": "{}_synthetic_order".format(COMMON.Direction.invert(COMMON.Direction(),
                                                                                         order_type=direction)),
                  "market_area": self.delivery_area_id,
                  "direction": direction,
                  "slot_size": self.buy_slot_size if is_buy else self.sell_slot_size,
                  "discounted_quantity": self.buy_discounted_quantity if is_buy else self.sell_discounted_quantity,
                  "quantity": self.buy_quantity if is_buy else self.sell_quantity,
                  "spread": self.buy_spread if is_buy else self.sell_spread,
                  "min_bid_ask_spread": self.min_bid_ask_spread,
                  "max_bid_ask_spread": self.max_bid_ask_spread,
                  "remove_if_traded": self.remove_if_traded,
                  "removal_seconds": self.removal_seconds,
                  "remove_both_sides": self.remove_both_sides,
                  "include_own_manual": self.include_own_manual,
                  "only_tradable": self.only_tradable,
                  }

        payload = {"synthetic_order_type": "MarketMaker",
                   "message_type": COMMON.SyntheticMessageType.order,
                   "identifier": "{}_synthetic_order".format(direction),
                   "configuration": config}
        return payload

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"MarketMaker": market_maker.MarketMaker}

    # endregion
