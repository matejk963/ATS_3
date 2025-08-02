# -*- coding: utf-8 -*-
"""
Created on Sun Sep 24 15:12:35 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from keras.models import Model
from keras.layers import Input, Conv1D, Flatten, Dense, Concatenate
from keras.callbacks import EarlyStopping
from sklearn.model_selection import train_test_split

import numpy as np
from tensorflow import keras
from keras.layers import Input, Conv1D, Flatten, Dense, Dropout, Concatenate
from keras.callbacks import EarlyStopping
from keras.metrics import Recall
from kerastuner import HyperModel, RandomSearch
from kerastuner import Objective
from tensorflow.keras import backend as K
from tensorflow.keras.layers import Reshape



import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.layers import Input, Conv1D, Flatten, Concatenate, Dense, Reshape, Dropout
from tensorflow.keras.models import Model
from tensorflow.keras.callbacks import EarlyStopping

class MultiInputNN:
    def __init__(self, input_shapes):
        self.input_shapes = input_shapes
        self.model = self._build_model()

    def _build_model(self):
        inputs = []
        processed_branches = []

        for shape in self.input_shapes:
            input_matrix = Input(shape=shape)
            inputs.append(input_matrix)
            
            reshaped_matrix = Reshape((shape[0], 1))(input_matrix)
            x = Conv1D(filters=64, kernel_size=5,padding='same', activation='relu')(reshaped_matrix)
            
            x = Conv1D(filters=32, kernel_size=3,padding='same', activation='relu')(x)
            x = Conv1D(filters=32, kernel_size=3,padding='same', activation='relu')(x)
            x = Conv1D(filters=16, kernel_size=3,padding='same', activation='relu')(x)
            
            
            
            x = Conv1D(filters=4, kernel_size=3, activation='relu')(x)
            

            x = Flatten()(x)
            processed_branches.append(x)

        merged = Concatenate()(processed_branches)

        merged = Dense(128, activation='relu')(merged)
        merged = Dropout(0.5)(merged)
        merged = Dense(64, activation='relu')(merged)
        merged = Dense(64, activation='relu')(merged)
        merged = Dense(64, activation='relu')(merged)
        merged = Dense(64, activation='relu')(merged)
        
        output = Dense(1, activation='sigmoid')(merged)

        model = Model(inputs=inputs, outputs=output)
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

        return model

    def train(self, input_data, y_train, epochs=100, validation_data=None):
        early_stopping = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)

        if validation_data:
            X_val, y_val = validation_data[:-1], validation_data[-1]
            self.model.fit(input_data, y_train, epochs=epochs, validation_data=(*X_val, y_val), callbacks=[early_stopping])
        else:
            self.model.fit(input_data, y_train, epochs=epochs, callbacks=[early_stopping])

    def evaluate(self, input_data, y_test):
        return self.model.evaluate(input_data, y_test)

    def predict(self, input_data):
        return self.model.predict(input_data)


    
y_data_raw = pd.read_csv(r's:\Algo\Database\Backups\data_df_nn.csv', index_col=[0])
y_data_raw['date'] = pd.to_datetime(y_data_raw.index)
y_data_raw = y_data_raw.set_index('date')


x_data = np.loadtxt(r's:\Algo\Database\Backups\rld_wa_nn.csv',
                    delimiter=',')

ttf_ret = pd.read_csv(r's:\Algo\Database\Backups\ttf_ret_nn.csv',index_col=[0])
ttf_ret['date'] = pd.to_datetime(ttf_ret.index)
ttf_ret = ttf_ret.set_index('date')

x_data_aux = pd.DataFrame(x_data,index=y_data_raw.index)
x_data_aux['date'] = pd.to_datetime(x_data_aux.index)
x_data_aux = x_data_aux.set_index('date')
x_data = np.array(x_data_aux.loc[ttf_ret.index].copy())

y_data_raw = y_data_raw.loc[ttf_ret.index]
y_data = y_data_raw['long']


X1_train, X1_test, y_train_1, y_test_1 = train_test_split(x_data,
                                                    y_data,
                                                    test_size=0.2,
                                                    shuffle=False)
X2_train, X2_test, _, _ = train_test_split(ttf_ret,
                                           y_data,
                                           test_size=0.2,
                                           shuffle=False)


y_train = y_train_1.copy()
y_test = y_test_1.copy()



model = MultiInputNN(input_shapes=[X1_train.shape[1:], X2_train.shape[1:]])
model.train([X1_train, X2_train], y_train, epochs=30, validation_data=([X1_test, X2_test], y_test))
accuracy = model.evaluate([X1_test, X2_test], y_test)
y_pred = model.predict([X1_test,X2_test])


y_pred_b = (y_pred>0.5).astype(int)

pos = pd.DataFrame(y_pred,
                   index=y_test_1.index,
                   columns=['prediction'])

pos = pd.concat([pos, y_data_raw], axis=1, join='inner')

thres = 0.6
pos['pnl'] = np.where(pos['prediction']>0.5,
                      pos['de'] - pos['wa_vwap'],
                      np.where(pos['prediction']<0.5,
                               pos['wa_vwap'] - pos['de'],0))

pos['pnl'].cumsum().plot()
plt.show()
plt.plot(pos['prediction'])
plt.show()


# Example usage:
# nn = VariableInputNN(input_shape=(168, 1), num_matrices=1)
# nn.train(y_train, epochs=50, validation_data=([X_val_A, X_val_B, X_val_C], y_val), X_train_A, X_train_B, X_train_C)
# accuracy = nn.evaluate(y_test, X_test_A, X_test_B, X_test_C)
# predictions = nn.predict(X_new_A, X_new_B, X_new_C)

print(X1_train.shape)  # Expected (number_of_samples, 168)
print(X2_train.shape)  # Expected (number_of_samples, 7)
print(y_train.shape)   # Expected (number_of_samples,)

# nn_o.train(X1_train, y_train=y_train, epochs=100, validation_data=(X1_test, y_test), optimize=True)
# 