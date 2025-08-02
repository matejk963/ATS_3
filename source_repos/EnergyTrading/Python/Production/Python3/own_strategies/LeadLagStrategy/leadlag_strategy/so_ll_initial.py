import logging
import time

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats, get_price_diff_depth, aon_check
from .own_tools.misc import round_to_tick, max_with_none_check, min_with_none_check, unix_timestamp_to_cet_string


log = logging.getLogger("leadlag.LL_Initial_order")

#QUANTITY_TICK_SIZE = 10

class InitialOrder(SYB.SyntheticOrderBase):

    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    lead_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lead_instrument_id", str,
        "Lead Instrument ID, which is used to know when to trade",
        required=True
    )

    lead_product_id = SYNCONF.ConfigOptionDescriptor(
        "lead_product_id", str,
        "Lead Product ID, which is used to know when to trade",
        required=True
    )

    lag_product_id = SYNCONF.ConfigOptionDescriptor(
        "lag_product_id", str,
        "Lag Product ID, this product ID is used for trading",
        required=True
    )

    ######################################################################################################################################################
    # main strategy parameters

    MACD_long_threshold = SYNCONF.SyntheticOrderConfigField(
        caption="MACD_long_threshold",
        expected_type=float,
        description="MACD_long_threshold"
    )

    MACD_short_threshold = SYNCONF.SyntheticOrderConfigField(
        caption="MACD_short_threshold",
        expected_type=float,
        description="MACD_short_threshold"
    )

    price_diff_long_threshold = SYNCONF.SyntheticOrderConfigField(
        caption="price_diff_long_threshold",
        expected_type=float,
        description="price_diff_long_threshold"
    )

    price_diff_short_threshold = SYNCONF.SyntheticOrderConfigField(
        caption="price_diff_short_threshold",
        expected_type=float,
        description="price_diff_short_threshold"
    )

    combined_long_threshold = SYNCONF.SyntheticOrderConfigField(
        caption="combined_long_threshold",
        expected_type=float,
        description="combined_long_threshold"
    )

    combined_short_threshold = SYNCONF.SyntheticOrderConfigField(
        caption="combined_short_threshold",
        expected_type=float,
        description="combined_short_threshold"
    )

    reg_model_coef1 = SYNCONF.SyntheticOrderConfigField(
        caption="reg_model_coef1",
        expected_type=float,
        description="reg_model_coef1"
    )

    reg_model_coef2 = SYNCONF.SyntheticOrderConfigField(
        caption="reg_model_coef2",
        expected_type=float,
        description="reg_model_coef2"
    )

    combined_mode = SYNCONF.SyntheticOrderConfigField(
        caption="combined_mode",
        expected_type=bool,
        description="To use simple thresholds or combined threshold",
    )

    minimum_intensity = SYNCONF.SyntheticOrderConfigField(
        caption="minimum_intensity",
        expected_type=float,
        description="minimum_intensity"
    )
    ######################################################################################################################################################

    ba_max = SYNCONF.SyntheticOrderConfigField(
        caption="ba_max",
        expected_type=float,
        description="Bid-Ask spread maximum"
    )

    closing_slot_name = SYNCONF.ConfigOptionDescriptor(
        "closing_slot_name", str,
        "Name of the closing slot"
    )

    closing_product_id = SYNCONF.ConfigOptionDescriptor(
        "closing_product_id", str,
        "Product ID of the Gas product to be used as closing order, which closes this orders 2nd leg"
    )

    closing_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "closing_instrument_id", str,
        "Name of the closing instrument additional view, as used in the strategy template"
    )


    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats_dict",
        expected_type=dict,
        description="Object for strategy statistics"
    )

    max_quantity = SYNCONF.SyntheticOrderConfigField(
        caption="max_quantity",
        expected_type=float,
        description="What is the maximum slot_size",
    )

    ql_max = SYNCONF.SyntheticOrderConfigField(
        caption="maximal_allowed_queue_lag",
        expected_type=float,
        description="Maximal allowed queue lag for strategy",
    )

    reset_bool = SYNCONF.SyntheticOrderConfigField(
        caption="autoTrader_reset",
        expected_type=bool,
        description="autoTrader reset boolean",
    )
    def act(self, localview, additional_views, timestamp):

        lead_market_view = additional_views.get_view_for_instrument(
            self.lead_instrument_id,
            self.lead_product_id
        )

        self.strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)

        self.local_buy, self.local_buy_volume  = localview.current_front_price(COMMON.Direction.buy), localview.current_front_volume(COMMON.Direction.buy)
        self.local_sell, self.local_sell_volume = localview.current_front_price(COMMON.Direction.sell), localview.current_front_volume(COMMON.Direction.sell)

        if self.slot_name in self.strategy_stats.slot_dict:
            net_traded_own = self.strategy_stats.slot_dict[self.slot_name]['net_volume']
        else:
            net_traded_own = 0

        if self.closing_slot_name in self.strategy_stats.slot_dict:
            net_traded_closing = self.strategy_stats.slot_dict[self.closing_slot_name]['net_volume']
        else:
            net_traded_closing = 0

        abs_net_open_position = abs(net_traded_own + net_traded_closing)
        self.abs_net_open_position=abs_net_open_position

        self.inst_key=self.market_area + "_" + self.lag_product_id
        self.ql=self.strategy_stats.aux_dict['ql']
        self.ql=0 if self.ql is None else self.ql

        if self.local_sell and self.local_buy:
            self.ba_spread=self.local_sell-self.local_buy
        else:
            self.ba_spread = None
            return self.remove_slot_info()

        self.parameter_dict={
            "MACD_long_threshold": self.MACD_long_threshold,
            "MACD_short_threshold": self.MACD_short_threshold,
            "price_diff_long_threshold": self.price_diff_long_threshold,
            "price_diff_short_threshold": self.price_diff_short_threshold,
            "combined_long_threshold": self.combined_long_threshold,
            "combined_short_threshold": self.combined_short_threshold,
            "reg_model_coef1": self.reg_model_coef1,
            "reg_model_coef2": self.reg_model_coef2,
            "combined_mode": self.combined_mode,
            "minimum_intensity": self.minimum_intensity
        }

        if abs_net_open_position == 0:
            self.strategy_stats.bool_dict['trail_stop_flag'] = False

        if abs_net_open_position == 0 and self.ba_spread<=self.ba_max and self.ql<=self.ql_max and not self.reset_bool and not self.strategy_stats.bool_dict['hard_stop_loss']:

            if self.strategy_stats.check_for_new_lead_trade():
                action=self.strategy_stats.calculate_action(lead_market_view, localview, self.local_buy, self.local_sell, self.parameter_dict)
                self.strategy_stats.aux_dict['last_action']=action

            elif self.strategy_stats.check_one_second_within_last_lead_trade():
                action = self.strategy_stats.calculate_action(lead_market_view, localview, self.local_buy,
                                                              self.local_sell, self.parameter_dict)
            else:
                action=0
                return self.remove_slot_info()

            if action==1:
                our_price = self.local_sell
                our_volume = min(self.local_sell_volume, self.max_quantity)
                aon = aon_check(self.strategy_id,localview, COMMON.Direction.sell, our_price, our_volume, self.market_area)
                if our_volume<=0. and aon:
                    self.strategy_stats.increment_paper_trading_list(COMMON.Direction.buy, our_price, our_volume, unix_timestamp_to_cet_string(time.time()))

                if aon:
                    return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                else:
                    return self.remove_slot_info()

            if action==-1:
                our_price = self.local_buy
                our_volume = min(self.local_buy_volume, self.max_quantity)
                aon = aon_check(self.strategy_id, localview, COMMON.Direction.buy, our_price, our_volume,
                                self.market_area)
                if our_volume <= 0. and aon:
                    self.strategy_stats.increment_paper_trading_list(COMMON.Direction.sell, our_price, our_volume,
                                                                     unix_timestamp_to_cet_string(time.time()))

                if aon:
                    return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                else:
                    return self.remove_slot_info()


        return self.remove_slot_info()

    def create_slot_info(self, direction, our_price, our_volume):
        log.debug(
            "[{}] LL-INITIAL-CREATE-SLOT-{}, {}@{},  [Public BUY/SELL]: LEAD_BEST_PRICES: {}[{}]: {}//{}".format(
                self.strategy_id, direction,our_price,our_volume, self.market_area, self.lag_product_id, self.local_buy if self.local_buy else -1.0,
                self.local_sell if self.local_sell else -1.0)
        )
        return self.create_slot(direction, our_volume, our_price, info="LL_INIT_"+direction.capitalize())

    def remove_slot_info(self):
        log.debug(
            "[{}] {} LL-INITIAL-REMOVE-SLOT: [abs_net_open_position: {}, ba_spread: {}, ql: {}, reset_bool: {}, hard_stop_loss: {}]".format(
                self.strategy_id, self.identifier, self.abs_net_open_position,self.ba_spread,self.ql, self.reset_bool, self.strategy_stats.bool_dict['hard_stop_loss'])
        )
        return self.remove()
