import json
from collections import defaultdict

def analyze_missed_signals(file_path):
    with open(file_path, 'r') as f:
        missed_signals = json.load(f)

    long_failure_reasons = defaultdict(int)
    short_failure_reasons = defaultdict(int)

    # Replicate the strict ANDed logic from compare_signals.py
    def check_long_conditions_failed(latest_row):
        failed_conditions = []
        
        # Ensure that indicator data is not None before proceeding
        if latest_row is None:
            failed_conditions.append("Indicator data is missing or incomplete.")
            return failed_conditions

        # LONG Signal Strategy (Inferred Logic)
        long_condition_1h_ichimoku_cloud = (latest_row['close_1h'] > latest_row['Ichimoku_A_1h']) and \
                                           (latest_row['close_1h'] > latest_row['Ichimoku_B_1h'])
        if not long_condition_1h_ichimoku_cloud:
            failed_conditions.append("1h Ichimoku Cloud (close not above A and B)")
            
        long_condition_4h_ma20 = latest_row['close_4h'] > latest_row['MA_20_4h']
        if not long_condition_4h_ma20:
            failed_conditions.append("4h MA_20 (close not above MA_20)")
            
        long_condition_4h_ma9_ma20_cross = latest_row['MA_9_4h'] > latest_row['MA_20_4h']
        if not long_condition_4h_ma9_ma20_cross:
            failed_conditions.append("4h MA_9 > MA_20 cross (MA_9 not above MA_20)")
            
        long_condition_4h_ichimoku_cloud = (latest_row['close_4h'] > latest_row['Ichimoku_A_4h']) and \
                                           (latest_row['close_4h'] > latest_row['Ichimoku_B_4h'])
        if not long_condition_4h_ichimoku_cloud:
            failed_conditions.append("4h Ichimoku Cloud (close not above A and B)")
            
        long_condition_4h_ichimoku_conversion_base = latest_row['Ichimoku_Conversion_Line_4h'] > latest_row['Ichimoku_Base_Line_4h']
        if not long_condition_4h_ichimoku_conversion_base:
            failed_conditions.append("4h Ichimoku Conversion Line not above Base Line")
            
        long_condition_4h_macd_hist = latest_row['MACD_Hist_4h'] > 0
        if not long_condition_4h_macd_hist:
            failed_conditions.append("4h MACD Histogram not positive")
            
        long_condition_4h_macd_line = latest_row['MACD_4h'] > latest_row['MACD_Signal_4h']
        if not long_condition_4h_macd_line:
            failed_conditions.append("4h MACD not above Signal Line")
            
        return failed_conditions

    def check_short_conditions_failed(latest_row):
        failed_conditions = []

        # Ensure that indicator data is not None before proceeding
        if latest_row is None:
            failed_conditions.append("Indicator data is missing or incomplete.")
            return failed_conditions
            
        # SHORT Signal Strategy (Inferred Logic)
        short_condition_1h_ichimoku_cloud = (latest_row['close_1h'] < latest_row['Ichimoku_A_1h']) and \
                                            (latest_row['close_1h'] < latest_row['Ichimoku_B_1h'])
        if not short_condition_1h_ichimoku_cloud:
            failed_conditions.append("1h Ichimoku Cloud (close not below A and B)")
            
        short_condition_4h_ma20 = latest_row['close_4h'] < latest_row['MA_20_4h']
        if not short_condition_4h_ma20:
            failed_conditions.append("4h MA_20 (close not below MA_20)")
            
        short_condition_4h_ma9_ma20_cross = latest_row['MA_9_4h'] < latest_row['MA_20_4h']
        if not short_condition_4h_ma9_ma20_cross:
            failed_conditions.append("4h MA_9 < MA_20 cross (MA_9 not below MA_20)")
            
        short_condition_4h_macd_hist = latest_row['MACD_Hist_4h'] < 0
        if not short_condition_4h_macd_hist:
            failed_conditions.append("4h MACD Histogram not negative")
            
        short_condition_4h_macd_line = latest_row['MACD_4h'] < latest_row['MACD_Signal_4h']
        if not short_condition_4h_macd_line:
            failed_conditions.append("4h MACD not below Signal Line")
            
        short_condition_4h_ichimoku_conversion_base = latest_row['Ichimoku_Conversion_Line_4h'] < latest_row['Ichimoku_Base_Line_4h']
        if not short_condition_4h_ichimoku_conversion_base:
            failed_conditions.append("4h Ichimoku Conversion Line not below Base Line")
            
        short_condition_4h_ichimoku_cloud = (latest_row['close_4h'] < latest_row['Ichimoku_A_4h']) and \
                                            (latest_row['close_4h'] < latest_row['Ichimoku_B_4h'])
        if not short_condition_4h_ichimoku_cloud:
            failed_conditions.append("4h Ichimoku Cloud (close not below A and B)")
            
        return failed_conditions


    for signal in missed_signals:
        indicator_data = signal['indicator_data']
        signal_type = signal['telegram_signal']

        if signal_type == 'LONG':
            failures = check_long_conditions_failed(indicator_data)
            for failure in failures:
                long_failure_reasons[failure] += 1
        elif signal_type == 'SHORT':
            failures = check_short_conditions_failed(indicator_data)
            for failure in failures:
                short_failure_reasons[failure] += 1
    
    print("Most frequent failure reasons for missed LONG signals:")
    for reason, count in sorted(long_failure_reasons.items(), key=lambda item: item[1], reverse=True):
        print(f"- {reason}: {count}")

    print("\nMost frequent failure reasons for missed SHORT signals:")
    for reason, count in sorted(short_failure_reasons.items(), key=lambda item: item[1], reverse=True):
        print(f"- {reason}: {count}")

if __name__ == "__main__":
    analyze_missed_signals("/home/ivjiyeonb/missed_signals_with_indicators.json")