import pandas as pd
import json
import ta
from datetime import datetime, timedelta
import os

# --- Configuration ---
PROCESSED_SIGNALS_PATH = "projects/reverse_engineering_signal/data/processed_signals.json"
KLINES_DATA_DIR = "projects/reverse_engineering_signal/data/"

# --- Helper Functions (from bitcoin_signal_generator.py, adapted) ---

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
    df['Ichimoku_Conversion_Line'] = (df['high'].rolling(window=9, min_periods=1).max() + \
                                      df['low'].rolling(window=9, min_periods=1).min()) / 2

    df['Ichimoku_Base_Line'] = (df['high'].rolling(window=26, min_periods=1).max() + \
                                 df['low'].rolling(window=26, min_periods=1).min()) / 2

    df['Ichimoku_A'] = ((df['Ichimoku_Conversion_Line'] + \
                                          df['Ichimoku_Base_Line']) / 2).shift(26)

    df['Ichimoku_B'] = ((df['high'].rolling(window=52, min_periods=1).max() + \
                                 df['low'].rolling(window=52, min_periods=1).min()) / 2).shift(26)
    return df

def generate_signal_for_timestamp(df_15m_full, df_1h_full, df_4h_full, target_timestamp):
    """
    Generates a trading signal for a specific target_timestamp based on historical data up to that point.
    target_timestamp should be the close time of the 15m candle.
    """
    
    # Filter data up to the target_timestamp (inclusive for the *close* of the candle)
    # The target_timestamp from processed_signals.json is the *close time* of the 15m candle.
    # So we need data up to this point.
    df_15m = df_15m_full[df_15m_full.index <= target_timestamp].copy()
    df_1h = df_1h_full[df_1h_full.index <= target_timestamp].copy()
    df_4h = df_4h_full[df_4h_full.index <= target_timestamp].copy()
    


    df_15m = calculate_indicators(df_15m)
    df_1h = calculate_indicators(df_1h)
    df_4h = calculate_indicators(df_4h)

    # Merge dataframes using merge_asof for the closest previous timestamp
    # We use the index of the 15m data as the reference point.
    df_merged = pd.merge_asof(df_15m, df_1h.add_suffix('_1h'),
                              left_index=True, right_index=True, direction='backward')
    df_merged = pd.merge_asof(df_merged, df_4h.add_suffix('_4h'),
                              left_index=True, right_index=True, direction='backward')



    if df_merged.empty:
        return "No Signal", None

    # Get the latest row relevant to the target_timestamp
    # This should be the last available candle *before or at* the target_timestamp
    latest_row = df_merged.iloc[-1] 

    # Check if the latest_row's index matches the target_timestamp close time
    # If not, it means there's no 15m candle closing exactly at target_timestamp in our data,
    # or not enough prior data to form indicators.
    # We should only generate a signal if the latest 15m candle *is* the target_timestamp.
    if latest_row.name != target_timestamp:
        return "No Signal", latest_row

    signal_found = False
    generated_signal = ""

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
        generated_signal = "LONG"
        signal_found = True

    # Evaluate conditions for SHORT signal based on the new inclusive logic
    if not signal_found: # Only check for SHORT if LONG wasn't found
        short_conditions_met_count = 0
        # Condition 1: 4h Close below MA_20
        if pd.notna(latest_row['MA_20_4h']) and latest_row['close_4h'] < latest_row['MA_20_4h']:
            short_conditions_met_count += 1
        # Condition 2: 4h MA_9 below MA_20
        if pd.notna(latest_row['MA_9_4h']) and pd.notna(latest_row['MA_20_4h']) and latest_row['MA_9_4h'] < latest_row['MA_20_4h']:
            short_conditions_met_count += 1
        # Condition 3: 4h MACD Histogram negative
        if pd.notna(latest_row['MACD_Hist_4h']) and latest_row['MACD_Hist_4h'] < 0:
            short_conditions_met_count += 1
        # Condition 4: 4h MACD below Signal Line
        if pd.notna(latest_row['MACD_4h']) and pd.notna(latest_row['MACD_Signal_4h']) and latest_row['MACD_4h'] < latest_row['MACD_Signal_4h']:
            short_conditions_met_count += 1
        # Condition 5: 1h Close below Ichimoku Cloud
        if pd.notna(latest_row['Ichimoku_A_1h']) and pd.notna(latest_row['Ichimoku_B_1h']) and (latest_row['close_1h'] < latest_row['Ichimoku_A_1h'] and latest_row['close_1h'] < latest_row['Ichimoku_B_1h']):
            short_conditions_met_count += 1
        # Condition 6: 4h Close below Ichimoku Cloud
        if pd.notna(latest_row['Ichimoku_A_4h']) and pd.notna(latest_row['Ichimoku_B_4h']) and (latest_row['close_4h'] < latest_row['Ichimoku_A_4h'] and latest_row['close_4h'] < latest_row['Ichimoku_B_4h']):
            short_conditions_met_count += 1
        # Condition 7: 4h Ichimoku Conversion Line below Base Line
        if pd.notna(latest_row['Ichimoku_Conversion_Line_4h']) and pd.notna(latest_row['Ichimoku_Base_Line_4h']) and latest_row['Ichimoku_Conversion_Line_4h'] < latest_row['Ichimoku_Base_Line_4h']:
            short_conditions_met_count += 1

        if short_conditions_met_count >= 4: # Require at least 4 out of 7 conditions for SHORT
            generated_signal = "SHORT"
            signal_found = True

    if not signal_found:
        generated_signal = "No Signal"

    return generated_signal, latest_row

