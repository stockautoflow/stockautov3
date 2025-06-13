import logging
import os
from datetime import datetime
import config_backtrader as config

def setup_logging():
    """
    ロギングの基本設定を行う関数。
    """
    # ログディレクトリが存在しない場合は作成
    if not os.path.exists(config.LOG_DIR):
        os.makedirs(config.LOG_DIR)

    log_filename = f"backtest_{datetime.now().strftime('%Y-%m-%d')}.log"
    log_filepath = os.path.join(config.LOG_DIR, log_filename)

    # ルートロガーを設定
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        handlers=[
            logging.FileHandler(log_filepath, encoding='utf-8'),
            logging.StreamHandler() # コンソールにも出力
        ]
    )

