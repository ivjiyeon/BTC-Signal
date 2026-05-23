import os
import requests
import json
import pandas as pd
import ta
from datetime import datetime, timedelta

def _evaluate_conditions(latest_row, df_merged, conditions):
    """Evaluates a list of conditions and returns the count of met conditions."""
    met_count = 0
    for condition_func in conditions:
        try:
            # All condition functions (lambdas) now accept both row and df_m
            # This simplifies the _evaluate_conditions function
            if condition_func(latest_row, df_merged):
                met_count += 1
        except (KeyError, TypeError): # Handle cases where a column might be missing or comparison with NaN
            continue
    return met_count

# --- Configuration Constants ---
BINANCE_API_URL = "https://api.binance.us/api/v3/klines"
LAST_SIGNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_sent_signal.txt")

# Indicator Window Constants
MA_SHORT_WINDOW = 9
MA_MEDIUM_WINDOW = 20
MA_LONG_WINDOW = 200
RSI_WINDOW = 14
BOLLINGER_WINDOW = 20
ICHIMOKU_TENKAN_WINDOW = 9
ICHIMOKU_KIJUN_WINDOW = 26
ICHIMOKU_SENKOU_B_WINDOW = 52
ICHIMOKU_DISPLACEMENT = 26
VWAP_WINDOW = 20 # Assuming 20-period rolling VWAP as implemented

# Data Fetch Limits (should cover the largest indicator window + displacement)
# For 15m, 1h, 4h, calculate limits based on the largest required window (Ichimoku Senkou B)
# We need enough data for Ichimoku_Senkou_B_Window (52) + Ichimoku_Displacement (26) + a few extra for safety/dropna
# max_window = max(MA_LONG_WINDOW, ICHIMOKU_SENKOU_B_WINDOW + ICHIMOKU_DISPLACEMENT)
# Since Ichimoku A and B are shifted by 26 periods, we need data for (window + shift).
# For 15m, to calculate 4h indicators, we need (4h / 15m) * (4h_window + 4h_shift) candles
# 4h interval: 4 * 4 = 16 15m candles
# Max needed: max(MA_LONG_WINDOW, ICHIMOKU_SENKOU_B_WINDOW + ICHIMOKU_DISPLACEMENT)
# For 4h: 200 (MA_LONG) or 52+26=78 (Ichimoku). So ~200 candles for 4h.
# For 1h: (200 * 4) = 800 candles.
# For 15m: (200 * 16) = 3200 candles.
# The original limits (300, 250, 250) are too small for MA_200.
# Let\'s adjust these to ensure enough data for all indicators, specifically MA_200.
# For MA_200 on 4h: Need at least 200 4h candles.
# For MA_200 on 1h: Need at least 200 1h candles.
# For MA_200 on 15m: Need at least 200 15m candles.
# Let\'s use a safe buffer of +50 on top of the max window required (200).
# So, for 4h and 1h, we need at least 250 candles for MA_200.
# For 15m, considering merging with 1h and 4h, we\'d need more.
# Given that the original script used 300 for 15m, and 250 for 1h/4h,
# and it uses `merge_asof` for backward fill, the current limits might be acceptable for the logic.
# I will stick to the original limits for now, as changing them might alter the logic and
# the task specifies not to change core signal generation logic, which includes the data it operates on.
# The `limit` in `fetch_klines` specifies the number of *candles* not periods.
# So, for a 200-period MA, we actually need 200 candles.
# The original limits for 1h and 4h are 250, which is enough for MA_200.
# For 15m, 300 is also enough.
# The problem might be with the `shift(26)` for Ichimoku leading spans if `min_periods` is 1 for rolling.
# `shift(26)` means we need 26 more candles in the past to calculate the shifted value.
# So if Ichimoku requires 52 + 26 = 78 candles, the current limits are sufficient.

KLINES_LIMIT_15M = 300
KLINES_LIMIT_1H = 250
KLINES_LIMIT_4H = 250

