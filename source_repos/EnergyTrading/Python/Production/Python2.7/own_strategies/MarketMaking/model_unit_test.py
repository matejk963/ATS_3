import unittest
import os
from mm_strategy.model_stats import ModelStats


class SOTest(unittest.TestCase):
    file_path = '//192.168.10.91/data/Data/data_model.txt'
    def test_model_mstd(self):
        # Load data
        with open(self.file_path, 'r') as file:
            data_list = [float(line.strip()) for line in file]
        model_type = 'MSTD_x'
        params_list = [5.2, .025]
        model_cls = ModelStats(model_type, params_list, 'model_test')
        # Loop over data
        val_list = []
        std_list = []
        for x in data_list:
            val_list.append(model_cls.update_strategy_prices(x - .1, x + .1, x))
            std_list.append(model_cls.spread_std)

        file_path_out = '//192.168.10.91/data/Data/data_model_mstd_x.txt'
        with open(file_path_out, 'w') as file:
            for val, std in zip(val_list, std_list):
                file.write(str(val) + ',' + str(std) + "\n")

    def test_model_mstd_t(self):
        # Load data
        with open(self.file_path, 'r') as file:
            data_list = [float(line.strip()) for line in file]
        model_type = 'MSTD_t'
        params_list = [5.2, .025]
        model_cls = ModelStats(model_type, params_list, 'model_test')
        # Loop over data
        val_list = []
        std_list = []
        for x in data_list:
            val_list.append(model_cls.update_strategy_prices(x - .1, x + .1, x))
            std_list.append(model_cls.spread_std)

        file_path_out = '//192.168.10.91/data/Data/data_model_mstd_t.txt'
        with open(file_path_out, 'w') as file:
            for val, std in zip(val_list, std_list):
                file.write(str(val) + ',' + str(std) + "\n")

    def test_model_ema(self):
        # Load data
        with open(self.file_path, 'r') as file:
            data_list = [float(line.strip()) for line in file]
        model_type = 'EMA'
        params_list = [5.2, .025]
        model_cls = ModelStats(model_type, params_list, 'model_test')
        # Loop over data
        val_list = []
        for x in data_list:
            val_list.append(model_cls.update_strategy_prices(x - .1, x + .1, x))

        file_path_out = '//192.168.10.91/data/Data/data_model_ema.txt'
        with open(file_path_out, 'w') as file:
            for val in val_list:
                file.write(str(val) + "\n")

if __name__ == '__main__':
    unittest.main()
