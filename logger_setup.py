import logging
import os
from datetime import datetime

def setup_logging(config_module, log_prefix):
    """
    バックテストとリアルタイムトレードで共用できる汎用ロガーをセットアップします。
    
    :param config_module: 'config_backtrader' または 'config_realtrade' モジュール
    :param log_prefix: 'backtest' または 'realtime'
    """
    log_dir = config_module.LOG_DIR
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    if log_prefix == 'backtest':
        log_filename = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.log"
    else:
        log_filename = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d')}.log"
    log_filepath = os.path.join(log_dir, log_filename)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=config_module.LOG_LEVEL,
                        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                        handlers=[logging.FileHandler(log_filepath, encoding='utf-8'),
                                  logging.StreamHandler()])
    print(f"ロガーをセットアップしました。モード: {log_prefix}, ログファイル: {log_filepath}")