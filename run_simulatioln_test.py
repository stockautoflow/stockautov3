import sys
import os
import time
import logging
import random
import glob
import pandas as pd
from datetime import datetime, timedelta
# unittest.mock はメモリリークの原因になるため使用しない

# プロジェクトルートの設定
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.realtrade import run_realtrade
from src.realtrade import config_realtrade as config
from src.realtrade.rakuten.rakuten_data import RakutenData

# ロガー設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [TEST] - %(message)s')
logger = logging.getLogger(__name__)

# === テスト設定 ===
# 仮想的な開始時間: 今日の09:00
START_DT = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)

# 時間加速倍率 (現実の1秒 = シミュレーションの TIME_SCALE 秒)
# 1800倍速 (1秒で30分進む)
TIME_SCALE = 1800 

# テスト開始時の現実時間
real_start_time = None

def get_current_sim_time():
    """現実の経過時間に基づいてシミュレーション時刻を算出する"""
    if real_start_time is None: return START_DT
    elapsed_real = time.time() - real_start_time
    elapsed_sim = elapsed_real * TIME_SCALE
    return START_DT + timedelta(seconds=elapsed_sim)

def mock_is_market_active(now):
    """シミュレーション時間に基づいて市場が開いているか判定"""
    current_sim_time = get_current_sim_time()
    market_close = START_DT.replace(hour=15, minute=30)
    
    is_open = current_sim_time <= market_close
    
    if not is_open:
        # ログ抑制
        if int(time.time()) % 5 == 0:
            logger.info(f"仮想市場ステータス: CLOSED ({current_sim_time.strftime('%H:%M')}) -> 停止プロセスへ")
    
    return is_open

def mock_load(self):
    """
    時間を「現実時間ベース」で進めながらデータを供給する関数
    """
    current_sim_time = get_current_sim_time()
    market_close = START_DT.replace(hour=15, minute=30)

    # 既に市場が閉じていれば何もしない
    if current_sim_time > market_close:
        return None

    # 各銘柄ごとにデータの生成頻度を制御 (現実時間で0.2秒に1回程度)
    if not hasattr(self, '_last_real_time'):
        self._last_real_time = 0
    
    if time.time() - self._last_real_time < 0.2:
        return None

    self._last_real_time = time.time()
    
    # ダミー価格生成
    dummy_price = 1000 + random.random() * 50
    
    # Builderに注入
    completed_bar = self.builder.add_tick(current_sim_time, dummy_price, 500.0)

    if completed_bar:
        # ログ間引き
        if random.random() < 0.05: 
            logger.info(f"[{self.symbol}] ★TIME WARP★ 5分足完成: {completed_bar['timestamp'].strftime('%H:%M')} Price={dummy_price:.0f}")
        
        self._new_bars.append(completed_bar.copy())
        self._populate_lines_from_dict(completed_bar)
        return True
    
    # Heartbeat
    row = {
        'timestamp': current_sim_time, 'open': dummy_price, 'high': dummy_price,
        'low': dummy_price, 'close': dummy_price, 'volume': 0, 'openinterest': 0
    }
    self._populate_lines_from_dict(row, is_heartbeat=True)
    return True

def mock_sleep(seconds):
    """メインループの待機時間を無効化"""
    time.sleep(0.05)

def mock_wait_seconds(now):
    """待機時間を短縮"""
    return 1.0

def run_test():
    global real_start_time
    logger.info("=== 履歴データ保存機能 時間加速テスト(v5: No-Mock版) ===")
    logger.info("unittest.mockを使用せず、直接関数を書き換えてメモリリークを回避します。")
    
    real_start_time = time.time()

    # --- 1. バックアップ ---
    original_is_market_active = run_realtrade.is_market_active
    original_load = RakutenData._load
    original_sleep = run_realtrade.time_module.sleep
    original_get_seconds = run_realtrade.get_seconds_until_next_open

    # --- 2. モンキーパッチ (関数の置き換え) ---
    run_realtrade.is_market_active = mock_is_market_active
    RakutenData._load = mock_load
    run_realtrade.time_module.sleep = mock_sleep
    run_realtrade.get_seconds_until_next_open = mock_wait_seconds

    # 安全のための強制終了タイマー (30秒)
    import threading
    def timeout_killer():
        time.sleep(30)
        logger.warning("テスト時間が超過しました。強制終了します。")
        os._exit(0)
    
    t = threading.Thread(target=timeout_killer, daemon=True)
    t.start()

    try:
        # メイン処理実行
        run_realtrade.main()

    except KeyboardInterrupt:
        logger.info("=== テスト終了シグナルを受信しました ===")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        # --- 3. 復元 (クリーンアップ) ---
        run_realtrade.is_market_active = original_is_market_active
        RakutenData._load = original_load
        run_realtrade.time_module.sleep = original_sleep
        run_realtrade.get_seconds_until_next_open = original_get_seconds
        
    # 結果確認
    check_csv_result()

def check_csv_result():
    logger.info("--- 保存結果の確認 ---")
    files = glob.glob(os.path.join(config.DATA_DIR, f"*.csv"))
    
    if not files:
        logger.error(f"CSVファイルが見つかりません。ディレクトリ: {config.DATA_DIR}")
        return

    found_count = 0
    for f in files:
        mtime = os.path.getmtime(f)
        # 直近1分以内に更新されたか
        is_recent = (time.time() - mtime) < 60
        
        if is_recent:
            found_count += 1
            filename = os.path.basename(f)
            try:
                df = pd.read_csv(f)
                if not df.empty:
                    last_dt_str = df.iloc[-1]['datetime']
                    logger.info(f"✔ 更新確認: {filename} (最終日時: {last_dt_str}, 行数: {len(df)})")
            except:
                pass
        
    if found_count > 0:
        logger.info(f"SUCCESS: {found_count} 個のファイルが正常に更新されました。")
    else:
        logger.error("FAILURE: ファイルの更新が確認できませんでした。")

if __name__ == "__main__":
    run_test()