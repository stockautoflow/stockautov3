import os
import logging

# --- ディレクトリ設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_DIR = os.path.join(BASE_DIR, 'backtest_results')
LOG_DIR = os.path.join(BASE_DIR, 'log')

# --- バックテスト設定 ---
INITIAL_CAPITAL = 10000000
BACKTEST_CSV_BASE_TIMEFRAME_STR = 'Minutes' 
BACKTEST_CSV_BASE_COMPRESSION = 5

# --- ロギング設定 ---
LOG_LEVEL = logging.INFO # INFO or DEBUG

# --- メール通知設定 ---
EMAIL_CONFIG = {
    "ENABLED": False, # デフォルトは無効
    "SMTP_SERVER": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "SMTP_USER": "your_email@gmail.com",
    "SMTP_PASSWORD": "your_app_password",
    "RECIPIENT_EMAIL": "recipient_email@example.com"
}