def read_last_signal():
    """Reads the last sent signal from a file."""
    if os.path.exists(LAST_SIGNAL_FILE):
        with open(LAST_SIGNAL_FILE, 'r') as f:
            return f.read().strip()
    return "No Signal" # Default if file doesn\'t exist or is empty

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
    df['MA_9'] = ta.trend.sma_indicator(df['close'], window=MA_SHORT_WINDOW)
    df['MA_20'] = ta.trend.sma_indicator(df['close'], window=MA_MEDIUM_WINDOW)
    df['MA_200'] = ta.trend.sma_indicator(df['close'], window=MA_LONG_WINDOW)

    macd = ta.trend.MACD(df['close'])
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['MACD_Hist'] = macd.macd_diff()

    # Ichimoku (manual calculation to bypass ta library issues with min_periods)
    # Tenkan-sen (Conversion Line): (Highest High + Lowest Low) / 2 over 9 periods
    high_9 = df['high'].rolling(window=ICHIMOKU_TENKAN_WINDOW, min_periods=1).max()
    low_9 = df['low'].rolling(window=ICHIMOKU_TENKAN_WINDOW, min_periods=1).min()
    df['Ichimoku_Conversion_Line'] = (high_9 + low_9) / 2

    # Kijun-sen (Base Line): (Highest High + Lowest Low) / 2 over 26 periods
    high_26 = df['high'].rolling(window=ICHIMOKU_KIJUN_WINDOW, min_periods=1).max()
    low_26 = df['low'].rolling(window=ICHIMOKU_KIJUN_WINDOW, min_periods=1).min()
    df['Ichimoku_Base_Line'] = (high_26 + low_26) / 2

    # Senkou Span A (Leading Span A): (Conversion Line + Base Line) / 2 plotted 26 periods ahead
    df['Ichimoku_A'] = ((df['Ichimoku_Conversion_Line'] + \
                                          df['Ichimoku_Base_Line']) / 2).shift(ICHIMOKU_DISPLACEMENT)

    # Senkou Span B (Leading Span B): (Highest High + Lowest Low) / 2 over 52 periods, plotted 26 periods ahead
    high_52 = df['high'].rolling(window=ICHIMOKU_SENKOU_B_WINDOW, min_periods=1).max()
    low_52 = df['low'].rolling(window=ICHIMOKU_SENKOU_B_WINDOW, min_periods=1).min()
    df['Ichimoku_B'] = ((high_52 + low_52) / 2).shift(ICHIMOKU_DISPLACEMENT)

    # New Indicators for 15m timeframe as per task
    # RSI (14-period)
    df['RSI'] = ta.momentum.rsi(df['close'], window=RSI_WINDOW)

    # Bollinger Bands (20-period)
    df['BB_Upper'] = ta.volatility.bollinger_hband(df['close'], window=BOLLINGER_WINDOW)
    df['BB_Middle'] = ta.trend.sma_indicator(df['close'], window=BOLLINGER_WINDOW)
    df['BB_Lower'] = ta.volatility.bollinger_lband(df['close'], window=BOLLINGER_WINDOW)

    # VWAP (using a rolling window, as session-based is complex for historical data)
    # Check if ta.volume.volume_weighted_average_price is available and use it.
    # If not, a basic rolling VWAP. The task specifies aiming for ta.volume.volume_weighted_average_price
    # For now, I will add a placeholder for a rolling window based VWAP.
    # If the ta library used does not have this, we will need to implement a more custom rolling VWAP.
    # Assuming 'ta.volume.volume_weighted_average_price' works as expected with default parameters for a rolling window.
    df['VWAP'] = ta.volume.volume_weighted_average_price(df['high'], df['low'], df['close'], df['volume'], window=VWAP_WINDOW)

    # OBV (On-Balance Volume)
    df['OBV'] = ta.volume.on_balance_volume(df['close'], df['volume'])

    return df

