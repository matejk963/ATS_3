from __future__ import absolute_import
import autotrader_core.strategy_template as TEMPLATE


class StrategyTemplateValidationError(Exception):
    pass


class StrategyConfiguration(object):

    def __init__(self, strategy_id, instrument_ids, strategies_folder, package_name, caption,
                 exchange="TRAYPORT", **kwargs):
        self._internal_strategy_config = dict(internal_number=strategy_id,
                                              caption=caption,
                                              exchange=exchange,
                                              instrument_ids=instrument_ids)
        self._internal_strategy_config.update(kwargs)
        self._package_name = package_name

        self.strategy_template_class = TEMPLATE.get_template_from_package(
            TEMPLATE.package_loader(strategies_folder, package_name))
        self.filled_template = None
        self._validate_and_create_data()

    @property
    def strategy_id(self):
        return self._internal_strategy_config["internal_number"]

    def _validate_and_create_data(self):
        self.filled_template = self.strategy_template_class(**self._internal_strategy_config)

    def update(self, changed_data):
        self.filled_template.update_parameters(**changed_data)

    def to_mongo_dict(self):
        return self.filled_template.to_mongo_object(self._package_name, "Backtesting User")
