# Project File Details

This document outlines the key files and directories within the BTC-Signal project.

## Directories:

-   `data/`: Contains historical market data (`BTCUSDT_*.csv`), raw signal history (`history.json`), processed signals (`processed_signals.json`), and analyzed missed signals (`missed_signals_with_indicators.json`).
-   `logs/`: Stores application logs, such as `send_signals.log`.
-   `scripts/`: Contains various utility scripts for signal analysis and processing.
-   `venv/`: Python virtual environment, containing project dependencies. (Note: This directory is typically excluded from version control).

## Key Files:

-   `scripts/bitcoin_signal_generator.py`: The main script responsible for generating Bitcoin trading signals.
-   `scripts/analyze_missed_signals.py`: Script to analyze signals that were missed by the generator.
-   `scripts/compare_signals.py`: Script for comparing different signal sets or strategies.
-   `scripts/infer_logic.py`: Script to infer the underlying logic of existing signals.
-   `README.md`: Project overview, setup, and usage instructions.
-   `file_details.md`: This file, detailing the project structure.