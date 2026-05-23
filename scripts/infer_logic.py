
import pandas as pd
import json
import ta

def load_data(file_path):
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    # Drop rows with any missing values that might affect indicator calculations
    df = df.dropna()
    return df

def load_signals(file_path):
    with open(file_path, 'r') as f:
        signals = json.load(f)
    df = pd.DataFrame(signals)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def calculate_indicators(df, timeframe_suffix=""):
    # Define all indicator column names that would be created
    indicator_cols = [
        f'MA_9{timeframe_suffix}', f'MA_20{timeframe_suffix}', f'MA_50{timeframe_suffix}', f'MA_200{timeframe_suffix}',
        f'MACD{timeframe_suffix}', f'MACD_Signal{timeframe_suffix}', f'MACD_Hist{timeframe_suffix}',
        f'Ichimoku_Conversion_Line{timeframe_suffix}', f'Ichimoku_Base_Line{timeframe_suffix}',
        f'Ichimoku_A{timeframe_suffix}', f'Ichimoku_B{timeframe_suffix}'
    ]

    # The largest window size is for MA_200, so we need at least 200 periods.
    required_min_periods = 200

    if len(df) < required_min_periods:
        for col in indicator_cols:
            df[col] = pd.NA
        return df

    # Moving Averages
    df[f'MA_9{timeframe_suffix}'] = ta.trend.sma_indicator(df['close'], window=9)
    df[f'MA_20{timeframe_suffix}'] = ta.trend.sma_indicator(df['close'], window=20)
    df[f'MA_50{timeframe_suffix}'] = ta.trend.sma_indicator(df['close'], window=50)
    df[f'MA_200{timeframe_suffix}'] = ta.trend.sma_indicator(df['close'], window=200)

    # MACD
    macd = ta.trend.MACD(df['close'])
    df[f'MACD{timeframe_suffix}'] = macd.macd()
    df[f'MACD_Signal{timeframe_suffix}'] = macd.macd_signal()
    df[f'MACD_Hist{timeframe_suffix}'] = macd.macd_diff()

    # Ichimoku (manual calculation to bypass ta library issues with min_periods)
    # Tenkan-sen (Conversion Line): (Highest High + Lowest Low) / 2 over 9 periods
    df[f'Ichimoku_Conversion_Line{timeframe_suffix}'] = (df['high'].rolling(window=9, min_periods=1).max() +
                                                      df['low'].rolling(window=9, min_periods=1).min()) / 2

    # Kijun-sen (Base Line): (Highest High + Lowest Low) / 2 over 26 periods
    df[f'Ichimoku_Base_Line{timeframe_suffix}'] = (df['high'].rolling(window=26, min_periods=1).max() +
                                                 df['low'].rolling(window=26, min_periods=1).min()) / 2

    # Senkou Span A (Leading Span A): (Conversion Line + Base Line) / 2 plotted 26 periods ahead
    df[f'Ichimoku_A{timeframe_suffix}'] = ((df[f'Ichimoku_Conversion_Line{timeframe_suffix}'] +
                                          df[f'Ichimoku_Base_Line{timeframe_suffix}']) / 2).shift(26)

    # Senkou Span B (Leading Span B): (Highest High + Lowest Low) / 2 over 52 periods, plotted 26 periods ahead
    df[f'Ichimoku_B{timeframe_suffix}'] = ((df['high'].rolling(window=52, min_periods=1).max() +
                                           df['low'].rolling(window=52, min_periods=1).min()) / 2).shift(26)

    # Chikou Span (Lagging Span): Closing price plotted 26 periods behind (not directly used for signal logic, but good to have)
    # df[f'Ichimoku_Lagging_Span{timeframe_suffix}'] = df['close'].shift(-26)

    return df

