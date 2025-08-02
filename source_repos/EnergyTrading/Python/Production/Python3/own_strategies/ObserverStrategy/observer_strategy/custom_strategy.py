import logging
import numpy as np
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
import autotrader_lib.common as COMMON
import autotrader_synthetic.factory_view as FV
from .strategy_stats import StrategyStats
from .predictors_stats import PredictorsStats
from .own_tools.instrument_key import InstrumentKey
from .OB_attributes import OB_attributes
from .predictors import predictor_sparsity
import time


log = logging.getLogger("autotrader.observer_strategy")

class CustomStrategy(SYSB.SyntheticOrderStrategyBase):
    default_payload = {}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log
        self.timestamp = (int(time.time()) // 86400) * 86400
        self.initialized = False
        self.duplicity_trade_list = []

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        
        # Create boolean for shutdown
        self.reset_bool = False
        
        # Create InstrumentKey Lists
        instrument_id_list = self.delivery_areas
        product_id_list = strategy_json["product_ids"]
        self.instrument_keys = [InstrumentKey(inst_id, prod_id).key
                                for (inst_id, prod_id) in zip(instrument_id_list, product_id_list)]
        
        # Strategy parameters
        self.instrument_ids = instrument_id_list
        self.product_ids = product_id_list
        self.broker_list = strategy_json["broker_list"]
        
        # Initialize StrategyStats with proper naming convention
        self.stats = StrategyStats(None, self.strategy_id, self.caption)
        self.predictors = PredictorsStats(self.strategy_id)

        self.time_of_init = str(int(round(time.time())))
        
        if not self.initialized:
            self.stats.update_instruments(self.instrument_keys, self.time_of_init, {})
            try:
                self.ref_area = InstrumentKey(self.delivery_areas[0], self.product_ids[0]).key
            except IndexError:
                self.ref_area = None
            self.initialized = True

    def prepare_data_dict(self, localview, market_area, strategy_stats):
        """
        Prepare data dictionary for predictors from order book and trade data
        """
        try:
            obAttr = OB_attributes(localview, market_area)
            
            # Basic order book metrics
            data_dict = {
                'b_price': obAttr.bid_price(),
                'a_price': obAttr.ask_price(),
                'ba_spread': obAttr.ba_spread(),
                'mid_price': obAttr.mid_price(),
                'trd_price': strategy_stats.aux_dict['last_traded_price'] or 0,
                'trd_object': strategy_stats.aux_dict['trd_object'],
                'bid_volume': obAttr.bid_volume(),
                'ask_volume': obAttr.ask_volume(),
                'bid_broker': obAttr.bid_broker(),
                'ask_broker': obAttr.ask_broker(),
                
                # Order book depth metrics
                'n_bids': len(obAttr.bids),
                'n_asks': len(obAttr.asks),
                
                # Volume ratios at different depths
                'vol_ratio_0_1': obAttr.vol_ratio(0.1),
                'vol_ratio_0_5': obAttr.vol_ratio(0.5),
                'vol_ratio_1_0': obAttr.vol_ratio(1.0),
                
                # Weighted mid prices at different depths (like ba_volrat pattern)
                'mid_priceW_00': obAttr.mid_priceW(0.0),
                'mid_priceW_05': obAttr.mid_priceW(0.05),
                'mid_priceW_08': obAttr.mid_priceW(0.08),
                'mid_priceW_10': obAttr.mid_priceW(0.10),
                'mid_priceW_15': obAttr.mid_priceW(0.15),
                'mid_priceW_20': obAttr.mid_priceW(0.20),
                'mid_priceW_25': obAttr.mid_priceW(0.25),
                
                # BA volume ratios at different depths
                'ba_volrat_00': obAttr.vol_ratio(0.0),
                'ba_volrat_05': obAttr.vol_ratio(0.05),
                'ba_volrat_08': obAttr.vol_ratio(0.08),
                'ba_volrat_10': obAttr.vol_ratio(0.10),
                'ba_volrat_15': obAttr.vol_ratio(0.15),
                'ba_volrat_20': obAttr.vol_ratio(0.20),
                'ba_volrat_25': obAttr.vol_ratio(0.25),
            }
            
            # Sparsity metrics
            sparsity = predictor_sparsity(obAttr)
            data_dict = {**data_dict, **sparsity}
            
            return data_dict
        except Exception as e:
            self.log.error(f"[OBSERVER_PREPARE data_dict] - exception: {e}, lineno{e.__traceback__.tb_lineno}")
            return None






    def custom_on_order_book_update(self, orders, timestamp):
        """Observer strategy - no order book processing needed"""
        return {}

    def custom_on_public_trade_update(self, trades, timestamp):
        """Focus on public trade events - collect predictor data"""
        for trade in trades:
            # Check delivery area matching
            delivery_match = trade.match_delivery_areas(self.delivery_areas)
            product_match = trade.product.product_id in self.product_ids
            
            if delivery_match and product_match:
                self.log.info(f"[{self.strategy_id}] On Public Trade Update: {trade.buy_delivery_area}[{trade.product.product_id}]: {trade.quantity}@{trade.price} execution_time: {trade.execution_time}")
                
                # Filter trades like in original strategy
                if trade.portfolio_key is not None and 'arb' in trade.portfolio_key:
                    self.stats.log_trade_decision(trade.trade_id, "arbitrage_trade")
                    continue
                elif trade.trade_id in self.duplicity_trade_list:
                    self.stats.log_trade_decision(trade.trade_id, "duplicate_trade")
                    continue
                elif not (str(trade.initiator_broker_id) == str(self.broker_list[0]) or str(trade.aggressor_broker_id) == str(self.broker_list[0])):
                    self.stats.log_trade_decision(trade.trade_id, "not_eex_trade")
                    continue
                
                # Add to duplicity list
                self.duplicity_trade_list.append(trade.trade_id)
                
                # Update trade info in StrategyStats
                self.stats.update_trade_info(trade, trade.execution_time)
                
                # Process trade data directly - no condition checking, just collect predictors
                try:
                    # Create ViewFactory and LocalView
                    view_factory = FV.ViewFactory(self.exchange.products, self.strategy_id)
                    localview = view_factory.get_view_for_instrument(trade.buy_delivery_area, trade.product.product_id)
                    
                    # Prepare data dictionary using LocalView
                    data_dict = self.prepare_data_dict(localview, trade.buy_delivery_area, self.stats)
                    
                    if data_dict:
                        # Update predictors
                        self.predictors.update_values(data_dict)
                        
                        # Store calculated predictors in strategy_stats
                        self.stats.predictor_dict['timestamp'].append(timestamp)
                        self.stats.predictor_dict['trade_id'].append(trade.trade_id)
                        self.stats.predictor_dict['predictors'].append(self.predictors.predictors_dict.copy())
                        
                        # Add basic market data tracking
                        self.stats.market_data_dict['timestamp'].append(timestamp)
                        self.stats.market_data_dict['trade_id'].append(trade.trade_id)
                        self.stats.market_data_dict['trd_price'].append(trade.price)
                        self.stats.market_data_dict['b_price'].append(data_dict['b_price'])
                        self.stats.market_data_dict['a_price'].append(data_dict['a_price'])
                        
                except Exception as err:
                    self.log.error(f"Exception in trade processing: {err}")
                
        return {}

    def custom_on_trade_update(self, trades, timestamp):
        """Observer strategy does not execute its own trades, but log for debugging"""
        self.log.info(f"[DEBUG][{self.strategy_id}] custom_on_trade_update called with {len(trades)} trades")
        return {}

    def on_strategy_update(self, strategy_json):
        try:
            if "steering_call" in strategy_json:
                self.handle_steering_call(strategy_json["steering_call"])
            else:
                super(CustomStrategy, self).on_strategy_update(strategy_json)
        except Exception as err:
            self.delete_standing_orders()
            log.error(f"Exception in on_strategy_update: {err}")

    def handle_steering_call(self, payload):
        """Handle steering calls to export StrategyStats data"""
        payload_dict = {k: v for d in payload if isinstance(d, dict) for k, v in d.items()}
        
        self.log.info(f"[{self.strategy_id}] Steering call: {payload}")
        
        try:
            if "stats" in payload:
                self.api_export_timeseries({
                    "stats": ("Observer Strategy Statistics", "MW", "MW", COMMON.HOUR, 
                             {self.timestamp: {**self.stats.to_dict(), **{'reset_bool': self.reset_bool}}})
                })
            elif "comprehensive_metrics" in payload_dict:
                # Export comprehensive metrics for production analysis
                comprehensive_data = self.stats.export_comprehensive_metrics_for_steering()
                self.api_export_timeseries({
                    "comprehensive_metrics": ("Observer Comprehensive Metrics",  "MW", "MW", COMMON.HOUR,
                                           {self.timestamp: comprehensive_data})
                })
                self.log.info(f"[{self.strategy_id}] Exported {comprehensive_data['total_observations']} comprehensive metrics")
            elif "trade_decisions" in payload_dict:
                trade_decisions = self.stats.get_recent_trade_decisions(payload_dict.get("count", 10))
                self.api_export_timeseries({
                    "trade_decisions": ("Observer Trade Decisions",  "MW", "MW", COMMON.HOUR,
                                      {self.timestamp: {'decisions': trade_decisions}})
                })
            elif "conditions_summary" in payload_dict:
                # Export trading conditions summary
                conditions_summary = self.stats.get_trading_conditions_summary()
                self.api_export_timeseries({
                    "conditions_summary": ("Observer Conditions Summary", "MW", "MW", COMMON.HOUR,
                                         {self.timestamp: conditions_summary})
                })
            else:
                self.log.info(f"[{self.strategy_id}] Unknown steering call code: {payload}")
        except Exception as e:
            self.log.error(f'ERROR steering, exception: {e}, line number: {e.__traceback__.tb_lineno}')

