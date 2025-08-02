# -*- coding: utf-8 -*-
"""
Created on Tue Mar  4 16:24:42 2025

@author: scasny
"""

import pandas as pd
from Database.DB_reader import Database


instrument = 'DEBM'
"""Get long/short percentage breakdown for all categories"""
db = Database()
df = pd.read_sql(
    sql=f'SELECT * FROM "cot"."agg_view" WHERE instrument = \'{instrument}\'',
    con=db.connection_string,
    coerce_float=False
)

df_agg = df.groupby(['instrument', 'date']).sum().loc[instrument]

# Long positions
long_cols = [c for c in df_agg.columns if '_long' in c]
long_df = df_agg[long_cols]
long_pct = long_df.div(long_df.sum(axis=1), axis=0)

# Short positions
short_cols = [c for c in df_agg.columns if '_short' in c]
short_df = df_agg[short_cols]
short_pct = df_agg[short_cols].div(df_agg[short_cols].sum(axis=1), axis=0)

spread = df_agg.eval('(commer_long - commer_short) / market_total')
