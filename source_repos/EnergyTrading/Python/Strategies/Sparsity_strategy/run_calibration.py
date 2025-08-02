# -*- coding: utf-8 -*-
"""
Created on Thu Mar 20 13:05:51 2025

@author: algouser
"""

import itertools
import subprocess
import sys
import os
from datetime import datetime

from Utilities.Storage import get_curr_storage_path

# Configuration of parameter combinations
PARAM_COMBINATIONS = {
    '--batch_size': [2**7, 2**8, 2**9],  # 128, 256, 512
    '--cache_r_path': ['data_factory/backtest_obt_dem1_from2024July.parquet'],
    '--top_k': [250, 500, 750],
    '--mode': ['gpu'],
    '--cpu_cores': [2, 4, 8]
}



def generate_commands(combinations):
    """Yield command lists for each parameter combination"""
    keys = combinations.keys()
    for values in itertools.product(*combinations.values()):
        cmd = [sys.executable, "-u", r"C:\Users\algouser\Documents\GitHub\EnergyTrading\Python\Strategies\Sparsity_strategy\rolling_calibration.py"]  # -u for unbuffered output
        for k, v in zip(keys, values):
            cmd += [k, str(v)]
        yield cmd

if __name__ == '__main__':
    _STORAGE = get_curr_storage_path()
    dir_name = datetime.now().strftime("%Y-%m-%d_%H_%M")
    os.mkdir(_STORAGE + 'calib_results/' + dir_name)
    PARAM_COMBINATIONS = {
        '--instrument': ['dem3'],
        '--top_k': [200, 500, 1000, 2000],
        '--fees': [0.05, 0.1, 0.12, 0.15, 0.2],
        '--train_days': [5, 10, 15, 20, 25, 30],
        '--cluster_size': [5, 10],
        '--directory_path': [dir_name + '/']
    }
    # FOR TESTING
    # PARAM_COMBINATIONS = {
    #     '--instrument': ['dem1'],
    #     '--top_k': [200],
    #     '--fees': [0.05],
    #     '--train_days': [5],
    #     '--cluster_size': [5],
    #     '--directory_path': [dir_name + '/']
    # }
    for i, cmd in enumerate(generate_commands(PARAM_COMBINATIONS), 1):
        print(f"\n{'#' * 40}")
        print(f"RUNNING COMBINATION {i}:")
        print(' '.join(cmd))
        
        # Run with live output display
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        # Stream output in real time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        
        print(f"\nCompleted combination {i}")
        print(f"{'#' * 40}\n")
