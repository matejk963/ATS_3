# -*- coding: utf-8 -*-
"""
Created on Wed Mar 12 15:13:06 2025

@author: david
"""

import pandas as pd
from datetime import datetime
import os

def spracuj_excel(vstupny_subor, vystupny_subor):
    """
    Spracuje Excel súbor, vypočíta medián, priemer a percentily pre každý inštrument a uloží výsledky.
    """

    # Načítanie dát z Excel súboru
    df = pd.read_excel(vstupny_subor)

    # Konverzia stĺpca 'datetime' na datetime objekt
    df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce', format='mixed') # Upravený riadok

    # Mapovanie slovenských skratiek mesiacov na anglické
    slovenske_mesiace = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'Máj': 5, 'Jún': 6,
        'Júl': 7, 'Aug': 8, 'Sep': 9, 'Okt': 10, 'Nov': 11, 'Dec': 12
    }

    # Funkcia na výpočet rozdielu mesiacov
    def rozdiel_mesiacov(datum, instrument):
        mesiac, rok = instrument.split(' ')
        mesiac_cislo = slovenske_mesiace[mesiac]
        instrument_datum = datetime(int(rok), mesiac_cislo, 1)
        return (instrument_datum.year - datum.year) * 12 + instrument_datum.month - datum.month

    vysledky = []

    # Iterácia cez unikátne inštrumenty
    for instrument in df['Instrument'].unique():
        # Iterácia cez unikátne dátumy
        for datum in df['datetime'].unique():
            print(f"Spracovávam inštrument: {instrument}, dátum: {datum}")
            # Výpočet rozdielu mesiacov
            rozdiel = rozdiel_mesiacov(datum, instrument)
            print(f"Rozdiel mesiacov: {rozdiel}")

            # Kontrola, či je rozdiel v rozmedzí 1 až 6 mesiacov a či je dátum pred inštrumentom
            if 0 < rozdiel <= 6:
                # Filtrovanie dát pre daný inštrument a rozdiel mesiacov
                filtered_df = df[(df['Instrument'] == instrument) & (df['datetime'].dt.to_period('M') == datum.to_period('M'))]
                print(f"Počet riadkov po filtrovaní: {len(filtered_df)}")

                # Výpočet štatistík
                if not filtered_df.empty:
                    median = filtered_df['Cena'].median()
                    mean = filtered_df['Cena'].mean()
                    percentile_10 = filtered_df['Cena'].quantile(0.1)
                    percentile_90 = filtered_df['Cena'].quantile(0.9)

                    # Pridanie výsledkov do zoznamu
                    vysledky.append({
                        'Instrument': instrument,
                        'Rozdiel_mesiacov': f'{rozdiel} mesiacov pred',
                        'Median': median,
                        'Mean': mean,
                        '10_percentil': percentile_10,
                        '90_percentil': percentile_90
                    })

    # Konverzia výsledkov na DataFrame
    vysledny_df = pd.DataFrame(vysledky)

    # Uloženie výsledkov do Excel súboru
    vysledny_df.to_excel(vystupny_subor, index=False)

# Cesty k súborom
vstupny_subor = r"C:\Users\david\data_factory\DE-AT\Spojené DE-AT Month.xlsx"
vystupny_subor = r"C:\David M\Historické dáta\Dáta\Futures\Spready krajiny\DE-AT\DE-AT Month Spread.xlsx"

# Vytvorenie adresára, ak neexistuje
os.makedirs(os.path.dirname(vystupny_subor), exist_ok=True)

# Spracovanie Excel súboru
spracuj_excel(vstupny_subor, vystupny_subor)
