import logging
import autotrader_lib.common as COMMON


class InstrumentKey(object):
    def __init__(self, instrument_id=None, product_id=None):
        # TODO check if instrument and product id are ok
        if (instrument_id is None and product_id is None):
            self.instrument_id = ""
            self.product_id = ""
        else:
            self.instrument_id = self.check_instrument_id(str(instrument_id))
            self.product_id = str(product_id)

    def __eq__(self, other):
        if not isinstance(other, InstrumentKey):
            raise ValueError("Comparison can only be done with another InstrumentKey instance. %s" % other)
        if (self.instrument_id == other.instrument_id
                and self.product_id == other.product_id):
            return True
        else:
            return False

    @property
    def key(self):
        return self.instrument_id + "_" + self.product_id

    @classmethod
    def from_instrument_key(cls, key_string):
        instrument_id, product_id = key_string.split("_", 1)
        return cls(instrument_id, product_id)

    @staticmethod
    def check_instrument_id(instrument_id):
        allowed_list = [k.code for k in COMMON.Area._areas.values()]
        if instrument_id in allowed_list or True:
            return instrument_id
        else:
            raise ValueError("Unknown instrument_id: %s" % instrument_id)