def infer_logic(signals_df, klines_15m, klines_1h, klines_4h):
    # Calculate indicators for each timeframe
    klines_15m = calculate_indicators(klines_15m, "_15m")
    klines_1h = calculate_indicators(klines_1h, "_1h")
    klines_4h = calculate_indicators(klines_4h, "_4h")

    long_signals_data = []
    short_signals_data = []

    for _, signal in signals_df.iterrows():
        signal_timestamp = signal['timestamp']
        signal_type = signal['signal_type']

        # Find the 15m candle data
        candle_15m_data_match = klines_15m[klines_15m['timestamp'] == signal_timestamp]
        if not candle_15m_data_match.empty:
            candle_15m_data = candle_15m_data_match.iloc[0]
        else:
            previous_candle_15m = klines_15m[klines_15m['timestamp'] < signal_timestamp].sort_values(by='timestamp', ascending=False).head(1)
            if not previous_candle_15m.empty:
                candle_15m_data = previous_candle_15m.iloc[0]
            else:
                continue

        # Find the 1h candle data
        candle_1h_data = klines_1h[(klines_1h['timestamp'] <= signal_timestamp) &
                                  (klines_1h['timestamp'] + pd.Timedelta(hours=1) > signal_timestamp)]
        if not candle_1h_data.empty:
            candle_1h_data = candle_1h_data.iloc[0]
        else:
            continue

        # Find the 4h candle data
        candle_4h_data = klines_4h[(klines_4h['timestamp'] <= signal_timestamp) &
                                  (klines_4h['timestamp'] + pd.Timedelta(hours=4) > signal_timestamp)]
        if not candle_4h_data.empty:
            candle_4h_data = candle_4h_data.iloc[0]
        else:
            continue

        # Combine all relevant data
        combined_data = {
            'timestamp': signal_timestamp,
            'signal_type': signal_type,
            'close_15m': candle_15m_data['close'],
            'MA_9_15m': candle_15m_data['MA_9_15m'],
            'MA_20_15m': candle_15m_data['MA_20_15m'],
            'MA_50_15m': candle_15m_data['MA_50_15m'],
            'MA_200_15m': candle_15m_data['MA_200_15m'],
            'MACD_15m': candle_15m_data['MACD_15m'],
            'MACD_Signal_15m': candle_15m_data['MACD_Signal_15m'],
            'MACD_Hist_15m': candle_15m_data['MACD_Hist_15m'],
            'Ichimoku_Conversion_Line_15m': candle_15m_data['Ichimoku_Conversion_Line_15m'],
            'Ichimoku_Base_Line_15m': candle_15m_data['Ichimoku_Base_Line_15m'],
            'Ichimoku_A_15m': candle_15m_data['Ichimoku_A_15m'],
            'Ichimoku_B_15m': candle_15m_data['Ichimoku_B_15m'],

            'close_1h': candle_1h_data['close'],
            'MA_9_1h': candle_1h_data['MA_9_1h'],
            'MA_20_1h': candle_1h_data['MA_20_1h'],
            'MA_50_1h': candle_1h_data['MA_50_1h'],
            'MA_200_1h': candle_1h_data['MA_200_1h'],
            'MACD_1h': candle_1h_data['MACD_1h'],
            'MACD_Signal_1h': candle_1h_data['MACD_Signal_1h'],
            'MACD_Hist_1h': candle_1h_data['MACD_Hist_1h'],
            'Ichimoku_Conversion_Line_1h': candle_1h_data['Ichimoku_Conversion_Line_1h'],
            'Ichimoku_Base_Line_1h': candle_1h_data['Ichimoku_Base_Line_1h'],
            'Ichimoku_A_1h': candle_1h_data['Ichimoku_A_1h'],
            'Ichimoku_B_1h': candle_1h_data['Ichimoku_B_1h'],

            'close_4h': candle_4h_data['close'],
            'MA_9_4h': candle_4h_data['MA_9_4h'],
            'MA_20_4h': candle_4h_data['MA_20_4h'],
            'MA_50_4h': candle_4h_data['MA_50_4h'],
            'MA_200_4h': candle_4h_data['MA_200_4h'],
            'MACD_4h': candle_4h_data['MACD_4h'],
            'MACD_Signal_4h': candle_4h_data['MACD_Signal_4h'],
            'MACD_Hist_4h': candle_4h_data['MACD_Hist_4h'],
            'Ichimoku_Conversion_Line_4h': candle_4h_data['Ichimoku_Conversion_Line_4h'],
            'Ichimoku_Base_Line_4h': candle_4h_data['Ichimoku_Base_Line_4h'],
            'Ichimoku_A_4h': candle_4h_data['Ichimoku_A_4h'],
            'Ichimoku_B_4h': candle_4h_data['Ichimoku_B_4h'],

        }

        if signal_type == 'LONG':
            long_signals_data.append(combined_data)
        else:
            short_signals_data.append(combined_data)

    long_df = pd.DataFrame(long_signals_data)
    short_df = pd.DataFrame(short_signals_data)

    long_conditions = []
    short_conditions = []

    # Helper to check conditions
    def check_conditions(df, prefix, signal_type):
        conditions = []
        close_col = f'close_{prefix}'
        ma9_col = f'MA_9_{prefix}'
        ma20_col = f'MA_20_{prefix}'
        macd_hist_col = f'MACD_Hist_{prefix}'
        macd_col = f'MACD_{prefix}'
        macd_signal_col = f'MACD_Signal_{prefix}'
        ichimoku_a_col = f'Ichimoku_A_{prefix}'
        ichimoku_b_col = f'Ichimoku_B_{prefix}'
        ichimoku_conversion_col = f'Ichimoku_Conversion_Line_{prefix}'
        ichimoku_base_col = f'Ichimoku_Base_Line_{prefix}'

        # Filter out rows with NaN values in relevant columns before calculating means
        required_cols = [col for col in [close_col, ma9_col, ma20_col, macd_hist_col, macd_col, macd_signal_col,
                                       ichimoku_a_col, ichimoku_b_col, ichimoku_conversion_col, ichimoku_base_col] if col in df.columns]

        df_filtered = df.dropna(subset=required_cols)

        if df_filtered.empty:
            return conditions

        # Apply a threshold for consistency, e.g., > 70% of signals show this condition
        consistency_threshold = 0.7

        if signal_type == 'LONG':
            if ma9_col in df_filtered.columns and (df_filtered[close_col] > df_filtered[ma9_col]).mean() > consistency_threshold: conditions.append(f"Close price is often above MA_9 ({prefix})")
            if ma20_col in df_filtered.columns and (df_filtered[close_col] > df_filtered[ma20_col]).mean() > consistency_threshold: conditions.append(f"Close price is often above MA_20 ({prefix})")
            if ma9_col in df_filtered.columns and ma20_col in df_filtered.columns and (df_filtered[ma9_col] > df_filtered[ma20_col]).mean() > consistency_threshold: conditions.append(f"MA_9 is often above MA_20 ({prefix})")
            if macd_hist_col in df_filtered.columns and (df_filtered[macd_hist_col] > 0).mean() > consistency_threshold: conditions.append(f"MACD Histogram is often positive ({prefix})")
            if macd_col in df_filtered.columns and macd_signal_col in df_filtered.columns and (df_filtered[macd_col] > df_filtered[macd_signal_col]).mean() > consistency_threshold: conditions.append(f"MACD is often above its Signal Line ({prefix})")
            if ichimoku_a_col in df_filtered.columns and ichimoku_b_col in df_filtered.columns and ((df_filtered[close_col] > df_filtered[ichimoku_a_col]) & (df_filtered[close_col] > df_filtered[ichimoku_b_col])).mean() > consistency_threshold: conditions.append(f"Close price is often above the Ichimoku Cloud ({prefix})")
            if ichimoku_conversion_col in df_filtered.columns and ichimoku_base_col in df_filtered.columns and (df_filtered[ichimoku_conversion_col] > df_filtered[ichimoku_base_col]).mean() > consistency_threshold: conditions.append(f"Ichimoku Conversion Line is often above Base Line ({prefix})")
        else: # SHORT
            if ma9_col in df_filtered.columns and (df_filtered[close_col] < df_filtered[ma9_col]).mean() > consistency_threshold: conditions.append(f"Close price is often below MA_9 ({prefix})")
            if ma20_col in df_filtered.columns and (df_filtered[close_col] < df_filtered[ma20_col]).mean() > consistency_threshold: conditions.append(f"Close price is often below MA_20 ({prefix})")
            if ma9_col in df_filtered.columns and ma20_col in df_filtered.columns and (df_filtered[ma9_col] < df_filtered[ma20_col]).mean() > consistency_threshold: conditions.append(f"MA_9 is often below MA_20 ({prefix})")
            if macd_hist_col in df_filtered.columns and (df_filtered[macd_hist_col] < 0).mean() > consistency_threshold: conditions.append(f"MACD Histogram is often negative ({prefix})")
            if macd_col in df_filtered.columns and macd_signal_col in df_filtered.columns and (df_filtered[macd_col] < df_filtered[macd_signal_col]).mean() > consistency_threshold: conditions.append(f"MACD is often below its Signal Line ({prefix})")
            if ichimoku_a_col in df_filtered.columns and ichimoku_b_col in df_filtered.columns and ((df_filtered[close_col] < df_filtered[ichimoku_a_col]) & (df_filtered[close_col] < df_filtered[ichimoku_b_col])).mean() > consistency_threshold: conditions.append(f"Close price is often below the Ichimoku Cloud ({prefix})")
            if ichimoku_conversion_col in df_filtered.columns and ichimoku_base_col in df_filtered.columns and (df_filtered[ichimoku_conversion_col] < df_filtered[ichimoku_base_col]).mean() > consistency_threshold: conditions.append(f"Ichimoku Conversion Line is often below Base Line ({prefix})")
        return conditions

    if not long_df.empty:
        long_conditions.extend(check_conditions(long_df, "15m", 'LONG'))
        long_conditions.extend(check_conditions(long_df, "1h", 'LONG'))
        long_conditions.extend(check_conditions(long_df, "4h", 'LONG'))

    if not short_df.empty:
        short_conditions.extend(check_conditions(short_df, "15m", 'SHORT'))
        short_conditions.extend(check_conditions(short_df, "1h", 'SHORT'))
        short_conditions.extend(check_conditions(short_df, "4h", 'SHORT'))

    return long_conditions, short_conditions

if __name__ == "__main__":
    signals_file = "projects/reverse_engineering_signal/data/processed_signals.json"
    klines_15m_file = "projects/reverse_engineering_signal/data/BTCUSDT_15m_klines.csv"
    klines_1h_file = "projects/reverse_engineering_signal/data/BTCUSDT_1h_klines.csv"
    klines_4h_file = "projects/reverse_engineering_signal/data/BTCUSDT_4h_klines.csv"

    signals_df = load_signals(signals_file)
    klines_15m = load_data(klines_15m_file)
    klines_1h = load_data(klines_1h_file)
    klines_4h = load_data(klines_4h_file)

    long_logic, short_logic = infer_logic(signals_df, klines_15m, klines_1h, klines_4h)

    print("Inferred LONG signal logic:")
    if long_logic:
        for condition in long_logic:
            print(f"- {condition}")
    else:
        print("No clear consistent LONG logic found.")

    print("\nInferred SHORT signal logic:")
    if short_logic:
        for condition in short_logic:
            print(f"- {condition}")
    else:
        print("No clear consistent SHORT logic found.")
