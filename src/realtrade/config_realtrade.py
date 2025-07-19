import os
import logging
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LIVE_TRADING = True
DATA_SOURCE = 'YAHOO'
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
if LIVE_TRADING:
    print(f"<<< ライブモード ({DATA_SOURCE}) で起動します >>>")
    if DATA_SOURCE == 'SBI' and (not API_KEY or "YOUR_API_KEY_HERE" in API_KEY or not API_SECRET or "YOUR_API_SECRET_HERE" in API_SECRET):
        print("警告: SBI設定でAPIキーまたはシークレットが設定されていません。")
else:
    print("<<< シミュレーションモードで起動します (MockDataFetcher使用) >>>")
INITIAL_CAPITAL = 5000000
MAX_CONCURRENT_ORDERS = 5
RECOMMEND_FILE_PATTERN = os.path.join(BASE_DIR, "results", "evaluation", "*", "all_recommend_*.csv")
# ログレベルを logging.DEBUG に変更すると詳細なログが出力されます
LOG_LEVEL = logging.DEBUG # or logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')