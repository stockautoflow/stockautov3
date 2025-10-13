import logging
import os
from datetime import datetime

def setup_logging(log_dir, log_prefix, level=logging.INFO):
    # ▼▼▼【変更箇所】▼▼▼
    # 渡されたレベルがNoneの場合、ロギングをセットアップせずに関数を抜ける
    if level is None:
        # ライブラリ等からの 'No handlers could be found' 警告を抑制するためにNullHandlerを追加
        logging.getLogger().addHandler(logging.NullHandler())
        return
    # ▲▲▲【変更箇所ここまで】▲▲▲

    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    log_filename = f"{log_prefix}_{timestamp}.log"
    file_mode = 'w'
    log_filepath = os.path.join(log_dir, log_filename)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=level,
                        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                        handlers=[logging.FileHandler(log_filepath, mode=file_mode, encoding='utf-8'),
                                  logging.StreamHandler()])
    print(f"ロガーをセットアップしました。モード: {log_prefix}, ログファイル: {log_filepath}, レベル: {logging.getLevelName(level)}")