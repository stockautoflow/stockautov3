import logging
import os
from datetime import datetime

def setup_logging(log_dir, log_prefix):
    """
    バックテストとリアルタイムトレードで共用できる汎用ロガーをセットアップします。
    
    :param log_dir: ログファイルを保存するディレクトリパス
    :param log_prefix: 'backtest', 'realtime', 'evaluation' などのログ種別
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # [修正] 全てのログファイル名にタイムスタンプを付与し、追記ではなく新規作成(w)モードに統一
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    log_filename = f"{log_prefix}_{timestamp}.log"
    file_mode = 'w'
        
    log_filepath = os.path.join(log_dir, log_filename)
    
    # 既存のハンドラをすべて削除
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                        handlers=[logging.FileHandler(log_filepath, mode=file_mode, encoding='utf-8'),
                                  logging.StreamHandler()])
    print(f"ロガーをセットアップしました。モード: {log_prefix}, ログファイル: {log_filepath}")