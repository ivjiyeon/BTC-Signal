import sys
import os

VENV_PYTHON = "/home/ivjiyeonb/projects/reverse_engineering_signal/venv/bin/python"

# If the current interpreter is not the one from the venv, re-execute with the venv's interpreter
if sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

# Original script content starts here (without the old shebang)
import requests
import json
import pandas as pd
import ta
from datetime import datetime, timedelta

# Binance API endpoint
BINANCE_API_URL = "https://api.binance.us/api/v3/klines"

def fetch_klines(symbol, interval, limit=100, exclude_current=False):
    """Fetches klines data from Binance.us."""
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    response = requests.get(BINANCE_API_URL, params=params)
    response.raise_for_status() # Raise an exception for HTTP errors
    data = response.json()

    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    # Convert only numeric columns to float, keep timestamp as datetime
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    df[numeric_cols] = df[numeric_cols].astype(float)
    df = df.set_index('timestamp')

    # Added logic to exclude the current candle
    if exclude_current and not df.empty:
        df = df.iloc[:-1] # Drop the last row

    return df

def calculate_indicators(df):
    """Calculates all necessary technical indicators."""
    df['MA_20'] = ta.trend.sma_indicator(df['close'], window=20)
    df['MA_100'] = ta.trend.sma_indicator(df['close'], window=100)

    macd = ta.trend.MACD(df['close'])
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['MACD_Hist'] = macd.macd_diff()

    ichimoku = ta.trend.IchimokuIndicator(df['high'], df['low'], window1=9, window2=26, window3=52, visual=False)
    df['Ichimoku_Conversion_Line'] = ichimoku.ichimoku_conversion_line()
    df['Ichimoku_Base_Line'] = ichimoku.ichimoku_base_line()
    df['Ichimoku_A'] = ichimoku.ichimoku_a()
    df['Ichimoku_B'] = ichimoku.ichimoku_b()
    return df

def generate_signals():
    """Generates trading signals based on the provided strategy and prints a message."""
    symbol = 'BTCUSDT' # NOTE: Binance.us might use BTCUSD instead of BTCUSDT. Let's keep an eye on this.
    # Fetch enough data to calculate indicators (e.g., for MA_100 and Ichimoku_B_52)
    # 100 periods for MA_100, and Ichimoku's longest period is 52. Let's fetch a bit more for safety.
    limit_15m = 150 # ~37.5 hours
    limit_1h = 150 # ~6.25 days
    limit_4h = 150 # ~25 days

    try:
        # Fetch one extra candle and then exclude the current one to ensure all are closed.
        df_15m = fetch_klines(symbol, '15m', limit=limit_15m + 1, exclude_current=True)
        df_1h = fetch_klines(symbol, '1h', limit=limit_1h + 1, exclude_current=True)
        df_4h = fetch_klines(symbol, '4h', limit=limit_4h + 1, exclude_current=True)
    except Exception as e:
        return f"Error fetching klines data: {e}"

    df_15m = calculate_indicators(df_15m)
    df_1h = calculate_indicators(df_1h)
    df_4h = calculate_indicators(df_4h)

    # Merge dataframes using merge_asof for the closest previous timestamp
    df_merged = pd.merge_asof(df_15m, df_1h.add_suffix('_1h'),
                              left_index=True, right_index=True, direction='backward')
    df_merged = pd.merge_asof(df_merged, df_4h.add_suffix('_4h'),
                              left_index=True, right_index=True, direction='backward')

    df_merged = df_merged.dropna()

    if df_merged.empty:
        return "No sufficient data to generate signals."

    latest_row = df_merged.iloc[-1] # This will now correctly reference the last CLOSED candle
    timestamp = (latest_row.name + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S") # Modified to show close time
    signal_message = f"BTCUSDT Signal ({timestamp}): "
    signal_found = False

    # LONG Signal Strategy
    long_condition_1h_ma = latest_row['close_1h'] > latest_row['MA_100_1h']
    long_condition_1h_ichimoku_cloud = latest_row['Ichimoku_A_1h'] > latest_row['Ichimoku_B_1h']
    long_condition_4h_ma = latest_row['close_4h'] > latest_row['MA_20_4h']
    long_condition_4h_macd_hist = latest_row['MACD_Hist_4h'] > 0
    long_condition_4h_macd_line = latest_row['MACD_4h'] > latest_row['MACD_Signal_4h']
    long_condition_4h_ichimoku_conversion_base = latest_row['Ichimoku_Conversion_Line_4h'] > latest_row['Ichimoku_Base_Line_4h']

    if (long_condition_1h_ma and long_condition_1h_ichimoku_cloud and
        long_condition_4h_ma and long_condition_4h_macd_hist and
        long_condition_4h_macd_line and long_condition_4h_ichimoku_conversion_base):
        signal_message += "LONG 🚀"
        signal_found = True

    # SHORT Signal Strategy
    short_condition_15m_ichimoku_cloud = latest_row['Ichimoku_A'] < latest_row['Ichimoku_B']
    short_condition_1h_ichimoku_conversion_base = latest_row['Ichimoku_Conversion_Line_1h'] < latest_row['Ichimoku_Base_Line_1h']
    short_condition_4h_ma = latest_row['close_4h'] < latest_row['MA_100_4h']
    short_condition_4h_ichimoku_cloud = latest_row['Ichimoku_A_4h'] < latest_row['Ichimoku_B_4h']

    if (short_condition_15m_ichimoku_cloud and
        short_condition_1h_ichimoku_conversion_base and
        short_condition_4h_ma and short_condition_4h_ichimoku_cloud):
        if signal_found: # If both long and short conditions are met, which shouldn't happen with this logic but as a safeguard
            signal_message += " (Also SHORT 📉 - CONFLICT!)"
        else:
            signal_message += "SHORT 📉"
            signal_found = True

    if not signal_found:
        return "" # Return empty string if no signal

    return signal_message

if __name__ == '__main__':
    print(generate_signals())
    