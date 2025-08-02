from Loaders.RLD_fetch import RLDDatabaseData, RLDFetch
from Enums import FTP as FTP_ENUM
from datetime import datetime
from time import sleep

r = RLDFetch()
rldd = RLDDatabaseData(path_name=r"Z:\EnergyTrading\configDB.json")
today = datetime.today().date()

ens_file = open('ens_updates.csv', 'a')
op_file = open('op_updates.csv', 'a')
last_ens = datetime(2022,1,1,0,0)
last_op = datetime(2022,1,1,0,0)

while(True):
    ens_file = open('ens_updates.csv', 'a')
    op_file = open('op_updates.csv', 'a')
    ens_update = rldd._getHistoryUpdateDate(
        r, r._path + FTP_ENUM['wind']['live_ens'].format_map({'date': today}), time=True)
    op_update = rldd._getHistoryUpdateDate(
        r, r._path + FTP_ENUM['wind']['live_op'].format_map({'date': today}), time=True)
    if last_ens != ens_update:
        ens_file.write(f"{ens_update};")
    
    if last_op != op_update:
        op_file.write(f"{op_update};")
    print("Current ens", ens_update, "op ", op_update)
    ens_file.close()
    op_file.close()
    sleep(1)
    