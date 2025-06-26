import os
import logging

# --- API認証情報 ---
# .envファイルから読み込まれた環境変数を取得します。
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# --- 必須設定の検証 ---
if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
    print("警告: 環境変数 'API_KEY' が設定されていません。")
if not API_SECRET or API_SECRET == "YOUR_API_SECRET_HERE":
    print("警告: 環境変数 'API_SECRET' が設定されていません。")

# --- 銘柄・戦略設定 ---
RECOMMEND_FILE_PATTERN = "all_recommend_*.csv"

# --- 安全装置設定 ---
MAX_ORDER_SIZE_JPY = 1000000
MAX_CONCURRENT_ORDERS = 5
EMERGENCY_STOP_THRESHOLD = -0.1

# --- データベース設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "realtrade", "db", "realtrade_state.db")

print("設定ファイルをロードしました (config_realtrade.py)")