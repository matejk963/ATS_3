from __future__ import absolute_import
import autotrader_synthetic.local_view as LV
import autotrader_synthetic.commingled_view as CV


COMMINGLED_VIEW_TYPE = "c"
LOCAL_VIEW_TYPE = "i"


class ViewNotConfigured(KeyError):
    """
    Raised when the get_configured_view() function is called for a non configured view
    """
    pass


class ViewFactory(object):
    """
    A ViewFactory is a class that provides new instances of LocalView or CommingledView
    """
    def __init__(self, products, strategy_id):
        """
        :param products: The Products object for which we would like to create the view
        :type products: autotrader_core.exchange_trading.Products
        :param strategy_id: The id of the strategy within which view is created
        :type strategy_id: str
        """
        self._products = products
        self.strategy_id = strategy_id
        self._view_names = dict()
        self._view = dict()

    def configure_view(self, view_name, instrument_ids):
        """
        Register a definition for a commingled view.

        By registering a list of instrument_ids under a name, this factory gains the ability to create commingled
        views for the given instrument_ids.
        :param view_name: The name of view
        :type view_name: str
        :param instrument_ids: The list of instrument_ids for which the view should be created
        :type instrument_ids: list[str]
        """
        self._view_names[view_name] = instrument_ids

    def get_configured_view(self, key, product_id):
        """
        The function creates an instance for the CommingledView (predefined list of instrument_ids) if there is not
        yet a valid instance for this view. The function returns the existing instance if there is already
        a valid instance for this view.
        :param key: single instrument_id or predefined commingled view
        :type key: str
        :param product_id: The id of the product within which this view is created
        :type product_id: str
        :return: CommingledView
        :rtype: autotrader_synthetic.commingled_view.CommingledView
        """
        view_key = (COMMINGLED_VIEW_TYPE, key, product_id)
        product = self._products.get_by_id(product_id)
        if view_key not in self._view:
            # key as a predefined commingled view
            if key in self._view_names:
                self._view[view_key] = CV.CommingledView(product, self._view_names[key], self.strategy_id)
            else:
                raise ViewNotConfigured("The view {} was not configured, please configure the view with the "
                                        "strategy template or call configure_view() function".format(key))
        return self._view[view_key]

    def get_view_for_instrument(self, instrument_id, product_id):
        """
        Function to get the instrument for the created view
        The function creates an instance for the LocalView if there is not yet a valid instance for this view and
        returns the existing instance if there is already a valid instance for this view.
        :param instrument_id: single instrument_id or predefined commingled view
        :type instrument_id: str
        :param product_id: The id of the product within which this view is created
        :type product_id: str
        :return: LocalView
        :rtype: autotrader_synthetic.local_view.LocalView
        """
        view_key = (LOCAL_VIEW_TYPE, instrument_id, product_id)
        if view_key not in self._view:
            product = self._products.get_by_id(product_id)
            self._view[view_key] = LV.LocalView(product, instrument_id, self.strategy_id)
        return self._view[view_key]
