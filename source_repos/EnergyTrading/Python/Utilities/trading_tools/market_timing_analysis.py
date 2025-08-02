"""
Market Timing Analysis - Standalone Python Module

This module contains all the necessary functions to perform market timing analysis
combining energy futures data with COT (Commitment of Traders) positions.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import refinitiv.data as rd
from Database.DB_reader import Database


class MarketTimingAnalyzer:
    """
    A comprehensive market timing analyzer for energy trading using HPI and COT data.
    """
    
    def __init__(self):
        """Initialize the analyzer with database connection."""
        self.db = Database()
    
    def get_net_pct_dfs(self, instruments):
        """
        For each instrument in `instruments`, fetch COT entries from the database,
        compute net volume percent per (actor, risk_reducing) bucket, and return a
        dict of DataFrames indexed by date with columns actor_RR or actor_NRR.
        """
        df_dict = {}
        
        for instr in instruments:
            # 1. Query data
            query = f"""
            SELECT *
            FROM "cot"."cot_entries"
            WHERE instrument = '{instr}';
            """
            raw = pd.read_sql(query, self.db.connection_string)
            raw['date'] = pd.to_datetime(raw['date'])
            
            # 2. Compute long and short vol_pct
            long = (
                raw[raw['direction']=='long']
                .reset_index(drop=True)
                .assign(vol_pct=lambda d: d.groupby(
                    ['date','instrument','direction']
                )['volume'].transform(lambda x: x / x.sum() * 100))
                .set_index('date')
            )
            short = (
                raw[raw['direction']=='short']
                .reset_index(drop=True)
                .assign(vol_pct=lambda d: d.groupby(
                    ['date','instrument','direction']
                )['volume'].transform(lambda x: x / x.sum() * 100))
                .set_index('date')
            )
            
            # 3. Merge and net
            net = pd.merge(
                long[['instrument','actor','risk_reducing','vol_pct']].reset_index(),
                short[['instrument','actor','risk_reducing','vol_pct']].reset_index(),
                on=['date','instrument','actor','risk_reducing'],
                how='outer',
                suffixes=('_long','_short')
            )
            net[['vol_pct_long','vol_pct_short']] = net[['vol_pct_long','vol_pct_short']].fillna(0)
            net['vol_pct_net'] = net['vol_pct_long'] - net['vol_pct_short']
            
            # 4. Pivot into date-indexed DF
            pivot = net.pivot(
                index='date',
                columns=['actor','risk_reducing'],
                values='vol_pct_net'
            )
            # flatten columns
            pivot.columns = [
                f"{actor}_{'RR' if rr else 'NRR'}" 
                for actor, rr in pivot.columns.tolist()
            ]
            pivot = pivot.sort_index(axis=1)
            
            df_dict[instr] = pivot
        
        return df_dict
    
    def hpi_weighted(self, df, window):
        """
        Calculate hedging pressure index based on price changes, open interest, and volume.
        """
        doi = df['oi'].diff().abs()
        ratio = (doi / df['vol']).clip(0, 1).fillna(0)
        sig = np.sign(df['price_diff']).fillna(0)
        return (sig * ratio).rolling(window).mean()
    
    def fetch_strip(self, codes, hpi_window=20, ema_span=5):
        """
        Fetch and process futures data for a single strip (power, gas, eua).
        """
        rd.open_session()
        try:
            p = rd.get_history([codes['power']], count=500)[['SETTLE','OPINT_1','ACVOL_UNS']]
            g = rd.get_history([codes['gas']], count=500)[['SETTLE']]
            e = rd.get_history([codes['eua']], count=500)[['SETTLE']]
        finally:
            rd.close_session()
        
        p.columns = ['power','oi','vol']
        g.columns = ['gas']
        e.columns = ['eua']
        
        raw = pd.concat([p, g, e], axis=1).dropna()
        raw['price'] = raw['power'] - 2*raw['gas'] - 0.4*raw['eua']
        # Alternative: raw['price'] = raw['power']
        
        df = raw[['price','oi','vol', 'power']].copy()
        df['price_diff'] = df['price'].pct_change()
        df['hpi_raw'] = self.hpi_weighted(df, hpi_window)
        df['hpi_ema'] = df['hpi_raw'].ewm(span=ema_span, adjust=False).mean()
        
        return df.dropna()
    
    def make_spread(self, df1, df2):
        """
        Create spread between two dataframes.
        """
        idx = df1.index.intersection(df2.index)
        spr = pd.DataFrame(index=idx)
        # Power spread on primary axis
        spr['power_spread'] = df1['power'].reindex(idx) - df2['power'].reindex(idx)
        # Price-HPI difference
        spr['hpi_ema'] = df1['hpi_ema'].reindex(idx) - df2['hpi_ema'].reindex(idx)
        return spr.dropna()
    
    def fetch_net_position_sql(self, power_code):
        """
        Fetch net position = long - short for the given power_code.
        """
        dfs = self.get_net_pct_dfs([power_code])
        pos = dfs[power_code].sort_index()
        # Sum all commercial positions (excluding non-risk reducing)
        pos['net_pos'] = pos[[a for a in pos.columns if 'Commer' in a]].sum(axis=1)
        return pos['net_pos']
    
    def plot_power_spread(self, spr, ref_hpi, net_pos, title):
        """
        Plot power spread with HPI and net position overlays.
        """
        fig, ax1 = plt.subplots(figsize=(12, 5))
        ax1.plot(spr.index, spr['power_spread'], color='tab:blue', label='Power Spread')
        ax1.set_ylabel('Power Spread', color='tab:blue')
        ax1.grid(ls='--', lw=0.4, alpha=0.6)

        ax2 = ax1.twinx()
        ax2.plot(spr.index, spr['hpi_ema'], '--', color='tab:green', label='Own HPI')
        ax2.set_ylabel('Own HPI', color='tab:green')

        ax4 = ax1.twinx()
        ax4.spines['right'].set_position(('outward', 120))
        net_pos_resampled = net_pos.resample('D').ffill().reindex(spr.index).bfill()
        ax4.plot(spr.index, net_pos_resampled, '-', color='tab:red', label='Net Pos')
        ax4.set_ylabel('Net Pos', color='tab:red')

        # Combined legend
        lines, labels = [], []
        for ax in (ax1, ax2, ax4):
            ln, lb = ax.get_legend_handles_labels()
            lines += ln
            labels += lb
        ax1.legend(lines, labels, loc='upper left')

        plt.title(title)
        plt.tight_layout()
        plt.show()
    
    def plot_leg_with_net(self, df, power_code, title):
        """
        Plot individual leg with its net position.
        """
        # Fetch leg net position
        net_pos = self.fetch_net_position_sql(power_code).reindex(df.index).ffill()
        
        fig, ax1 = plt.subplots(figsize=(12, 4))
        ax1.plot(df.index, df['power'], color='tab:blue', label='Price')
        ax1.set_ylabel('Price', color='tab:blue')
        ax1.grid(ls='--', lw=0.4, alpha=0.6)

        ax2 = ax1.twinx()
        ax2.plot(df.index, df['hpi_ema'], '--', color='tab:green', label='HPI (EMA)')
        ax2.set_ylabel('HPI (EMA)', color='tab:green')

        ax3 = ax1.twinx()
        ax3.spines['right'].set_position(('outward', 60))
        ax3.plot(df.index, net_pos, ':', color='tab:red', label='Net Pos')
        ax3.set_ylabel('Net Pos', color='tab:red')

        # Combined legend
        lines, labels = [], []
        for ax in (ax1, ax2, ax3):
            ln, lb = ax.get_legend_handles_labels()
            lines += ln
            labels += lb
        ax1.legend(lines, labels, loc='upper left')

        plt.title(title)
        plt.tight_layout()
        plt.show()
    
    def run_full_analysis(self):
        """
        Run the complete market timing analysis with predefined configurations.
        """
        # ───────── CONFIGURATION ─────────
        LEG1A = dict(power='DEBYF6', gas='TFMBYZ6', eua='CFI2Z6')
        LEG1B = dict(power='FDBYF6', gas='TFMBYZ6', eua='CFI2Z6')
        LEG2A = dict(power='FDBYF6', gas='TFMBYZ6', eua='CFI2Z6')
        LEG2B = dict(power='F9BYF6', gas='TFMBYZ6', eua='CFI2Z6')
        REF = dict(power='DEBYF6', gas='TFMBYZ6', eua='CFI2Z6')

        HPI_WINDOW = 20
        EMA_SPAN = 5        # ───────── MAIN ANALYSIS ─────────
        print("Fetching market data...")
        A1 = self.fetch_strip(LEG1A, HPI_WINDOW, EMA_SPAN)
        A2 = self.fetch_strip(LEG1B, HPI_WINDOW, EMA_SPAN)
        B1 = self.fetch_strip(LEG2A, HPI_WINDOW, EMA_SPAN)
        B2 = self.fetch_strip(LEG2B, HPI_WINDOW, EMA_SPAN)
        R = self.fetch_strip(REF, HPI_WINDOW, EMA_SPAN)

        print("Creating spreads...")
        spr1 = self.make_spread(A1, A2)
        spr2 = self.make_spread(B1, B2)

        print("Fetching COT positions...")
        # Automatically convert power codes to COT codes
        cot1a = self.power_to_cot_code(LEG1A['power'])  # DEBYF6 → DEBM
        cot1b = self.power_to_cot_code(LEG1B['power'])  # FDBYF6 → FDBM
        cot2a = self.power_to_cot_code(LEG2A['power'])  # FDBYF6 → FDBM  
        cot2b = self.power_to_cot_code(LEG2B['power'])  # F9BYF6 → F9BM
        
        net1 = self.fetch_net_position_sql(cot1a) - self.fetch_net_position_sql(cot1b)
        net2 = self.fetch_net_position_sql(cot2a) - self.fetch_net_position_sql(cot2b)

        print("Generating plots...")
        
        # Plot spreads with net positions
        self.plot_power_spread(spr1, R['hpi_ema'], net1, 'Spread 1 of Power & HPI & Net Pos')
        self.plot_power_spread(spr2, R['hpi_ema'], net2, 'Spread 2 of Power & HPI & Net Pos')

        # Plot individual legs with their net positions
        self.plot_leg_with_net(A1, cot1a, f'Leg 1A ({LEG1A["power"]}): Price, HPI & Net Pos')
        self.plot_leg_with_net(A2, cot1b, f'Leg 1B ({LEG1B["power"]}): Price, HPI & Net Pos')
        self.plot_leg_with_net(B1, cot2a, f'Leg 2A ({LEG2A["power"]}): Price, HPI & Net Pos')
        self.plot_leg_with_net(B2, cot2b, f'Leg 2B ({LEG2B["power"]}): Price, HPI & Net Pos')
        
        print("Analysis complete!")
        
        return {
            'spreads': {'spr1': spr1, 'spr2': spr2},
            'legs': {'A1': A1, 'A2': A2, 'B1': B1, 'B2': B2, 'REF': R},
            'net_positions': {'net1': net1, 'net2': net2}
        }
    
    def power_to_cot_code(self, power_code):
        """
        Convert power futures code to COT instrument code.
        Takes first two letters (country code) and adds 'BM'.
        
        Examples:
        - DEBYF6 → DEBM
        - FDBYF6 → FDBM  
        - F9BYF6 → F9BM
        """
        if len(power_code) >= 2:
            return power_code[:2] + 'BM'
        return power_code  # fallback if code is too short


def main():
    """
    Main function to run the market timing analysis.
    """
    analyzer = MarketTimingAnalyzer()
    results = analyzer.run_full_analysis()
    return results


if __name__ == "__main__":
    # Run the analysis
    results = main()
