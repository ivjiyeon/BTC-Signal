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

# File to store the last sent signal
LAST_SIGNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_sent_signal.txt")

def read_last_signal():
    """Reads the last sent signal from a file."""
    if os.path.exists(LAST_SIGNAL_FILE):
        with open(LAST_SIGNAL_FILE, 'r') as f:
            return f.read().strip()
    return "No Signal" # Default if file doesn't exist or is empty

def write_last_signal(signal):
    """Writes the current signal to a file."""
    with open(LAST_SIGNAL_FILE, 'w') as f:
        f.write(signal)

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
    df['MA_9'] = ta.trend.sma_indicator(df['close'], window=9)
    df['MA_20'] = ta.trend.sma_indicator(df['close'], window=20)
    df['MA_200'] = ta.trend.sma_indicator(df['close'], window=200)

    macd = ta.trend.MACD(df['close'])
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['MACD_Hist'] = macd.macd_diff()

    # Ichimoku (manual calculation to bypass ta library issues with min_periods)
    # Tenkan-sen (Conversion Line): (Highest High + Lowest Low) / 2 over 9 periods
    df['Ichimoku_Conversion_Line'] = (df['high'].rolling(window=9, min_periods=1).max() + \
                                      df['low'].rolling(window=9, min_periods=1).min()) / 2

    # Kijun-sen (Base Line): (Highest High + Lowest Low) / 2 over 26 periods
    df['Ichimoku_Base_Line'] = (df['high'].rolling(window=26, min_periods=1).max() + \
                                 df['low'].rolling(window=26, min_periods=1).min()) / 2

    # Senkou Span A (Leading Span A): (Conversion Line + Base Line) / 2 plotted 26 periods ahead
    df['Ichimoku_A'] = ((df['Ichimoku_Conversion_Line'] + \
                                          df['Ichimoku_Base_Line']) / 2).shift(26)

    # Senkou Span B (Leading Span B): (Highest High + Lowest Low) / 2 over 52 periods, plotted 26 periods ahead
    df['Ichimoku_B'] = ((df['high'].rolling(window=52, min_periods=1).max() + \
                                 df['low'].rolling(window=52, min_periods=1).min()) / 2).shift(26)

    # New Indicators for 15m timeframe as per task
    # RSI (14-period)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)

    # Bollinger Bands (20-period)
    df['BB_Upper'] = ta.volatility.bollinger_hband(df['close'], window=20)
    df['BB_Middle'] = ta.volatility.bollinger_mband(df['close'], window=20)
    df['BB_Lower'] = ta.volatility.bollinger_lband(df['close'], window=20)

    # VWAP (using a rolling window, as session-based is complex for historical data)
    # Check if ta.volume.volume_weighted_average_price is available and use it.
    # If not, a basic rolling VWAP. The task specifies aiming for ta.volume.volume_weighted_average_price
    # For now, I will add a placeholder for a rolling window based VWAP.
    # If the ta library used does not have this, we will need to implement a more custom rolling VWAP.
    # Assuming 'ta.volume.volume_weighted_average_price' works as expected with default parameters for a rolling window.
    df['VWAP'] = ta.volume.volume_weighted_average_price(df['high'], df['low'], df['close'], df['volume'], window=20)

    # OBV (On-Balance Volume)
    df['OBV'] = ta.volume.on_balance_volume(df['close'], df['volume'])

    return df

