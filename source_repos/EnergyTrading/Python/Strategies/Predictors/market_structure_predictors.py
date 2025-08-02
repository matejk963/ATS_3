import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time
from Database.TPData import TPData, TPDataDa
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Strategies.Sparse_momentum.ob_attributes import OB_attributes

class MarketStructurePredictors:
    def __init__(self, params_dict):
        self._params_dict = params_dict
        
        pass

    @property
    def start_date(self):
        return self._start_date
    
    @property
    def end_date(self):
        return self._end_date
    
    # def load_ob(m, t, dt, p_d, bT, eT):
    #     ob_class = OrderBookSnaps(verbose=True)
    #     file_path = l_path + t.split('_')[0] + '/'
    #     file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt.strftime('%y%m%d') + '.p'
    #     print('%s Loading OrderBook %d...' % (dt.strftime('%y-%m-%d'), 0))
    #     print(file_path + file_name)
    #     time_load = ob_class.import_data(file_path + file_name)
    #     print('OrderBook %d created in %d sec' % (0, time_load))
    #     # ob_class.LoB_truncate(thres_vol=1)
    #     return ob_class.LoB_select(bT, eT, freq=None)

    # def variables_from_instrument(instrument: str):
    #     result = {
    #         'mkt': None,
    #         'tenor': None,
    #         'tn': None
    #     }
    #     for x in ['de', 'fr', 'ttf']:
    #         if x in instrument:
    #             result['mkt'] = x
    #     result['tenor'] = instrument[-2]
    #     result['tn'] = int(instrument[-1])
    #     return result