def generate_signals():
    """Generates trading signals based on the provided strategy and prints a message."""
    symbol = 'BTCUSDT'

    last_sent_signal = read_last_signal()
    current_signal_type = "No Signal" # Default to No Signal

    try:
        df_15m = fetch_klines(symbol, '15m', limit=KLINES_LIMIT_15M + 1, exclude_current=True)
        df_1h = fetch_klines(symbol, '1h', limit=KLINES_LIMIT_1H + 1, exclude_current=True)
        df_4h = fetch_klines(symbol, '4h', limit=KLINES_LIMIT_4H + 1, exclude_current=True)
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

    # Define all long conditions as functions
    long_conditions = [
        lambda row, df_m: row['close_4h'] > row['MA_20_4h'], # Condition 1: 4h Close above MA_20
        lambda row, df_m: row['MA_9_4h'] > row['MA_20_4h'], # Condition 2: 4h MA_9 above MA_20
        lambda row, df_m: row['MACD_Hist_4h'] > 0, # Condition 3: 4h MACD Histogram positive
        lambda row, df_m: row['MACD_4h'] > row['MACD_Signal_4h'], # Condition 4: 4h MACD above Signal Line
        lambda row, df_m: row['close_1h'] > row['Ichimoku_A_1h'] and row['close_1h'] > row['Ichimoku_B_1h'], # Condition 5: 1h Close above Ichimoku Cloud
        lambda row, df_m: row['close_4h'] > row['Ichimoku_A_4h'] and row['close_4h'] > row['Ichimoku_B_4h'], # Condition 6: 4h Close above Ichimoku Cloud
        lambda row, df_m: row['Ichimoku_Conversion_Line_4h'] > row['Ichimoku_Base_Line_4h'], # Condition 7: 4h Ichimoku Conversion Line above Base Line
        lambda row, df_m: 30 <= row['RSI'] <= 50, # RSI Confirmation: 30 <= latest_row['RSI'] <= 50
        lambda row, df_m: row['close'] > row['BB_Middle'] or (row['low'] <= row['BB_Lower'] and row['close'] > row['BB_Lower']), # Bollinger Band Support/Bounce
        lambda row, df_m: row['close'] > row['VWAP'], # VWAP Support/Trend
        lambda row, df_m: not df_m.empty and len(df_m) >= 2 and row['OBV'] > df_m.iloc[-2]['OBV'] # OBV Trend Confirmation
    ]

    long_conditions_met_count = _evaluate_conditions(latest_row, df_merged, long_conditions)

    if long_conditions_met_count >= 4: # Require at least 4 out of 7 conditions for LONG
        current_signal_type = "LONG 🚀"

    # Evaluate conditions for SHORT signal based on the new inclusive logic
    if current_signal_type == "No Signal": # Only check for SHORT if LONG wasn\'t found
        short_conditions = [
            lambda row, df_m: row['close_4h'] < row['MA_20_4h'], # Condition 1: 4h Close below MA_20
            lambda row, df_m: row['MA_9_4h'] < row['MA_20_4h'], # Condition 2: 4h MA_9 below MA_20
            lambda row, df_m: row['MACD_Hist_4h'] < 0, # Condition 3: 4h MACD Histogram negative
            lambda row, df_m: row['MACD_4h'] < row['MACD_Signal_4h'], # Condition 4: 4h MACD below Signal Line
            lambda row, df_m: row['close_1h'] < row['Ichimoku_A_1h'] and row['close_1h'] < row['Ichimoku_B_1h'], # Condition 5: 1h Close below Ichimoku Cloud
            lambda row, df_m: row['close_4h'] < row['Ichimoku_A_4h'] and row['close_4h'] < row['Ichimoku_B_4h'], # Condition 6: 4h Close below Ichimoku Cloud
            lambda row, df_m: row['Ichimoku_Conversion_Line_4h'] < row['Ichimoku_Base_Line_4h'], # Condition 7: 4h Ichimoku Conversion Line below Base Line
            lambda row, df_m: 50 <= row['RSI'] <= 70, # RSI Confirmation: 50 <= latest_row['RSI'] <= 70
            lambda row, df_m: row['close'] < row['BB_Middle'] or (row['high'] >= row['BB_Upper'] and row['close'] < row['BB_Upper']), # Bollinger Band Resistance/Rejection
            lambda row, df_m: row['close'] < row['VWAP'], # VWAP Resistance/Trend
            lambda row, df_m: not df_m.empty and len(df_m) >= 2 and row['OBV'] < df_m.iloc[-2]['OBV'] # OBV Trend Confirmation
        ]

        short_conditions_met_count = _evaluate_conditions(latest_row, df_merged, short_conditions)

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