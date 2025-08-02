import math
import numpy as np
import pandas as pd
from Math.accumfeatures import MSTD, DerivativeEMA
from Strategies.Market_making.model_class import model_class as Model

class Model_mstd(Model):
    def __init__(self, tau_ema, n):
        self.mstd = None
        self.tau_ema = tau_ema
        self.n = n
    
    def deep_copy(self):
        try:
            cls = Model_mstd(self.window,
                            self.tau_ema)
            cls.mstd = MSTD(cls.tau_ema, p=2, n=self.n, value0=self.mstd.value)
            cls.data_stack = self.data_stack
            return cls
        except:
            return None
        
    def _init(self, data):
        self.mstd = MSTD(self.tau_ema, p=2, n=self.n, value0=data)

    def predict(self, x):
        if self.mstd == None:
            self._init(x)
        else:
            self.mstd.push(x)

        return {
            'ema': self.mstd.mean.value,
            'sigma': self.mstd.value
            }
        
    def reset(self):
        self.mstd = None

    # def get_trend(self): 
    #     if self.len < self.window:
    #         return None
        
    #     close_data = [x['Close'] for x in self.data_stack]
    #     y = np.array(close_data)
    #     nan_pos = np.isnan(y)
    #     y = y[~nan_pos]
    #     x = np.arange(1,len(y)+1)
    #     lin_reg = np.polyfit(x, y, 1)
    #     m, b = lin_reg[0], lin_reg[1]
    #     sigma = pd.Series([x['sigma'] for x in self.data_stack]).mean()
    #     alfa = ((x[-1]*m+b) - (x[0]*m+b))/math.sqrt(sigma*self.window)
    #     return alfa

class Model_trend(Model):
    def __init__(self, tau_ema, n):
        self.ema = None
        self.tau_ema = tau_ema
        self.n = n
    
    def _init(self, x):
        self.ema = DerivativeEMA(self.tau_ema, self.n, value0=x)

    def predict(self, x):
        if self.ema == None:
            self._init(x)
        else:
            self.ema.push(x)

        return {
            'trend': self.ema.value 
            }
    
    def reset(self):
        self.mstd = None