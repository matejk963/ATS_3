from __future__ import absolute_import
import os.path

# The parent directory, into which the backtesting package is installed/ copied
ROOT_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


DEFAULT_TRADE_EXPORT_COLUMNS = ["exchange", "product_id", "delivery_start",
                                "delivery_end", "trade_id", "quantity", "price", "buy_delivery_area",
                                "sell_delivery_area", "trading_portfolio",
                                "execution_time", "product_type", "aggressor_broker_id",
                                "initiator_broker_id", "aggressor", "object_type"]
