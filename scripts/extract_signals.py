import json
from datetime import datetime, timedelta

def extract_signals(history_file_path):
    signals = []
    with open(history_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for message in data['messages']:
        if message['type'] == 'message' and 'text' in message:
            text = message['text']
            signal_type = None

            if "매수(롱)" in text:
                signal_type = "LONG"
            elif "매도(숏)" in text:
                signal_type = "SHORT"
            
            if signal_type:
                # Binance klines timestamp refers to the start of the candle.
                # The cron job runs shortly after the candle closes.
                # We want to store the signal with the close time of the candle it corresponds to.
                # Assuming these Telegram signals correspond to a 15-minute candle closing.
                # The 'date' in history.json is the message send time.
                # We'll assume the signal refers to the 15-min candle that *just closed* before the message.
                # So, we need to round down the message time to the nearest 15-minute interval for the candle close.
                
                message_time = datetime.fromisoformat(message['date'])
                
                # Round down to the nearest 15 minutes for the candle close time
                # Example: message at 16:28:37 -> candle close at 16:15:00
                # message at 20:05:31 -> candle close at 20:00:00
                
                # Calculate total minutes from midnight
                total_minutes = message_time.hour * 60 + message_time.minute
                # Round down to nearest 15 minutes
                rounded_minutes = (total_minutes // 15) * 15
                
                # Construct the rounded datetime object (candle close time)
                candle_close_time = message_time.replace(
                    minute=rounded_minutes % 60,
                    hour=(message_time.hour + rounded_minutes // 60) % 24, # Handle hour rollover if rounded_minutes > 59
                    second=0,
                    microsecond=0
                )

                # Adjust for cases where rounding down might result in a time *before* the actual candle close.
                # For example, if message_time is 16:28:37, rounded_minutes is 16:15.
                # The 16:15 candle starts at 16:00 and closes at 16:15.
                # If message_time is e.g., 16:16:00, the candle that closed was 16:15.
                # If message_time is 16:00:01, the candle that closed was 15:45.
                # If message_time.minute is less than 15, it should round to the previous 15-min mark.
                
                # More robust rounding down to nearest 15 minutes
                # This ensures the timestamp corresponds to the *end* of the 15-minute candle.
                # Example: Message at 16:28:37 means the candle closing at 16:15:00 is relevant.
                # Message at 16:00:00 means the candle closing at 15:45:00 is relevant.
                
                # Calculate minutes until next 15-min mark
                minutes_to_subtract = message_time.minute % 15
                if minutes_to_subtract != 0:
                    candle_close_time = message_time.replace(second=0, microsecond=0) - timedelta(minutes=minutes_to_subtract)
                else:
                    # If message is exactly on a 15-min mark (e.g., HH:00, HH:15), assume it refers to the candle that just closed.
                    # E.g., message at 16:00:00 should refer to the 15:45 candle close.
                    # message at 16:15:00 should refer to the 16:00 candle close.
                    candle_close_time = message_time.replace(second=0, microsecond=0) - timedelta(minutes=15)
                
                signals.append({
                    "timestamp": candle_close_time.isoformat(),
                    "signal_type": signal_type
                })
    return signals

if __name__ == "__main__":
    history_file = "projects/reverse_engineering_signal/data/history.json"
    processed_signals_file = "projects/reverse_engineering_signal/data/processed_signals.json"
    
    extracted_signals = extract_signals(history_file)
    
    with open(processed_signals_file, 'w', encoding='utf-8') as f:
        json.dump(extracted_signals, f, indent=4)
    
    print(f"Extracted {len(extracted_signals)} signals and saved to {processed_signals_file}")
