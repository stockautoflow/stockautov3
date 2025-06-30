import os
import logging

# ==============================================================================
# --- グローバル設定 ---
# ==============================================================================
# Trueにすると実際の証券会社APIやデータソースに接続します。
# FalseにするとMockDataFetcherを使用し、シミュレーションを実行します。
LIVE_TRADING = True

# ライブトレーディング時のデータソースを選択: 'SBI' または 'YAHOO'
# 'YAHOO' を選択した場合、売買機能はシミュレーション(BackBroker)になります。
DATA_SOURCE = 'YAHOO'

# --- API認証情報 (環境変数からロード) ---
# DATA_SOURCEが'SBI'の場合に利用されます
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

if LIVE_TRADING:
    print(f"<<< ライブモード ({DATA_SOURCE}) で起動します >>>")
    if DATA_SOURCE == 'SBI':
        if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
            raise ValueError("環境変数 'API_KEY' が設定されていません。")
        if not API_SECRET or API_SECRET == "YOUR_API_SECRET_HERE":
            raise ValueError("環境変数 'API_SECRET' が設定されていません。")
else:
    print("<<< シミュレーションモードで起動します (MockDataFetcher使用) >>>")


# ==============================================================================
# --- 取引設定 ---
# ==============================================================================
# 1注文あたりの最大投資額（日本円）
MAX_ORDER_SIZE_JPY = 1000000

# 同時に発注できる最大注文数
MAX_CONCURRENT_ORDERS = 5

# 緊急停止する資産減少率の閾値 (例: -0.1は資産が10%減少したら停止)
EMERGENCY_STOP_THRESHOLD = -0.1

# 取引対象の銘柄と戦略が書かれたファイル名のパターン
RECOMMEND_FILE_PATTERN = "all_recommend_*.csv"


# ==============================================================================
# --- システム設定 ---
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- データベース ---
DB_PATH = os.path.join(BASE_DIR, "realtrade", "db", "realtrade_state.db")

# --- ロギング ---
LOG_LEVEL = logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')

print("設定ファイルをロードしました (config_realtrade.py)")