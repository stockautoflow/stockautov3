import logging
import os
from datetime import datetime
import config_backtrader as config

def setup_logging():
    if not os.path.exists(config.LOG_DIR): os.makedirs(config.LOG_DIR)
    log_filename = f"backtest_{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.log"
    log_filepath = os.path.join(config.LOG_DIR, log_filename)
    logging.basicConfig(level=config.LOG_LEVEL,
                        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                        handlers=[logging.FileHandler(log_filepath, encoding='utf-8'),
                                  logging.StreamHandler()], force=True)