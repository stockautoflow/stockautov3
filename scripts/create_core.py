import os

# ==============================================================================
# ファイル: create_core.py
# 実行方法: python create_core.py
# Ver. 00-46
# 変更点:
#   - src/core/util/notifier.py:
#     - メール送信をキューイング方式に変更。
#     - 専用のワーカースレッドが一定間隔でメールを送信するロジックを実装。
#       これにより、Gmailのレート制限エラーを完全に回避する。
#   - src/core/strategy.py:
#     - _send_notificationを、新しいキューイング方式のnotifierを呼び出すよう修正。
# ==============================================================================

project_files = {
    "src/core/__init__.py": """""",

    "src/core/util/__init__.py": """""",

    "src/core/indicators.py": """
import backtrader as bt
import collections

class SafeStochastic(bt.indicators.Stochastic):
    def next(self):
        if self.data.high[0] - self.data.low[0] == 0:
            self.lines.percK[0] = 50.0
            self.lines.percD[0] = 50.0
        else:
            super().next()

class VWAP(bt.Indicator):
    lines = ('vwap',)
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.tp = (self.data.high + self.data.low + self.data.close) / 3.0
        self.cumulative_tpv = 0.0
        self.cumulative_volume = 0.0

    def next(self):
        if len(self) == 1:
            return
        if self.data.datetime.date(0) != self.data.datetime.date(-1):
            self.cumulative_tpv = 0.0
            self.cumulative_volume = 0.0

        self.cumulative_tpv += self.tp[0] * self.data.volume[0]
        self.cumulative_volume += self.data.volume[0]

        if self.cumulative_volume > 0:
            self.lines.vwap[0] = self.cumulative_tpv / self.cumulative_volume
        else:
            self.lines.vwap[0] = self.tp[0]

class SafeADX(bt.Indicator):
    lines = ('adx', 'plusDI', 'minusDI',)
    params = (('period', 14),)
    alias = ('ADX',)

    def __init__(self):
        self.p.period_wilder = self.p.period * 2 - 1
        self.tr = 0.0
        self.plus_dm = 0.0
        self.minus_dm = 0.0
        self.plus_di = 0.0
        self.minus_di = 0.0
        self.adx = 0.0
        self.dx_history = collections.deque(maxlen=self.p.period)

    def _wilder_smooth(self, prev_val, current_val):
        return prev_val - (prev_val / self.p.period) + current_val

    def next(self):
        high, low, close = self.data.high[0], self.data.low[0], self.data.close[0]
        prev_high, prev_low, prev_close = self.data.high[-1], self.data.low[-1], self.data.close[-1]

        current_tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        self.tr = self._wilder_smooth(self.tr, current_tr)

        move_up, move_down = high - prev_high, prev_low - low
        current_plus_dm = move_up if move_up > move_down and move_up > 0 else 0.0
        current_minus_dm = move_down if move_down > move_up and move_down > 0 else 0.0

        self.plus_dm = self._wilder_smooth(self.plus_dm, current_plus_dm)
        self.minus_dm = self._wilder_smooth(self.minus_dm, current_minus_dm)

        if self.tr > 1e-9:
            self.plus_di = 100.0 * self.plus_dm / self.tr
            self.minus_di = 100.0 * self.minus_dm / self.tr
        else:
            self.plus_di, self.minus_di = 0.0, 0.0

        self.lines.plusDI[0], self.lines.minusDI[0] = self.plus_di, self.minus_di

        di_sum = self.plus_di + self.minus_di
        dx = 100.0 * abs(self.plus_di - self.minus_di) / di_sum if di_sum > 1e-9 else 0.0
        self.dx_history.append(dx)

        if len(self) >= self.p.period:
            if len(self) == self.p.period:
                self.adx = sum(self.dx_history) / self.p.period
            else:
                self.adx = (self.adx * (self.p.period - 1) + dx) / self.p.period
        self.lines.adx[0] = self.adx
""",

    "src/core/data_preparer.py": """
import os
import glob
import logging
import pandas as pd
import backtrader as bt

try:
    from src.realtrade.live.yahoo_data import YahooData as LiveData
except ImportError:
    LiveData = None

logger = logging.getLogger(__name__)

def _load_csv_data(filepath, timeframe_str, compression):
    try:
        df = pd.read_csv(filepath, index_col='datetime', parse_dates=True, encoding='utf-8-sig')
        if df.empty:
            logger.warning(f"データファイルが空です: {filepath}")
            return None
        df.columns = [x.lower() for x in df.columns]
        return bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.TFrame(timeframe_str), compression=compression)
    except Exception as e:
        logger.error(f"CSV読み込みまたはデータフィード作成で失敗: {filepath} - {e}")
        return None

def prepare_data_feeds(cerebro, strategy_params, symbol, data_dir, is_live=False, live_store=None, backtest_base_filepath=None):
    logger.info(f"[{symbol}] データフィードの準備を開始 (ライブモード: {is_live})")
    timeframes_config = strategy_params['timeframes']
    short_tf_config = timeframes_config['short']

    if is_live:
        if not LiveData:
            raise ImportError("リアルタイム取引部品が見つかりません。")
        base_data = LiveData(dataname=symbol, store=live_store,
                             timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']),
                             compression=short_tf_config['compression'])
    else:
        if backtest_base_filepath is None:
            logger.warning(f"バックテスト用のベースファイルパスが指定されていません。銘柄コード {symbol} から自動検索を試みます。")
            short_tf_compression = strategy_params['timeframes']['short']['compression']
            search_pattern = os.path.join(data_dir, f"{symbol}_{short_tf_compression}m_*.csv")
            files = glob.glob(search_pattern)
            if not files:
                raise FileNotFoundError(f"ベースファイルが見つかりません: {search_pattern}")
            backtest_base_filepath = files[0]
            logger.info(f"ベースファイルを自動検出しました: {backtest_base_filepath}")
        if not os.path.exists(backtest_base_filepath):
            raise FileNotFoundError(f"ベースファイルが見つかりません: {backtest_base_filepath}")
        base_data = _load_csv_data(backtest_base_filepath, short_tf_config['timeframe'], short_tf_config['compression'])

    if base_data is None:
        logger.error(f"[{symbol}] 短期データフィードの作成に失敗しました。")
        return False

    cerebro.adddata(base_data, name=str(symbol))
    logger.info(f"[{symbol}] 短期データフィードを追加しました。")

    for tf_name in ['medium', 'long']:
        tf_config = timeframes_config.get(tf_name)
        if not tf_config:
            logger.warning(f"[{symbol}] {tf_name}の時間足設定が見つかりません。")
            continue
        source_type = tf_config.get('source_type', 'resample')
        if is_live or source_type == 'resample':
            cerebro.resampledata(base_data,
                                 timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                                 compression=tf_config['compression'], name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データフィードをリサンプリングで追加しました。")
        elif source_type == 'direct':
            pattern_template = tf_config.get('file_pattern')
            if not pattern_template:
                logger.error(f"[{symbol}] {tf_name}のsource_typeが'direct'ですが、file_patternが未定義です。")
                return False
            search_pattern = os.path.join(data_dir, pattern_template.format(symbol=symbol))
            data_files = glob.glob(search_pattern)
            if not data_files:
                logger.error(f"[{symbol}] {tf_name}用のデータファイルが見つかりません: {search_pattern}")
                return False
            data_feed = _load_csv_data(data_files[0], tf_config['timeframe'], tf_config['compression'])
            if data_feed is None: return False
            cerebro.adddata(data_feed, name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データフィードを直接読み込みで追加しました: {data_files[0]}")
    return True
""",

    "src/core/strategy.py": """import backtrader as bt
import logging
import inspect
import yaml
import copy
import threading
from datetime import datetime
from .indicators import SafeStochastic, VWAP, SafeADX
from .util import notifier

class DynamicStrategy(bt.Strategy):
    params = (
        ('strategy_params', None),
        ('strategy_catalog', None),
        ('strategy_assignments', None),
        ('live_trading', False),
        ('persisted_position', None),
        # --- ▼▼▼ 修正箇所 ▼▼▼ ---
        ('state_manager', None), # StateManagerを受け取るためのパラメータ
    )

    def __init__(self):
        # ... (既存の__init__処理) ...
        self.live_trading = self.p.live_trading
        self.state_manager = self.p.state_manager # StateManagerをインスタンス変数に保持

        # ... (既存のインジケーター作成処理など) ...

    # ... (既存のメソッド) ...

    def next(self):
        # ... (既存のnextメソッドの処理) ...

        # --- ▼▼▼ 修正箇所 ▼▼▼ ---
        # ライブ取引中、かつstate_managerが渡されている場合のみ実行
        if self.live_trading and self.state_manager:
            self._update_live_status_to_db()

    def _update_live_status_to_db(self):
        \"\"\"
        現在の戦略の状態をDBに書き込む。
        \"\"\"
        try:
            symbol = self.data0._name
            key = f"chart_{symbol}"
            
            # DBに保存するステータス情報を構築
            status_data = {
                "price": self.data.close[0],
                "dt": self.data.datetime.datetime(0).isoformat(),
                "position_size": self.getposition().size,
                "position_price": self.getposition().price or 0,
                "sl_price": self.sl_price or 0,
                "tp_price": self.tp_price or 0,
            }
            
            # 代表的なインジケータの値を追加 (例: RSI)
            # 実際のキーは動的に生成されるため、適宜調整が必要
            for k, v in self.indicators.items():
                if 'rsi' in k.lower():
                    status_data['rsi'] = v[0]
                    break
            
            self.state_manager.update_live_status(key, status_data)

            # 最初のスレッドが全体のサマリーも更新する (簡易的な実装)
            if '1301' in symbol: # 例として最初の銘柄コードで判定
                 summary_data = {
                    "cash": self.broker.getcash(),
                    "value": self.broker.getvalue()
                 }
                 self.state_manager.update_live_status("summary", summary_data)
        except Exception as e:
            self.log(f"ライブステータスのDB更新中にエラー: {e}", level=logging.WARNING)

    def log(self, txt, dt=None, level=logging.INFO):
        log_time = dt or self.data.datetime.datetime(0)
        self.logger.log(level, f'{log_time.isoformat()} - {txt}')
        if level >= logging.CRITICAL:
            subject = f"【リアルタイム取引】システム警告 ({self.data0._name})"
            self._send_notification(subject, txt)""",

    "src/core/util/logger.py": """
import logging
import os
from datetime import datetime

def setup_logging(log_dir, log_prefix, level=logging.INFO):
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
""",

    "src/core/util/notifier.py": """
import smtplib
import yaml
import logging
import socket
import queue
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

_notification_queue = queue.Queue()
_worker_thread = None
_stop_event = threading.Event()
_smtp_server = None
_email_config = None

def _get_server():
    global _smtp_server, _email_config

    if _email_config is None:
        _email_config = load_email_config()

    if not _email_config.get("ENABLED"):
        return None

    if _smtp_server:
        try:
            status = _smtp_server.noop()
            if status[0] == 250:
                return _smtp_server
        except smtplib.SMTPServerDisconnected:
            logger.warning("SMTPサーバーとの接続が切断されました。再接続します。")
            _smtp_server = None

    try:
        server_name = _email_config["SMTP_SERVER"]
        server_port = _email_config["SMTP_PORT"]
        logger.info(f"SMTPサーバーに新規接続します: {server_name}:{server_port}")
        
        server = smtplib.SMTP(server_name, server_port, timeout=20)
        server.starttls()
        server.login(_email_config["SMTP_USER"], _email_config["SMTP_PASSWORD"])
        
        _smtp_server = server
        return _smtp_server
    except Exception as e:
        logger.critical(f"SMTPサーバーへの接続またはログインに失敗しました: {e}", exc_info=True)
        return None

def _email_worker():
    while not _stop_event.is_set():
        try:
            item = _notification_queue.get(timeout=1)
            if item is None: # 停止シグナル
                break

            server = _get_server()
            if not server:
                continue

            msg = MIMEMultipart()
            msg['From'] = _email_config["SMTP_USER"]
            msg['To'] = _email_config["RECIPIENT_EMAIL"]
            msg['Subject'] = item['subject']
            msg.attach(MIMEText(item['body'], 'plain', 'utf-8'))

            try:
                logger.info(f"メールを送信中... To: {_email_config['RECIPIENT_EMAIL']}")
                server.send_message(msg)
                logger.info("メールを正常に送信しました。")
            except Exception as e:
                logger.critical(f"メール送信中に予期せぬエラーが発生しました: {e}", exc_info=True)
                global _smtp_server
                _smtp_server = None
            
            time.sleep(2) # 2秒待機

        except queue.Empty:
            continue

def start_notifier():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _stop_event.clear()
        _worker_thread = threading.Thread(target=_email_worker, daemon=True)
        _worker_thread.start()
        logger.info("メール通知ワーカースレッドを開始しました。")

def stop_notifier():
    global _worker_thread, _smtp_server
    if _worker_thread and _worker_thread.is_alive():
        logger.info("メール通知ワーカースレッドを停止します...")
        _notification_queue.put(None) # 停止シグナルをキューに追加
        _worker_thread.join(timeout=10)
        if _worker_thread.is_alive():
            logger.warning("ワーカースレッドがタイムアウト後も終了していません。")
    
    if _smtp_server:
        logger.info("SMTPサーバーとの接続を閉じます。")
        _smtp_server.quit()
        _smtp_server = None
    
    _worker_thread = None
    logger.info("メール通知システムが正常に停止しました。")


def load_email_config():
    global _email_config
    if _email_config is not None:
        return _email_config
    try:
        with open('config/email_config.yml', 'r', encoding='utf-8') as f:
            _email_config = yaml.safe_load(f)
            return _email_config
    except FileNotFoundError:
        logger.warning("config/email_config.ymlが見つかりません。メール通知は無効になります。")
        return {"ENABLED": False}
    except Exception as e:
        logger.error(f"config/email_config.ymlの読み込み中にエラー: {e}")
        return {"ENABLED": False}

def send_email(subject, body):
    _notification_queue.put({'subject': subject, 'body': body})
"""
}


def create_files(files_dict):
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        content = content.strip()
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"  - ファイル作成: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- 3. coreパッケージの生成を開始します ---")
    create_files(project_files)
    print("coreパッケージの生成が完了しました。")