# --- Main Logic ---
def main():
    print("Loading historical klines data...")
    df_15m_full = pd.read_csv(os.path.join(KLINES_DATA_DIR, 'BTCUSDT_15m_klines.csv'))
    df_1h_full = pd.read_csv(os.path.join(KLINES_DATA_DIR, 'BTCUSDT_1h_klines.csv'))
    df_4h_full = pd.read_csv(os.path.join(KLINES_DATA_DIR, 'BTCUSDT_4h_klines.csv'))

    df_15m_full['timestamp'] = pd.to_datetime(df_15m_full['timestamp'])
    df_1h_full['timestamp'] = pd.to_datetime(df_1h_full['timestamp'])
    df_4h_full['timestamp'] = pd.to_datetime(df_4h_full['timestamp'])

    # Use 'timestamp' as index which represents the close time of the candle in our context
    df_15m_full = df_15m_full.set_index('timestamp')
    df_1h_full = df_1h_full.set_index('timestamp')
    df_4h_full = df_4h_full.set_index('timestamp')
    
    # Sort dataframes by index to ensure merge_asof works correctly
    df_15m_full = df_15m_full.sort_index()
    df_1h_full = df_1h_full.sort_index()
    df_4h_full = df_4h_full.sort_index()


    print(f"Loading processed signals from {PROCESSED_SIGNALS_PATH}...")
    with open(PROCESSED_SIGNALS_PATH, 'r') as f:
        processed_signals_data = json.load(f)

    telegram_signals = {}
    for entry in processed_signals_data:
        # The 'time' in processed_signals.json is the close time of the 15m candle
        dt_object = datetime.strptime(entry['timestamp'], '%Y-%m-%dT%H:%M:%S')
        telegram_signals[dt_object] = entry['signal_type']

    print(f"Found {len(telegram_signals)} Telegram signals.")

    comparison_results = []
    
    # Sort telegram signals by timestamp to process chronologically
    sorted_telegram_timestamps = sorted(telegram_signals.keys())

    for i, timestamp in enumerate(sorted_telegram_timestamps):
        if i % 100 == 0:
            print(f"Processing signal {i+1}/{len(sorted_telegram_timestamps)} at {timestamp}...")
        
        telegram_signal = telegram_signals[timestamp]
        
        # Generate signal using our logic for this specific timestamp
        our_signal, indicator_data = generate_signal_for_timestamp(df_15m_full, df_1h_full, df_4h_full, timestamp)
        
        comparison_results.append({
            'timestamp': timestamp,
            'telegram_signal': telegram_signal,
            'our_signal': our_signal,
            'indicator_data': indicator_data.to_dict() if indicator_data is not None else None
        })

    # --- Generate Report ---
    total_telegram_signals = len(comparison_results)
    our_generated_signals_count = 0
    matching_long = 0
    matching_short = 0
    telegram_no_signal_our_signal = 0 # Telegram 'No Signal', our logic generated a signal
    telegram_signal_our_no_signal = 0 # Telegram had a signal, our logic generated 'No Signal'
    
    for res in comparison_results:
        if res['our_signal'] != "No Signal":
            our_generated_signals_count += 1

        if res['telegram_signal'] == "LONG" and res['our_signal'] == "LONG":
            matching_long += 1
        elif res['telegram_signal'] == "SHORT" and res['our_signal'] == "SHORT":
            matching_short += 1
        
        if res['telegram_signal'] == "No Signal" and res['our_signal'] != "No Signal":
            telegram_no_signal_our_signal += 1
        elif res['telegram_signal'] != "No Signal" and res['our_signal'] == "No Signal":
            telegram_signal_our_no_signal += 1

    total_matching_signals = matching_long + matching_short
    
    # Calculate overall accuracy/match percentage
    # Considering "No Signal" as a valid match if both are "No Signal" might inflate accuracy
    # Let's define accuracy based on when Telegram actually had a signal.
    
    # Total Telegram signals that were not "No Signal"
    telegram_active_signals = sum(1 for res in comparison_results if res['telegram_signal'] != "No Signal")
    
    accuracy = 0
    if telegram_active_signals > 0:
        accuracy = (total_matching_signals / telegram_active_signals) * 100

    print("\n--- Signal Comparison Report ---")
    print(f"Total Telegram Signals: {total_telegram_signals}")
    print(f"Total Signals Generated by Our Logic (excluding 'No Signal'): {our_generated_signals_count}")
    print(f"Matching LONG Signals: {matching_long}")
    print(f"Matching SHORT Signals: {matching_short}")
    print(f"Total Matching Signals (LONG/SHORT): {total_matching_signals}")
    print(f"Telegram had 'No Signal', Our Logic generated a signal: {telegram_no_signal_our_signal}")
    print(f"Telegram had a Signal, Our Logic generated 'No Signal': {telegram_signal_our_no_signal}")
    print(f"Accuracy (Matching LONG/SHORT out of Telegram's active signals): {accuracy:.2f}%")
    print("--------------------------------\n")

    # Save missed signals for further analysis
    missed_signals_for_analysis = []
    for res in comparison_results:
        if res['telegram_signal'] != "No Signal" and res['our_signal'] == "No Signal":
            missed_signals_for_analysis.append({
                'timestamp': res['timestamp'].isoformat(),
                'telegram_signal': res['telegram_signal'],
                'indicator_data': res['indicator_data']
            })
    
    output_filename = "missed_signals_with_indicators.json"
    with open(output_filename, 'w') as f:
        json.dump(missed_signals_for_analysis, f, indent=4)
    print(f"Saved {len(missed_signals_for_analysis)} missed signals with indicator data to {output_filename}")


if __name__ == '__main__':
    main()