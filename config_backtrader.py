import os

# --- ディレクトリ設定 ---
# このプロジェクトのルートディレクトリ (例: C:\stockautov3)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_DIR = os.path.join(BASE_DIR, 'backtest_results')

# --- バックテスト設定 ---
INITIAL_CAPITAL = 10000000
# 基準となるCSVファイルの足種（Backtraderが認識できる形式）
# ★★★ 修正点: 先頭を大文字に変更 ★★★
BACKTEST_CSV_BASE_TIMEFRAME_STR = 'Minutes' 
BACKTEST_CSV_BASE_COMPRESSION = 5 # 5分足の場合

# --- メール通知設定 ---
EMAIL_CONFIG = {
    "ENABLED": True,
    "SMTP_SERVER": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "SMTP_USER": "your_email@gmail.com",
    "SMTP_PASSWORD": "your_app_password",
    "RECIPIENT_EMAIL": "recipient_email@example.com"
}

