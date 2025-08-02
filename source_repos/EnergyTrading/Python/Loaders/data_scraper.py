#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jul 24 12:09:16 2023

@author: marek
"""

from io import BytesIO
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from bs4 import BeautifulSoup
import numpy as np
import pytz

_HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/116.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "sk,cs;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate",
            "Cookie": "cookieaccept=yes",
            "Connection": "close",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        }

def is_dst_transition(date, timezone_str="Europe/Berlin"):
    tz = pytz.timezone(timezone_str)
    localized_date = tz.localize(date, is_dst=None)
    one_day_later = localized_date + timedelta(days=1)
    # DST is considered to be different if the UTC offset changes
    return localized_date.utcoffset() != one_day_later.utcoffset()

def json2df(json_data, date):
    data = json.loads(json_data)
    h_list = [int(x[0][1:]) - 1 if x[0] not in ['H3B'] else 2 for x in data['rows']]
    date_list = [date.replace(hour=h) for h in h_list]
    df_data = pd.DataFrame(data["rows"], columns=[col["label"].lower().split(' (')[0] for col in data["cols"]])
    df_data['datetime'] = date_list   

    return df_data.drop(columns=['hours'])

# Private function that will be used in scrape_epexSpotPrices()
#  that will substract 1 day from date in the format 'YYYY-MM-DD'
def _subtract_day(date):
    date = datetime.strptime(date, '%Y-%m-%d')
    date = date - timedelta(days=1)
    date = date.strftime('%Y-%m-%d')
    return date

# Private function to validate scraped values, if the values cannot be transformed into numeric values
# the function will return np.nan
def _val_numeric(string):
    try:
        if '.' in string:
            return pd.to_numeric(string.replace(',','').replace(' ',''))
        else:
            return pd.to_numeric(string.replace(',','.').replace(' ',''))
    except:
        return np.nan

def _setCookies(response, cookies_names):
    set_cookie_header = response.headers['Set-Cookie']
    cookies = {}
    cookie_parts = set_cookie_header.replace(',',';').split('; ')
    for cookie_part in cookie_parts:
        cookie_attr = cookie_part.split('=')
        if cookie_attr[0] in cookies_names and len(cookie_attr) > 1:
            cookies[cookie_attr[0]] = cookie_attr[1]
    return cookies
    
def _create_emptydf(date):
    df = pd.DataFrame(columns=['datetime', 'b_volume', 's_volume', 'volume', 'price'])
    df.set_index('datetime', inplace=True)
    df = pd.concat([df, pd.DataFrame({
        'datetime': [datetime.strptime(f"{date} {i}:00:00",'%Y-%m-%d %H:%M:%S') for i in range(24)]
        }).set_index('datetime')])
    df.fillna(np.nan, inplace=True)

    return df


def scrapeEpex(market_area='AT'):
    if market_area == 'DE':
        market_area = 'DE-LU'
    elif market_area in ['DKW', 'DK']:
            market_area = 'DK1'
    elif market_area == 'DKE':
        market_area = 'DK2'
    """
    Scrape EPEX Spot Prices for a specific market area for last 2 days including dayahead and today.
    parameters:
        market_area (str, optional): The market area code. Default is 'AT'.
    returns:
        result_df (DataFrame): DataFrame with scraped data
    """

    def _scrape_epexSpotPricesDayAhead(market_area='AT', day_ahead=True):
        """
        Scrape EPEX Spot Prices for a specific market area and dates.

        Parameters:
            market_area (str, optional): The market area code. Default is 'AT'.
            current_date (bool, optional): If True, the current date will be used. If False, the previous date will be used. Default is True.

        """
        # Get the current date in the format 'YYYY-MM-DD'
        trading_date = datetime.now().strftime('%Y-%m-%d')
        delivery_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        if not day_ahead:
            trading_date = _subtract_day(trading_date)
            delivery_date = _subtract_day(delivery_date)

        url = (f"https://www.epexspot.com/en/market-data?market_area={market_area}&"
            f"trading_date={trading_date}&delivery_date={delivery_date}"
            f"&underlying_year=&modality=Auction&sub_modality=DayAhead"
            f"&technology=&product=60&data_mode=table&period=&production_period="
            )
        
        response = requests.get(url, headers=_HEADERS, verify=False)
        
        if response.status_code != 200:
            print("Failed to fetch data from the webpage.")
            raise ValueError(f"Error: EPEX {market_area} {(trading_date, delivery_date)}: Failed to fetch data from the webpage.\n response: {response}")

        soup = BeautifulSoup(response.content, "html.parser")
        
        try:
            values = [_val_numeric(td.text.replace(',','')) for td in soup.find('div', class_='js-table-values').find_all('td')]
            times = [li.text[:2] for li in soup.find('div', class_='js-table-times').find_all('li')]
            date = soup.find(string=lambda text: 'Auction >' in text).split('>')[-1].strip()
            dates = [datetime.strptime(f"{date} {t}:00:00", "%d %B %Y %H:%M:%S") for t in times]
            
            column1, column2, column3, column4 = [values[i::4] for i in range(4)]
        except Exception as e:
            raise ValueError(f"SCRAPING Data not found for TD:{trading_date} DT:{delivery_date}")

        # Create a dictionary with the column names and their respective lists
        data = {
            'datetime': dates,
            'b_volume': column1,
            's_volume': column2,
            'volume': column3,
            'price': column4
        }
        
        df = pd.DataFrame(data)
        df.set_index("datetime", inplace=True)

        return df

    def _scrape_epexSpotPricesToday(market_area='AT'):
        """
        Scrape EPEX Spot Prices for a specific market for the previous day.
        """
        today = _scrape_epexSpotPricesDayAhead(market_area, day_ahead=False)
        return today

    return pd.concat([_scrape_epexSpotPricesToday(market_area),
                      _scrape_epexSpotPricesDayAhead(market_area)])

def scrapeOkte(delta=4, end=None):
    """
    Scrape OKTE prices from the website in range of 4 days
    parameters:
        delta (int, optional): Number of days to scrape. Default is 4
    returns:
        result_df (DataFrame): DataFrame with scraped data
    """
    if end == None:
        dayahead = (datetime.now() + timedelta(days=1))
        deltaDay = dayahead + timedelta(days=-delta)
    else:
        dayahead = pd.to_datetime(end)
        deltaDay = dayahead + timedelta(days=-delta)

    url = (f"https://isot.okte.sk/api/v1/dam/results?" \
        f"deliveryDayFrom={deltaDay.strftime('%Y-%m-%d')}&deliveryDayTo={dayahead.strftime('%Y-%m-%d')}")
    response = requests.get(url, verify=False)
    if response.status_code != 200:
        raise ValueError(f"Error: SK : {url}: Failed to fetch data from the webpage.\n response: {response}")
    try:
        data_df = pd.DataFrame(response.json())
        date = [pd.to_datetime(x, utc=True).tz_convert('Europe/Berlin').replace(tzinfo=None)
                for x in data_df['deliveryStart']]
        result_df = pd.DataFrame({
            'datetime': date,
            'b_volume': data_df['purchaseSuccessfulVolume'],
            's_volume': data_df['saleSuccessfulVolume'],
            'volume': data_df[['saleSuccessfulVolume','purchaseSuccessfulVolume']].max(axis=1),
            'price': data_df['price']
        })
        result_df.set_index("datetime", inplace=True)
    except Exception as e:
        raise ValueError(f"e\{data_df.head()}\{date}")

    return result_df

def scrapeOte(delta=5):
    """
    Scrape OTE prices from the website in range of delta days
    parameters:
        delta (int, optional): Number of days to scrape. Default is 5
    returns:
        result_df (DataFrame): DataFrame with scraped data
    """

    def _scrape_Ote_date(delta=0):
        date = (datetime.now() + timedelta(days=(-delta+1))).strftime('%Y-%m-%d')
        df_result = _create_emptydf(date)
        url = f"https://www.ote-cr.cz/cs/kratkodobe-trhy/elektrina/denni-trh?date={date}"
        response = requests.get(url, verify=False)
        if response.status_code != 200:
            raise ValueError(f"CZ : {date}: Failed to fetch data from the webpage.\n response: {response}")

        soup = BeautifulSoup(response.content, "html.parser")
        try:
            soup_elements = soup.find_all(class_='report_table')[1].find_all('td')
            data = [_val_numeric(x.text) for x in soup_elements]
            price, volume, saldo = [data[i::5] for i in range(3)]
            for i in range(len(df_result)):
                df_result.iloc[i,0] = (volume[i] - saldo[i]) if saldo[i] > 0 else volume[i]
                df_result.iloc[i,1] = volume[i] if saldo[i] > 0 else (volume[i] + saldo[i])
                df_result.iloc[i,2] = volume[i]
                df_result.iloc[i,3] = price[i] 
        except Exception as e:
            raise ValueError(f"SCRAPER OteCZ : Data not found for date:{date}")
        return df_result.astype(float)

    df_result = _scrape_Ote_date()
    for i in range(1,delta):
        df_result = pd.concat([df_result, _scrape_Ote_date(i)])
    return df_result.sort_index(ascending=True)


def scrapeSi(delta=5, _from=None):

    def _si_FetchXls(year=None):
        #FIXME: replace hardcoded year
        year_string = (lambda y: ("_"+y) if (y and y != str(datetime.now().year) ) else '')(year)
        response = requests.get(f"https://www.bsp-southpool.com/day-ahead-trading-results-si.html?file=files/documents/trading/MarketResultsAuction{year_string}.xlsx", verify=False)
        if response.status_code != 200:
            raise ValueError(f"SI response error: Data not found for date:{year} \n response: {response}")
        return response.content

    def _si_ProcessMonth(response, month , _from, _to):
        try:
            df = pd.read_excel(BytesIO(response),sheet_name=month,usecols='A,D:AA')
        except Exception as e:
            raise ValueError(f"{e}, line number: {e.__traceback__.tb_lineno}")
        index = (lambda col: next((i for i, x in enumerate(col) if x == "Delivery Date"), None))(df.iloc[1:,0])
        df_price = df.iloc[1:index+1,:].dropna()
        df_volume = df.iloc[index+2:,:].dropna()
        df_result = pd.DataFrame(columns=['datetime','b_volume','s_volume','volume','price'])
        for i in range(len(df_price)):
            df_result = pd.concat([df_result, pd.DataFrame({
                'datetime': pd.date_range(start=df_price.iloc[i,0], periods=24, freq='H'),
                'b_volume': np.nan,
                's_volume': np.nan,
                'volume': df_volume.iloc[i,1:].values,
                'price': df_price.iloc[i,1:].values
            })])
        df_result = df_result[(df_result['datetime'].dt.date <=
                                _to.date()) &
                                  (df_result['datetime'].dt.date >= _from.date())]
        return df_result

    dateNow = datetime.now() + relativedelta(days=1)

    if _from:
        try:
            _from = pd.to_datetime(_from)
        except:
            print("Wrong date format. Use YYYY-MM-DD")
            return
    else:
        _from = dateNow - timedelta(days=delta)
    
    difference = relativedelta(dateNow, _from)
    diff_months = 12 - _from.month + dateNow.month if dateNow.month < _from.month else dateNow.month - _from.month
    total_months =  difference.years * 12 + diff_months

    df_result = pd.DataFrame(columns=['datetime','b_volume','s_volume','volume','price'])
    yearStamp, response = None, None

    try:
        for i in range(total_months+1):
            year = (_from + relativedelta(months=i)).year
            month = (_from + relativedelta(months=i))
            if yearStamp != year:
                response = _si_FetchXls(str(year))
                yearStamp = year
            if response:
                df_result = pd.concat([df_result, _si_ProcessMonth(response, month.strftime("%B"), _from, dateNow)])

        return df_result.set_index("datetime")
    except Exception as e:
        raise ValueError(f"{e}, line number: {e.__traceback__.tb_lineno}")

def _toDate(string):
    try:
        return pd.to_datetime(string)
    except:
        print("Wrong date format. Use YYYY-MM-DD")
        return
    
def scrapeRo(delta=5, _from=None, _to=None):
    """
    Example:
        data = scrapeRu(_from="2021-01-01", _to="2021-01-05")\n
        data = scrapeRu(delta=5)\n
    params:
        delta: number of days to scrape
        _from: start date
        _to: end date, default is day ahead
    """

    def _scrapeRo_getSoup(date):
        url = "https://www.opcom.ro/grafice-ip-raportPIP-si-volumTranzactionat/en"
        response = requests.get(url, verify=False)

        if response.status_code != 200:
            raise ValueError(f"RO : {(date)}: Failed to fetch data from the webpage.\n response: {response}")
            return -1
        try:
            soup = BeautifulSoup(response.content, "html.parser")
            token_value = soup.select_one('input[name="_token"]')['value']
            data = {
                '_token': token_value,
                'day': date.strftime("%d"),
                'month': date.strftime("%m"),
                'year': date.year,
                'buton': 'Refresh'
            }
            # Parse the Set-Cookie header to extract cookies
            cookies_names = ['laravel_session', 'XSRF-TOKEN', 'PHPSESSID']
            set_cookie_header = response.headers['Set-Cookie']
            cookies = {}
            cookie_parts = set_cookie_header.replace(',',';').split('; ')
            for cookie_part in cookie_parts:
                cookie_attr = cookie_part.split('=')
                if cookie_attr[0] in cookies_names and len(cookie_attr) > 1:
                    cookies[cookie_attr[0]] = cookie_attr[1]
        except Exception as e:
            raise ValueError("problem during cookies extraction, {e}")

        response = requests.post(url, cookies=cookies, data=data, verify=False)
        soup = BeautifulSoup(response.content, "html.parser")

        return soup

    def _scrape_Ro_date(date):
        soup = _scrapeRo_getSoup(date)
        df_result = pd.DataFrame(columns=['datetime','b_volume','s_volume','volume','price'])
        try:
            elements = soup.find(id='tab_PIP_Vol').find_all('tr')
            data = [x.find_all('td') for x in elements][1:]
            result = [cell.text for row in data for cell in row]
            periods_length = len(result[4::6])
            df_result = pd.concat([df_result, pd.DataFrame({
                'datetime': pd.date_range(start=date.date(), periods=periods_length, freq='h').tolist(),

                'b_volume': [_val_numeric(x) for x in result[4::6]],
                's_volume': [_val_numeric(x) for x in result[5::6]],
                'volume': [_val_numeric(x) for x in result[3::6]],
                'price': [_val_numeric(x) for x in result[2::6]]

            })])
        except Exception as e:
            raise ValueError(f"RO : Failed to scrape data {date}\ {e}")
        return df_result

    dateNow = datetime.now() + timedelta(days=1)
    if _from:
        _from = _toDate(_from)
    else:
        _from = dateNow - timedelta(days=delta)
    if _to:
        _to = _toDate(_to)
    else:
        _to = dateNow

    current = _from
    df_result = pd.DataFrame(columns=['datetime','b_volume','s_volume','volume','price'])
    while current <= _to:
        df_current = _scrape_Ro_date(current)
        df_result = pd.concat([df_result, df_current])
        current = current + timedelta(days=1)

    return df_result.set_index('datetime')
    
def _scrapeIta_getSoup(date):
    # TODO: implement
    url = "https://www.mercatoelettrico.org/En/Default.aspx"
    response = requests.get(url, verify=False)
    date = date.strftime("%Y%m%d")

    if response.status_code != 200:
        raise ValueError(f"Error: IT : Failed to fetch data from the webpage.")
    
    soup = BeautifulSoup(response.content, "html.parser")

    # Parse the Set-Cookie header to extract cookies
    cookies_names = ['ASP.NET_SessionId','GMEInglese','GmeItaliano']
    set_cookie_header = response.headers['Set-Cookie']
    cookies = {}
    cookie_parts = set_cookie_header.replace(',',';').split('; ')
    for cookie_part in cookie_parts:
        cookie_attr = cookie_part.split('=')
        if cookie_attr[0] in cookies_names and len(cookie_attr) > 1:
            cookies[cookie_attr[0]] = cookie_attr[1]

    url = f"https://www.mercatoelettrico.org/It/WebServerDataStore/MGP_Prezzi/{date}MGPPrezzi.xml"
    responseXml = requests.get(url, cookies=cookies, verify=False)
    soup = BeautifulSoup(responseXml.content, "html.parser")
    return soup


def scrapeBg(delta=5, _from=None, _to=None):
    """
    Example:
        data = scrapeBu(_from="2021-01-01", _to="2021-01-05")\n
        data = scrapeBu(delta=5)\n
    params:
        delta: number of days to scrape
        _from: start date
        _to: end date, default is day ahead
    """
    def _scrape_Bg_getSoup(date):
        url = "https://ibex.bg/markets/dam/day-ahead-prices-and-volumes-v2-0-2/"
        response = requests.get(url, headers=_HEADERS ,verify=False)
        if response.status_code != 200:
            raise ValueError(f" BG {date}: Failed to fetch data from the webpage.\n response: {response}")
            return
        soup = BeautifulSoup(response.content, "html.parser")

        # Parse the Set-Cookie header to extract cookies
        cookies = _setCookies(response, ['__wpdm_client',
                                        '_ga_5LBFZ1MK81', '_ga', 'pll_language'])
        data = {
            'fromDate': date.strftime("%Y-%m-%d"),
            'but_search': 'Search'
        }
        responsePost = requests.post(url, cookies=cookies, data=data, headers=_HEADERS,
                                    verify=False)
        if response.status_code != 200:
            raise ValueError(f"BG post request failed.\ {data} \ {cookies} n response: {response}")

        soup = BeautifulSoup(responsePost.content, "html.parser")
        return soup

    def _scrape_Bg_date(date):
        soup = _scrape_Bg_getSoup(date)
        try:
            table = soup.select('#dam-php-table tr')[1:]
            dateTime, volume, price = [], [], []
            for row in table:
                dateTime.append(datetime.strptime(row.select_one('.column-date').text +
                            row.select_one('.column-time_part').text, "%Y-%m-%d%H:%M:%S"))
                volume.append(_val_numeric(row.select_one('.column-volume').text))
                price.append(_val_numeric(row.select_one('.column-price_eur').text))

            df = pd.DataFrame(columns=['datetime','b_volume','s_volume','volume','price'],
                            data={'datetime':dateTime, 'volume': volume, 'price': price})
            df.fillna(np.nan, inplace=True)
            df.sort_values(by=['datetime'], inplace=True)

            return df
        except Exception as e:
            print(f"Data not found for date:{date}")
            return -1

    dateNow = (datetime.now() + timedelta(days=1)
               ).replace(hour=0, minute=0, second=0, microsecond=0)
    if _from:
        _from = _toDate(_from)
    else:
        _from = dateNow - timedelta(days=delta)
    if _to:
        _to = _toDate(_to)
    else:
        _to = dateNow

    current = _to
    df_result = pd.DataFrame(columns=['datetime','b_volume','s_volume','volume','price'])
    try:
        while current > _from:
            df_current = _scrape_Bg_date(current)
            df_result = pd.concat([df_result, df_current])
            current = current - timedelta(days=7)

        df_result = df_result[(df_result['datetime'] <=
                        _to + timedelta(days=1)) 
                        & (df_result['datetime'] >= _from)]
        df_result.set_index('datetime', inplace=True)
        df_result.sort_index(inplace=True)
        return df_result
    except Exception as e:
        raise ValueError(f"BG failed exception: {e} line number {e.__traceback__.tb_lineno}")

def scrapeHu(delta=5, _from=None, _to=None):
    headers = {
        'Accept': '*/*',
        'Accept-Language': 'sk,cs;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate',
        'X-Requested-With': 'XMLHttpRequest',
        'Connection': 'close',
        'Referer': 'https://hupx.hu/en/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin'
    }
    def _scrapeHupxDate(date):
        urlDate = f"https://hupx.hu/en/dam/homepage/graph.json?date={date.strftime('%Y-%m-%d')}"
        responseDate = requests.get(urlDate, headers=headers)
        if responseDate.status_code != 200:
            raise ValueError(f"HU {date}: Failed to fetch data from the webpage.\n response: {responseDate}")
            
        data_df = json2df(responseDate.content, date)
        return data_df
    dateNow = (datetime.now() + timedelta(days=1)
            ).replace(hour=0, minute=0, second=0, microsecond=0)
    if _from:
        _from = _toDate(_from)
    else:
        _from = dateNow - timedelta(days=delta)
    if _to:
        _to = _toDate(_to)
    else:
        _to = dateNow

    current = _to
    df_result = pd.DataFrame(columns=['datetime','b_volume','s_volume','volume','price'])
    try:
        while current > _from:
            df_current = _scrapeHupxDate(current)
            if df_current is None:
                current = current - timedelta(days=1)
                continue
            df_result = pd.concat([df_result, df_current])
            current = current - timedelta(days=1)

        df_result = df_result[(df_result['datetime'] <=
                        _to + timedelta(days=1))
                        & (df_result['datetime'] >= _from)]
        df_result.set_index('datetime', inplace=True)
        df_result.sort_index(inplace=True)
        check_duplicates = False
        for i in range(1,25):
            if df_result.iloc[-i,2] == df_result.iloc[-(i+24),2] and df_result.iloc[-i,3] == df_result.iloc[-(i+24),3]:
                check_duplicates = True
                break
        if check_duplicates:
            df_result[-24:] = np.nan
        return df_result
    except Exception as e:
        raise ValueError(f"HU - failed, exception {e}, line {e.__traceback__.tb_lineno}")
    

def scrapeIta(delta=2, _from=None, _to=None):
    dateNow = (datetime.now() + timedelta(days=1)
        ).replace(hour=0, minute=0, second=0, microsecond=0)
    if _from:
        _from = _toDate(_from)
    else:
        _from = dateNow - timedelta(days=delta)
    if _to:
        _to = _toDate(_to)
    else:
        _to = dateNow
    
    hello = requests.get("https://www.mercatoelettrico.org/en-us/Home/Results/Electricity/MGP/Results/PUN", headers=_HEADERS)
    cookies = _setCookies(hello,
                           ['.ASPXANONYMOUS', 'dnn_IsMobile', '__RequestVerificationToken'])
    # 20250115 date format YYYYMMDD
    _from = _from.strftime("%Y%m%d")
    _to = _to.strftime("%Y%m%d")

    zones = ["PUN"]
    headers_token = 'RequestVerificationToken'
    get_url = f"https://www.mercatoelettrico.org/DesktopModules/GmeEsitiPrezziME/API/item/GetMEPrezzi?DataInizio={_from}&DataFine={_to}&Granularita=h&Mercato=MGP&Zona={zones[0]}&Tipologia=PUN"
    