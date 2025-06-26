import os

# --- API認証情報 ---
# セキュリティのため、環境変数から読み込むことを強く推奨します。
# 例: export API_KEY='your_key'
API_KEY = os.getenv("API_KEY", "YOUR_API_KEY_HERE")
API_SECRET = os.getenv("API_SECRET", "YOUR_API_SECRET_HERE")

# --- 銘柄・戦略設定 ---
# 最新のall_recommend_*.csvを自動で検索するためのパターン
RECOMMEND_FILE_PATTERN = "all_recommend_*.csv"

# --- 安全装置設定 ---
# 1注文あたりの最大金額(円)。これを超える注文はブロックされる。
MAX_ORDER_SIZE_JPY = 1000000
# 同時に発注できる最大注文数
MAX_CONCURRENT_ORDERS = 5
# 資産がこの割合(マイナス値)以上に減少したらシステムを緊急停止する
EMERGENCY_STOP_THRESHOLD = -0.1

# --- データベース設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# realtrade/db ディレクトリ内にデータベースファイルを配置
DB_PATH = os.path.join(BASE_DIR, "realtrade", "db", "realtrade_state.db")