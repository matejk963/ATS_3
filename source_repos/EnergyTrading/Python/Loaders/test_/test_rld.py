from Loaders.RLD_fetch import RLDDatabaseData
from datetime import datetime
from matplotlib import pyplot as plt

# def plotResExample():
#     rldd = RLDDatabaseData()
#     df1 = rldd.getResAtMoment(_from=datetime(2022,1,1), _to=datetime(2022,2,5), hour=8, minute=40)
#     df2 = rldd.getResAtMoment(_from=datetime(2022,1,1), _to=datetime(2022,2,5), hour=10, minute=45)
#     df3 = rldd.createRLDVector(_from=datetime(2022,1,1), _to=datetime(2022,2,5), hours=12, delta=7)

#     plt.plot(df1['forecast_date'], df1['mean'],label='forecast 8hour')
#     plt.plot(df2['forecast_date'], df2['mean'],label='forecast 10hour')
#     plt.plot(df3['forecast_date'], df3['mean'],label='dayahead + forecast')

#     plt.legend()

#     plt.show()

# def injectNormals():
#     rldd = RLDDatabaseData()
#     rldd.injectHistoryNormalData(_from=2018, _to=2025)

# def getNormals(_from, _to):
#     """
#     df = getNormals(datetime(2025,12,30),datetime(2025,12,31))
#     """
#     rldd = RLDDatabaseData()
#     df = rldd.getResNormals(_from, _to)
#     return df

# rldd = RLDDatabaseData()
# df = rldd.getResDayAhead(_from=datetime(2022,1,1), _to=datetime(2022,2,5))

cls = RLDDatabaseData(r"Z:\EnergyTrading\configDB.json")
df = cls.history_live_merge(from_=datetime(2024,1,1), to_=datetime(2024,1,16))