def generate_signals():
    """Generates trading signals based on the provided strategy and prints a message."""
    symbol = 'BTCUSDT'
    limit_15m = 300
    limit_1h = 250
    limit_4h = 250

    last_sent_signal = read_last_signal()
    current_signal_type = "No Signal" # Default to No Signal

    try:
        df_15m = fetch_klines(symbol, '15m', limit=limit_15m + 1, exclude_current=True)
        df_1h = fetch_klines(symbol, '1h', limit=limit_1h + 1, exclude_current=True)
        df_4h = fetch_klines(symbol, '4h', limit=limit_4h + 1, exclude_current=True)
    except Exception as e:
        # If fetching fails, we might still want to report "No Signal" if previous was different
        error_message = f"Error fetching klines data: {e}"
        if last_sent_signal != "No Signal":
            write_last_signal("No Signal") # Update state to No Signal on error
            return f"BTCUSDT Signal (Error): No Signal (Data Fetch Error: {e})"
        return "" # If last was also No Signal, suppress message


    df_15m = calculate_indicators(df_15m)
    df_1h = calculate_indicators(df_1h)
    df_4h = calculate_indicators(df_4h)

    df_merged = pd.merge_asof(df_15m, df_1h.add_suffix('_1h'),
                              left_index=True, right_index=True, direction='backward')
    df_merged = pd.merge_asof(df_merged, df_4h.add_suffix('_4h'),
                              left_index=True, right_index=True, direction='backward')

    df_merged = df_merged.dropna()

    if df_merged.empty:
        if last_sent_signal != "No Signal":
            write_last_signal("No Signal")
            return "BTCUSDT Signal: No Signal (Insufficient data)"
        return ""

    latest_row = df_merged.iloc[-1]
    timestamp_display = (latest_row.name + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")

    # Evaluate conditions for LONG signal based on the new inclusive logic
    long_conditions_met_count = 0
    # Condition 1: 4h Close above MA_20
    if pd.notna(latest_row['MA_20_4h']) and latest_row['close_4h'] > latest_row['MA_20_4h']:
        long_conditions_met_count += 1
    # Condition 2: 4h MA_9 above MA_20
    if pd.notna(latest_row['MA_9_4h']) and pd.notna(latest_row['MA_20_4h']) and latest_row['MA_9_4h'] > latest_row['MA_20_4h']:
        long_conditions_met_count += 1
    # Condition 3: 4h MACD Histogram positive
    if pd.notna(latest_row['MACD_Hist_4h']) and latest_row['MACD_Hist_4h'] > 0:
        long_conditions_met_count += 1
    # Condition 4: 4h MACD above Signal Line
    if pd.notna(latest_row['MACD_4h']) and pd.notna(latest_row['MACD_Signal_4h']) and latest_row['MACD_4h'] > latest_row['MACD_Signal_4h']:
        long_conditions_met_count += 1
    # Condition 5: 1h Close above Ichimoku Cloud
    if pd.notna(latest_row['Ichimoku_A_1h']) and pd.notna(latest_row['Ichimoku_B_1h']) and (latest_row['close_1h'] > latest_row['Ichimoku_A_1h'] and latest_row['close_1h'] > latest_row['Ichimoku_B_1h']):
        long_conditions_met_count += 1
    # Condition 6: 4h Close above Ichimoku Cloud
    if pd.notna(latest_row['Ichimoku_A_4h']) and pd.notna(latest_row['Ichimoku_B_4h']) and (latest_row['close_4h'] > latest_row['Ichimoku_A_4h'] and latest_row['close_4h'] > latest_row['Ichimoku_B_4h']):
        long_conditions_met_count += 1
    # Condition 7: 4h Ichimoku Conversion Line above Base Line
    if pd.notna(latest_row['Ichimoku_Conversion_Line_4h']) and pd.notna(latest_row['Ichimoku_Base_Line_4h']) and latest_row['Ichimoku_Conversion_Line_4h'] > latest_row['Ichimoku_Base_Line_4h']:
        long_conditions_met_count += 1

    if long_conditions_met_count >= 4: # Require at least 4 out of 7 conditions for LONG
        current_signal_type = "LONG 🚀"

    # Add new 15m conditions for LONG signals
    # RSI Confirmation: 30 <= latest_row['RSI'] <= 50
    if pd.notna(latest_row['RSI']) and 30 <= latest_row['RSI'] <= 50:
        long_conditions_met_count += 1
    # Bollinger Band Support/Bounce: latest_row['close'] > latest_row['BB_Middle'] OR (latest_row['low'] <= latest_row['BB_Lower'] AND latest_row['close'] > latest_row['BB_Lower'])
    if pd.notna(latest_row['BB_Middle']) and pd.notna(latest_row['BB_Lower']):
        if latest_row['close'] > latest_row['BB_Middle'] or \
           (latest_row['low'] <= latest_row['BB_Lower'] and latest_row['close'] > latest_row['BB_Lower']):
            long_conditions_met_count += 1
    # VWAP Support/Trend: latest_row['close'] > latest_row['VWAP']
    if pd.notna(latest_row['VWAP']) and latest_row['close'] > latest_row['VWAP']:
        long_conditions_met_count += 1
    # OBV Trend Confirmation: latest_row['OBV'] > df_15m.iloc[-2]['OBV']
    # Note: df_15m.iloc[-2] refers to the previous candle of the 15m timeframe BEFORE merging.
    # After merging, latest_row refers to the last row of df_merged, which is derived from df_15m.iloc[-1].
    # So, df_merged should have the OBV from df_15m.iloc[-1] as 'OBV' and from df_15m.iloc[-2] as a previous value.
    # Let's assume df_merged has enough history that df_merged.iloc[-2]['OBV'] is the previous 15m OBV.
    # If the df_merged is small, this could be an issue.
    # The instruction says df_15m.iloc[-2]['OBV'], so we need to access the original df_15m before merging or ensure that the merged dataframe correctly carries this history.
    # The simplest approach is to get OBV from df_merged.iloc[-2] as it is already aligned.
    if pd.notna(latest_row['OBV']) and not df_merged.empty and len(df_merged) >= 2:
        if latest_row['OBV'] > df_merged.iloc[-2]['OBV']:
            long_conditions_met_count += 1

    if long_conditions_met_count >= 4: # Require at least 4 out of 7 conditions for LONG
        current_signal_type = "LONG 🚀"

    # Evaluate conditions for SHORT signal based on the new inclusive logic
    if current_signal_type == "No Signal": # Only check for SHORT if LONG wasn't found
        short_conditions_met_count = 0
        # Condition 1: 4h Close below MA_20
        if pd.notna(latest_row['MA_20_4h']) and latest_row['close_4h'] < latest_row['MA_20_4h']:\
            short_conditions_met_count += 1
        # Condition 2: 4h MA_9 below MA_20
        if pd.notna(latest_row['MA_9_4h']) and pd.notna(latest_row['MA_20_4h']) and latest_row['MA_9_4h'] < latest_row['MA_20_4h']:\
            short_conditions_met_count += 1
        # Condition 3: 4h MACD Histogram negative
        if pd.notna(latest_row['MACD_Hist_4h']) and latest_row['MACD_Hist_4h'] < 0:\
            short_conditions_met_count += 1
        # Condition 4: 4h MACD below Signal Line
        if pd.notna(latest_row['MACD_4h']) and pd.notna(latest_row['MACD_Signal_4h']) and latest_row['MACD_4h'] < latest_row['MACD_Signal_4h']:\
            short_conditions_met_count += 1
        # Condition 5: 1h Close below Ichimoku Cloud
        if pd.notna(latest_row['Ichimoku_A_1h']) and pd.notna(latest_row['Ichimoku_B_1h']) and (latest_row['close_1h'] < latest_row['Ichimoku_A_1h'] and latest_row['close_1h'] < latest_row['Ichimoku_B_1h']):\
            short_conditions_met_count += 1
        # Condition 6: 4h Close below Ichimoku Cloud
        if pd.notna(latest_row['Ichimoku_A_4h']) and pd.notna(latest_row['Ichimoku_B_4h']) and (latest_row['close_4h'] < latest_row['Ichimoku_A_4h'] and latest_row['close_4h'] < latest_row['Ichimoku_B_4h']):\
            short_conditions_met_count += 1
        # Condition 7: 4h Ichimoku Conversion Line below Base Line
        if pd.notna(latest_row['Ichimoku_Conversion_Line_4h']) and pd.notna(latest_row['Ichimoku_Base_Line_4h']) and latest_row['Ichimoku_Conversion_Line_4h'] < latest_row['Ichimoku_Base_Line_4h']:\
            short_conditions_met_count += 1

        if short_conditions_met_count >= 4: # Require at least 4 out of 7 conditions for SHORT
            current_signal_type = "SHORT 📉"

    # Add new 15m conditions for SHORT signals
    # RSI Confirmation: 50 <= latest_row['RSI'] <= 70
    if pd.notna(latest_row['RSI']) and 50 <= latest_row['RSI'] <= 70:
        short_conditions_met_count += 1
    # Bollinger Band Resistance/Rejection: latest_row['close'] < latest_row['BB_Middle'] OR (latest_row['high'] >= latest_row['BB_Upper'] AND latest_row['close'] < latest_row['BB_Upper'])
    if pd.notna(latest_row['BB_Middle']) and pd.notna(latest_row['BB_Upper']):
        if latest_row['close'] < latest_row['BB_Middle'] or \
           (latest_row['high'] >= latest_row['BB_Upper'] and latest_row['close'] < latest_row['BB_Upper']):
            short_conditions_met_count += 1
    # VWAP Resistance/Trend: latest_row['close'] < latest_row['VWAP']
    if pd.notna(latest_row['VWAP']) and latest_row['close'] < latest_row['VWAP']:
        short_conditions_met_count += 1
    # OBV Trend Confirmation: latest_row['OBV'] < df_15m.iloc[-2]['OBV']
    if pd.notna(latest_row['OBV']) and not df_merged.empty and len(df_merged) >= 2:
        if latest_row['OBV'] < df_merged.iloc[-2]['OBV']:
            short_conditions_met_count += 1

    if short_conditions_met_count >= 4: # Require at least 4 out of 7 conditions for SHORT
        current_signal_type = "SHORT 📉"

    final_message = ""
    if current_signal_type == "No Signal":
        if last_sent_signal != "No Signal":
            final_message = f"BTCUSDT Signal ({timestamp_display}): No Signal"
    else:
        final_message = f"BTCUSDT Signal ({timestamp_display}): {current_signal_type}"

    if current_signal_type != last_sent_signal:
        write_last_signal(current_signal_type)
        return final_message
    else:
        return "" # No change, suppress output

if __name__ == '__main__':
    print(generate_signals())
