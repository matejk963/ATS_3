import autotrader_core.persistence as PERSIST
import six
if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG


log = FLOG.getLogger("exchange-configuration")


class ExchangeConfiguration(object):
    default_config = {
        "max_exposed_orders_per_side": None
    }

    @classmethod
    def from_db(cls, exchange_id):
        toplevel_config = cls.default_config.copy()
        mongo_cfg = PERSIST.MongoDBConnector().load_db_exchange_configuration(exchange_id)
        if mongo_cfg is None:
            mongo_cfg = {}

        toplevel_config.update(mongo_cfg)
        return cls(toplevel_config)

    def load_configuration_max_exposed_orders_per_side(self, toplevel_config):
        """
        Config is set by OPS.
        To ensure things are set up correctly and our tests won't fail, we have extra handling here

        :param toplevel_config: mongo exchange configuration
        :type toplevel_config: dict
        """
        config_value = toplevel_config["max_exposed_orders_per_side"]
        try:
            value = int(config_value)
            if value <= 0:
                raise ValueError
            self.max_exposed_orders_per_side = value
        except (ValueError, TypeError):
            # max_exposed_orders_per_side can still be None in tests!
            log.warning("Could not set new value of 'max_exposed_orders_per_side':"
                        " '{}' - please use a positive integer instead!".format(config_value))

    def __init__(self, toplevel_config):
        """
        :param toplevel_config: mongo exchange configuration
        :type toplevel_config: dict
        """
        self.max_exposed_orders_per_side = None
        self.load_configuration_max_exposed_orders_per_side(toplevel_config)
