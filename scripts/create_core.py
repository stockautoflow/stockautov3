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

    "src/core/util/notifier.py": """import smtplib
import yaml
import logging
import queue
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .notification_logger import NotificationLogger

logger = logging.getLogger(__name__)

# --- グローバル変数 ---
_notification_queue = queue.PriorityQueue()
_worker_thread = None
_stop_event = threading.Event()
_smtp_server = None
_email_config = None
_logger_instance = None

def _get_server():
    global _smtp_server, _email_config
    if _email_config is None: _email_config = load_email_config()
    if not _email_config.get("ENABLED"): return None
    if _smtp_server:
        try:
            if _smtp_server.noop()[0] == 250: return _smtp_server
        except smtplib.SMTPServerDisconnected:
            logger.warning("SMTPサーバーとの接続が切断されました。再接続します。")
            _smtp_server = None
    try:
        server_name, server_port = _email_config["SMTP_SERVER"], _email_config["SMTP_PORT"]
        logger.info(f"SMTPサーバーに新規接続します: {server_name}:{server_port}")
        server = smtplib.SMTP(server_name, server_port, timeout=20)
        server.starttls()
        server.login(_email_config["SMTP_USER"], _email_config["SMTP_PASSWORD"])
        _smtp_server = server
        return _smtp_server
    except Exception as e:
        logger.critical(f"SMTPサーバーへの接続/ログイン失敗: {e}", exc_info=True)
        return None

def _email_worker():
    while not _stop_event.is_set():
        try:
            # <<< 変更点 1/3: タイムスタンプも受け取るようにアンパック処理を変更
            priority, timestamp, item = _notification_queue.get(timeout=1)
            if item is None: break

            record_id = item['record_id']
            server = _get_server()
            if not server:
                if _logger_instance:
                    _logger_instance.update_status(record_id, "FAILED", "SMTP Server not available")
                continue
            
            msg = MIMEMultipart()
            msg['From'] = _email_config["SMTP_USER"]
            msg['To'] = _email_config["RECIPIENT_EMAIL"]
            msg['Subject'] = item['subject']
            msg.attach(MIMEText(item['body'], 'plain', 'utf-8'))

            try:
                logger.info(f"メールを送信中... To: {_email_config['RECIPIENT_EMAIL']}")
                server.send_message(msg)
                if _logger_instance: _logger_instance.update_status(record_id, "SUCCESS")
                logger.info("メールを正常に送信しました。")
            except Exception as e:
                if _logger_instance: _logger_instance.update_status(record_id, "FAILED", str(e))
                logger.critical(f"メール送信中にエラー: {e}", exc_info=True)
                global _smtp_server
                _smtp_server = None
            
            time.sleep(0.1 if priority == 0 else 2.0)
        except queue.Empty:
            continue

def start_notifier():
    global _worker_thread, _logger_instance
    if _logger_instance is None:
        db_path = "log/notification_history.db"
        _logger_instance = NotificationLogger(db_path)
        logger.info(f"通知ロガーを初期化しました。DB: {db_path}")
    if _worker_thread is None or not _worker_thread.is_alive():
        _stop_event.clear()
        _worker_thread = threading.Thread(target=_email_worker, daemon=True)
        _worker_thread.start()
        logger.info("メール通知ワーカースレッドを開始しました。")

def stop_notifier():
    global _worker_thread, _smtp_server, _logger_instance
    if _worker_thread and _worker_thread.is_alive():
        logger.info("メール通知ワーカースレッドを停止します...")
        # <<< 変更点 2/3: 停止シグナルの形式をタプルに合わせる
        _notification_queue.put((-1, time.time(), None))
        _worker_thread.join(timeout=10)
    if _smtp_server:
        _smtp_server.quit()
        _smtp_server = None
        logger.info("SMTPサーバーとの接続を閉じました。")
    if _logger_instance:
        _logger_instance.close()
        logger.info("通知ロガーの接続を閉じました。")
    _worker_thread = None
    logger.info("メール通知システムが正常に停止しました。")

def load_email_config():
    global _email_config
    if _email_config is not None: return _email_config
    try:
        with open('config/email_config.yml', 'r', encoding='utf-8') as f:
            _email_config = yaml.safe_load(f)
            return _email_config
    except FileNotFoundError:
        logger.warning("config/email_config.ymlが見つかりません。メール通知は無効になります。")
        return {"ENABLED": False}
    except Exception as e:
        logger.error(f"config/email_config.ymlの読み込みエラー: {e}")
        return {"ENABLED": False}

def send_email(subject, body, immediate=False):
    config = load_email_config()
    if not config.get("ENABLED") or _stop_event.is_set() or _logger_instance is None:
        return

    priority_str = "URGENT" if immediate else "NORMAL"
    priority_val = 0 if immediate else 1

    try:
        record_id = _logger_instance.log_request(
            priority=priority_str,
            recipient=config.get("RECIPIENT_EMAIL", ""),
            subject=subject,
            body=body
        )
        
        # <<< 変更点 3/3: タイムスタンプをキューのタプルに追加
        timestamp = time.time()
        item = {'record_id': record_id, 'subject': subject, 'body': body}
        _notification_queue.put((priority_val, timestamp, item))

    except Exception as e:
        logger.error(f"通知リクエストのロギング/キューイング失敗: {e}", exc_info=True)""",

    "src/core/util/notification_logger.py": """import sqlite3
import threading
from datetime import datetime
import os

class NotificationLogger:
    def __init__(self, db_path: str):
        \"\"\"
        データベースへの接続とテーブルの初期化を行う。
        \"\"\"
        # データベースファイルのディレクトリが存在しない場合は作成
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self._db_path = db_path
        self._lock = threading.Lock() # スレッドセーフな操作のためのロック
        # check_same_thread=False は、複数スレッドからのアクセスを許可するために必要
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        \"\"\"
        通知履歴を保存するテーブルを作成する。
        \"\"\"
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notification_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    recipient TEXT,
                    subject TEXT,
                    body TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT
                )
            ''')
            self.conn.commit()

    def log_request(self, priority: str, recipient: str, subject: str, body: str) -> int:
        \"\"\"
        送信リクエストをDBに記録し、ユニークIDを返す。
        - statusは 'PENDING' として記録される。
        - 戻り値: 作成されたレコードのID (rowid)
        \"\"\"
        sql = '''
            INSERT INTO notification_history (timestamp, priority, recipient, subject, body, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
        '''
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(sql, (timestamp, priority, recipient, subject, body))
            self.conn.commit()
            return cursor.lastrowid

    def update_status(self, record_id: int, status: str, error_message: str = ""):
        \"\"\"
        指定されたIDのレコードのステータスとエラーメッセージを更新する。
        - status: 'SUCCESS' または 'FAILED'
        \"\"\"
        sql = '''
            UPDATE notification_history
            SET status = ?, error_message = ?
            WHERE id = ?
        '''
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(sql, (status, error_message, record_id))
            self.conn.commit()

    def close(self):
        \"\"\"
        データベース接続を閉じる。
        \"\"\"
        if self.conn:
            self.conn.close()
""",

    "src/core/strategy/__init__.py": """
# strategy パッケージ
""",

    "src/core/strategy/strategy_orchestrator.py": """import backtrader as bt
import logging

from .strategy_initializer import StrategyInitializer
from .entry_signal_generator import EntrySignalGenerator
from .exit_signal_generator import ExitSignalGenerator
from .order_manager import OrderManager
from .position_manager import PositionManager
from .event_handler import EventHandler
from .strategy_logger import StrategyLogger
from .strategy_notifier import StrategyNotifier

class DynamicStrategy(bt.Strategy):
    \"\"\"
    司令塔（オーケストレーター）として、各専門コンポーネントを統括し、
    取引のライフサイクルを管理する責務を持つ。
    \"\"\"
    params = (
        ('strategy_params', None),
        ('live_trading', False),
        ('persisted_position', None),
        ('state_manager', None),
    )

    def __init__(self):
        # --- 1. ロガーと通知機能を最優先で初期化 ---
        self.logger = StrategyLogger(self)
        self.notifier = StrategyNotifier(self.p.live_trading, self)

        # --- 2. 各専門コンポーネントを初期化 ---
        self.initializer = StrategyInitializer(self.p.strategy_params)
        self.position_manager = PositionManager(self.p.persisted_position)

        # --- 3. イベントハンドラを初期化し、ロガーと通知機能、StateManagerを渡す ---
        self.event_handler = EventHandler(self, self.logger, self.notifier, self.p.state_manager)

        # --- 4. 依存関係のあるコンポーネントを初期化 ---
        self.order_manager = OrderManager(self, self.p.strategy_params.get('sizing', {}), self.event_handler)
        
        # --- 5. データフィードの辞書を作成 ---
        self.data_feeds = {
            'short': self.datas[0],
            'medium': self.datas[1],
            'long': self.datas[2]
        }
        
        # --- 6. インジケーターを生成 ---
        self.indicators = self.initializer.create_indicators(self.data_feeds)

        # --- 7. シグナル生成器を初期化 ---
        self.entry_signal_generator = EntrySignalGenerator(self.indicators, self.data_feeds)
        self.exit_signal_generator = ExitSignalGenerator(self, self.indicators, self.order_manager)
        
        # --- 8. 状態変数を初期化 ---
        self.entry_order = None
        self.exit_orders = []
        self.live_trading_started = False

    def start(self):
        \"\"\"cerebro.run() 開始時に一度だけ呼び出される\"\"\"
        self.live_trading_started = True

    def next(self):
        \"\"\"データフィードが更新されるたびに呼び出されるメインループ\"\"\"
        self.logger.log_bar_data(self.indicators)

        if not self.live_trading_started or self.datas[0].volume[0] == 0:
            return

        # 永続化されたポジションの復元処理
        if self.position_manager.is_restoring:
            # ATRが計算されるまで待機
            if self.exit_signal_generator.are_indicators_ready():
                self.position_manager.restore_state(self, self.exit_signal_generator)
            else:
                self.logger.log("ポジション復元待機中: インジケーターが未計算です...")
            return

        # 注文執行中の場合は何もしない
        if self.entry_order or (self.p.live_trading and self.exit_orders):
            return

        # ポジションがある場合は決済ロジックを実行
        if self.position:
            self.exit_signal_generator.check_exit_conditions()
        # ポジションがない場合はエントリーロジックを実行
        else:
            trade_type, reason = self.entry_signal_generator.check_entry_signal(self.p.strategy_params)
            if trade_type:
                self.order_manager.place_entry_order(trade_type, reason, self.indicators)

    def notify_order(self, order):
        \"\"\"注文状態の更新をイベントハンドラに委譲する\"\"\"
        self.event_handler.on_order_update(order)

    def notify_trade(self, trade):
        \"\"\"トレード状態の更新をポジションマネージャーに委譲する\"\"\"
        self.position_manager.on_trade_update(trade, self)""",

    "src/core/strategy/strategy_initializer.py": """
import backtrader as bt
import inspect
import logging

# 変更: core パッケージからインポート
from ..indicators import SafeStochastic, VWAP, SafeADX

class StrategyInitializer:
    \"\"\"
    責務：戦略の実行に必要な設定を読み込み、インジケーター群を生成する。
    \"\"\"
    def __init__(self, strategy_params):
        self.strategy_params = strategy_params
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_indicator_key(self, timeframe, name, params):
        \"\"\"インジケーターを一意に識別するためのキーを生成する\"\"\"
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def create_indicators(self, data_feeds):
        \"\"\"設定に基づき、Backtraderのインジケーターオブジェクトを動的に生成する\"\"\"
        indicators, unique_defs = {}, {}

        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            key = self._get_indicator_key(timeframe, **ind_def)
            if key not in unique_defs: unique_defs[key] = (timeframe, ind_def)

        # エントリー条件から必要なインジケーターを収集
        if isinstance(self.strategy_params.get('entry_conditions'), dict):
            for cond_list in self.strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict): continue
                    tf = cond.get('timeframe')
                    if not tf: continue
                    add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                    if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target']['indicator'])
        
        # 決済条件から必要なインジケーターを収集
        if isinstance(self.strategy_params.get('exit_conditions'), dict):
            for exit_type in ['take_profit', 'stop_loss']:
                cond = self.strategy_params['exit_conditions'].get(exit_type, {})
                if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                    atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                    add_def(cond.get('timeframe'), {'name': 'atr', 'params': atr_params})

        # 収集した定義に基づき、インジケーターをインスタンス化
        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = self._find_indicator_class(name)

            if ind_cls:
                self.logger.debug(f"インジケーター作成: {key} using class {ind_cls.__name__}")
                indicators[key] = ind_cls(data_feeds[timeframe], plot=False, **params)
            else:
                self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        # クロスオーバー用のインジケーターを追加
        if isinstance(self.strategy_params.get('entry_conditions'), dict):
            for cond_list in self.strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict) or cond.get('type') not in ['crossover', 'crossunder']: continue
                    k1 = self._get_indicator_key(cond['timeframe'], **cond['indicator1']); k2 = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    if k1 in indicators and k2 in indicators:
                        cross_key = f"cross_{k1}_vs_{k2}"
                        if cross_key not in indicators: indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2], plot=False)
        
        return indicators

    def _find_indicator_class(self, name):
        \"\"\"文字列からBacktraderのインジケータークラスを見つける\"\"\"
        custom_indicators = {'stochastic': SafeStochastic, 'vwap': VWAP, 'adx': SafeADX}
        if name.lower() in custom_indicators:
            return custom_indicators[name.lower()]
        
        for n_cand in [name, name.upper(), name.capitalize(), f"{name.capitalize()}Safe", f"{name.upper()}_Safe"]:
            cls_candidate = getattr(bt.indicators, n_cand, None)
            if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator):
                return cls_candidate
        return None
""",

    "src/core/strategy/entry_signal_generator.py": """
class EntrySignalGenerator:
    \"\"\"
    責務：価格やインジケーターの情報に基づき、新規エントリーのシグナル（買い/売り）を生成する。
    このクラスは状態を持たない（stateless）。
    \"\"\"
    def __init__(self, indicators, data_feeds):
        self.indicators = indicators
        self.data_feeds = data_feeds

    def check_entry_signal(self, strategy_params):
        \"\"\"ロングとショート、両方のエントリー条件をチェックし、シグナルを返す\"\"\"
        trading_mode = strategy_params.get('trading_mode', {})
        
        if trading_mode.get('long_enabled', True):
            is_met, reason = self._check_all_conditions('long', strategy_params)
            if is_met:
                return 'long', reason

        if trading_mode.get('short_enabled', True):
            is_met, reason = self._check_all_conditions('short', strategy_params)
            if is_met:
                return 'short', reason
        
        return None, None

    def _check_all_conditions(self, trade_type, strategy_params):
        \"\"\"指定されたタイプの全エントリー条件が満たされているか評価する\"\"\"
        conditions = strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not conditions:
            return False, ""

        reason_details = []
        all_conditions_met = True
        for c in conditions:
            is_met, reason_str = self._evaluate_condition(c)
            if not is_met:
                all_conditions_met = False
                break
            reason_details.append(reason_str)

        return (all_conditions_met, " / ".join(reason_details)) if all_conditions_met else (False, "")

    def _evaluate_condition(self, cond):
        \"\"\"単一の条件式を評価する\"\"\"
        tf, cond_type = cond['timeframe'], cond.get('type')
        data_feed = self.data_feeds[tf]
        if len(data_feed) == 0:
            return False, ""

        # クロスオーバー/クロスアンダー条件の評価
        if cond_type in ['crossover', 'crossunder']:
            from .strategy_initializer import StrategyInitializer
            si = StrategyInitializer({}) # ヘルパーメソッドのためだけにインスタンス化
            k1 = si._get_indicator_key(tf, **cond['indicator1'])
            k2 = si._get_indicator_key(tf, **cond['indicator2'])
            cross_indicator = self.indicators.get(f"cross_{k1}_vs_{k2}")
            
            if cross_indicator is None or len(cross_indicator) == 0: return False, ""

            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or \\
                     (cross_indicator[0] < 0 and cond_type == 'crossunder')
            
            p1 = ",".join(map(str, cond['indicator1'].get('params', {}).values()))
            p2 = ",".join(map(str, cond['indicator2'].get('params', {}).values()))
            reason = f"{tf[0].upper()}: {cond_type}({cond['indicator1']['name']}({p1}),{cond['indicator2']['name']}({p2})) [{is_met}]"
            return is_met, reason

        # 通常の比較条件の評価
        from .strategy_initializer import StrategyInitializer
        si = StrategyInitializer({}) # ヘルパーメソッドのためだけにインスタンス化
        ind = self.indicators.get(si._get_indicator_key(tf, **cond['indicator']))
        if ind is None or len(ind) == 0: return False, ""

        val, compare, target = ind[0], cond['compare'], cond['target']
        target_type, target_val, target_val_str = target.get('type'), None, ""

        if target_type == 'data':
            target_val = getattr(data_feed, target['value'])[0]
            target_val_str = f"{target['value']} [{target_val:.2f}]"
        elif target_type == 'indicator':
            target_ind = self.indicators.get(si._get_indicator_key(tf, **target['indicator']))
            if target_ind is None or len(target_ind) == 0: return False, ""
            target_val = target_ind[0]
            target_val_str = f"{target['indicator']['name']}(...) [{target_val:.2f}]"
        elif target_type == 'values':
            target_val = target['value']
            target_val_str = f"[{target_val[0]},{target_val[1]}]" if compare == 'between' else f"[{target_val}]"

        if target_val is None: return False, ""

        is_met = False
        if compare == '>': is_met = val > (target_val[0] if isinstance(target_val, list) else target_val)
        elif compare == '<': is_met = val < (target_val[0] if isinstance(target_val, list) else target_val)
        elif compare == 'between': is_met = target_val[0] < val < target_val[1]
        
        params_str = ",".join(map(str, cond['indicator'].get('params', {}).values()))
        reason = f"{tf[0].upper()}: {cond['indicator']['name']}({params_str}) [{val:.2f}] {compare} {target_val_str}"
        return is_met, reason
""",

    "src/core/strategy/exit_signal_generator.py": """
import backtrader as bt

class ExitSignalGenerator:
    \"\"\"
    責務：保有中のポジションに対し、利確や損切りなどの決済シグナルを生成する。
    \"\"\"
    def __init__(self, strategy, indicators, order_manager):
        self.strategy = strategy
        self.indicators = indicators
        self.order_manager = order_manager
        
        # 内部状態として決済価格を保持
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.risk_per_share = 0.0

    def are_indicators_ready(self):
        \"\"\"ポジション復元に必要なATRインジケーターが計算済みか確認\"\"\"
        from .strategy_initializer import StrategyInitializer
        si = StrategyInitializer(self.strategy.p.strategy_params)
        
        sl_cond = self.strategy.p.strategy_params.get('exit_conditions', {}).get('stop_loss', {})
        if not sl_cond: return False
        
        atr_params = {k: v for k, v in sl_cond.get('params', {}).items() if k != 'multiplier'}
        atr_key = si._get_indicator_key(sl_cond.get('timeframe'), 'atr', atr_params)
        
        atr_indicator = self.indicators.get(atr_key)
        return atr_indicator and len(atr_indicator) > 0

    def calculate_and_set_exit_prices(self, entry_price, is_long):
        \"\"\"エントリー価格に基づき、利確・損切り価格を計算して内部に保持する\"\"\"
        from .strategy_initializer import StrategyInitializer
        si = StrategyInitializer(self.strategy.p.strategy_params)
        p = self.strategy.p.strategy_params
        
        exit_conditions = p.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss', {})
        tp_cond = exit_conditions.get('take_profit', {})

        # Stop Loss
        if sl_cond:
            atr_params = {k: v for k, v in sl_cond.get('params', {}).items() if k != 'multiplier'}
            atr_key = si._get_indicator_key(sl_cond.get('timeframe'), 'atr', atr_params)
            atr_val = self.indicators[atr_key][0]
            if atr_val and atr_val > 1e-9:
                self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
                self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share

        # Take Profit
        if tp_cond:
            atr_params = {k: v for k, v in tp_cond.get('params', {}).items() if k != 'multiplier'}
            atr_key = si._get_indicator_key(tp_cond.get('timeframe'), 'atr', atr_params)
            atr_val = self.indicators[atr_key][0]
            if atr_val and atr_val > 1e-9:
                self.tp_price = entry_price + atr_val * tp_cond.get('params', {}).get('multiplier', 5.0) if is_long else entry_price - atr_val * tp_cond.get('params', {}).get('multiplier', 5.0)

    def check_exit_conditions(self):
        \"\"\"ライブ取引かバックテストかに応じて、適切な決済ロジックを呼び出す\"\"\"
        if self.strategy.p.live_trading:
            self._check_live_exit()
        # バックテストのネイティブ注文はOrderManagerが発注済みのため、ここでは何もしない

    def _check_live_exit(self):
        \"\"\"リアルタイム取引での決済条件を監視し、シグナルが出たら注文を出す\"\"\"
        pos = self.strategy.getposition()
        is_long = pos.size > 0
        current_price = self.strategy.datas[0].close[0]
        logger = self.strategy.logger

        # 利確条件
        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            logger.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
            self.order_manager.close_position()
            return

        # 損切り条件
        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                logger.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                self.order_manager.close_position()
                return

            # トレーリングストップの更新
            new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                logger.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                self.sl_price = new_sl_price
""",

    "src/core/strategy/order_manager.py": """
import backtrader as bt

class OrderManager:
    \"\"\"
    責務：生成されたシグナルに基づき、ロットサイズを計算して注文APIを実行する。
    \"\"\"
    def __init__(self, strategy, sizing_params, event_handler):
        self.strategy = strategy
        self.sizing_params = sizing_params
        self.event_handler = event_handler

    def place_entry_order(self, trade_type, reason, indicators):
        \"\"\"エントリー注文のサイズ計算から発注までを行う\"\"\"
        p = self.strategy.p.strategy_params
        exit_signal_generator = self.strategy.exit_signal_generator
        
        # 決済価格の計算（発注前に必要）
        entry_price = self.strategy.datas[0].close[0]
        is_long = trade_type == 'long'
        exit_signal_generator.calculate_and_set_exit_prices(entry_price, is_long)
        
        risk_per_share = exit_signal_generator.risk_per_share
        if risk_per_share < 1e-9:
            self.strategy.logger.log(f"計算されたリスクが0のため、エントリーをスキップ。")
            return

        # 注文サイズの計算
        cash = self.strategy.broker.getcash()
        risk_capital = cash * self.sizing_params.get('risk_per_trade', 0.01)
        max_investment = self.sizing_params.get('max_investment_per_trade', 1e7)
        
        size1 = risk_capital / risk_per_share
        size2 = max_investment / entry_price if entry_price > 0 else float('inf')
        size = min(size1, size2)

        if size <= 0: return

        # エントリー注文の発注
        if is_long:
            self.strategy.entry_order = self.strategy.buy(size=size)
        else:
            self.strategy.entry_order = self.strategy.sell(size=size)
        
        # イベントハンドラに通知
        self.event_handler.on_entry_order_placed(
            trade_type=trade_type, size=size, reason=reason,
            tp_price=exit_signal_generator.tp_price,
            sl_price=exit_signal_generator.sl_price
        )

    def place_backtest_exit_orders(self):
        \"\"\"バックテスト専用のOCO決済注文（利確・損切り）を発注する\"\"\"
        if not self.strategy.position: return
        
        pos = self.strategy.position
        is_long, size = pos.size > 0, abs(pos.size)
        
        exit_signal_generator = self.strategy.exit_signal_generator
        tp_price = exit_signal_generator.tp_price
        risk_per_share = exit_signal_generator.risk_per_share
        
        limit_order, stop_order = None, None

        if tp_price != 0:
            if is_long:
                limit_order = self.strategy.sell(exectype=bt.Order.Limit, price=tp_price, size=size, transmit=False)
            else:
                limit_order = self.strategy.buy(exectype=bt.Order.Limit, price=tp_price, size=size, transmit=False)

        if risk_per_share > 0:
            if is_long:
                stop_order = self.strategy.sell(exectype=bt.Order.StopTrail, trailamount=risk_per_share, size=size, oco=limit_order)
            else:
                stop_order = self.strategy.buy(exectype=bt.Order.StopTrail, trailamount=risk_per_share, size=size, oco=limit_order)

        self.strategy.exit_orders = [o for o in [limit_order, stop_order] if o is not None]

    def close_position(self):
        \"\"\"現在のポジションを決済する注文を発注する\"\"\"
        self.strategy.exit_orders.append(self.strategy.close())
""",

    "src/core/strategy/position_manager.py": """from datetime import datetime

class PositionManager:
    \"\"\"
    責務：現在のポジション情報を保持し、システムの再起動時に状態を復元する。
    \"\"\"
    def __init__(self, persisted_position):
        self.persisted_position = persisted_position
        self.is_restoring = persisted_position is not None
        
        # トレード分析用の情報
        self.current_position_entry_dt = None
        self.entry_reason_for_trade = ""
        self.executed_size = 0

    def restore_state(self, strategy, exit_signal_generator):
        \"\"\"永続化された情報からポジションの状態を復元する\"\"\"
        pos_info = self.persisted_position
        size, price = pos_info['size'], pos_info['price']

        strategy.position.size = size
        strategy.position.price = price
        self.current_position_entry_dt = datetime.fromisoformat(pos_info['entry_datetime'])

        exit_signal_generator.calculate_and_set_exit_prices(entry_price=price, is_long=(size > 0))
        
        strategy.logger.log(
            f"ポジション復元完了。Size: {size}, Price: {price}, "
            f"SL: {exit_signal_generator.sl_price:.2f}, TP: {exit_signal_generator.tp_price:.2f}"
        )
        self.is_restoring = False

    def on_trade_update(self, trade, strategy):
        \"\"\"トレードの開始/終了イベントを処理する\"\"\"
        if trade.isopen:
            strategy.logger.log(f"トレード開始: {'BUY' if trade.long else 'SELL'}, Size: {trade.size}, Price: {trade.price}")
            self.current_position_entry_dt = strategy.data.datetime.datetime(0)
            # エントリー理由はEventHandlerが保持しているものを参照
            self.entry_reason_for_trade = strategy.event_handler.current_entry_reason
            self.executed_size = trade.size
        
        elif trade.isclosed:
            # バックテスト分析用に情報を追加
            trade.executed_size = self.executed_size
            trade.entry_reason_for_trade = self.entry_reason_for_trade
            strategy.logger.log(f"トレード終了: PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")
            self.current_position_entry_dt = None
            self.entry_reason_for_trade = ""
            self.executed_size = 0""",

    "src/core/strategy/event_handler.py": """import backtrader as bt

class EventHandler:
    \"\"\"
    責務：Backtraderからのイベントを解釈し、情報（メッセージ）を整形して、
    ロガーやノーティファイアーに渡す。
    \"\"\"
    def __init__(self, strategy, logger, notifier, state_manager=None):
        self.strategy = strategy
        self.logger = logger
        self.notifier = notifier
        self.state_manager = state_manager
        self.current_entry_reason = "" # notify_tradeで参照するため

    def on_entry_order_placed(self, trade_type, size, reason, tp_price, sl_price):
        \"\"\"エントリー注文が発注された際のログ記録と通知\"\"\"
        self.current_entry_reason = reason
        is_long = trade_type == 'long'
        
        self.logger.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}, TP: {tp_price:.2f}, SL: {sl_price:.2f}")
        
        subject = f"【リアルタイム取引】新規注文発注 ({self.strategy.data0._name})"
        body = (
            f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\\n"
            f"銘柄: {self.strategy.data0._name}\\n"
            f"戦略: {self.strategy.p.strategy_params.get('name', 'N/A')}\\n"
            f"方向: {'BUY' if is_long else 'SELL'}\\n"
            f"数量: {size:.2f}\\n\\n"
            "--- エントリー根拠 ---\\n"
            f"{reason}"
        )
        self.notifier.send(subject, body, immediate=True)

    def on_order_update(self, order):
        \"\"\"注文状態が更新された際のログ記録と通知\"\"\"
        if order.status in [order.Submitted, order.Accepted]:
            return

        is_entry = self.strategy.entry_order and self.strategy.entry_order.ref == order.ref
        is_exit = any(o.ref == order.ref for o in self.strategy.exit_orders)

        if not is_entry and not is_exit:
            return

        if order.status == order.Completed:
            if is_entry:
                self._handle_entry_completion(order)
            elif is_exit:
                self._handle_exit_completion(order)
            
            self._update_trade_persistence(order)
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self._handle_order_failure(order)

        # 注文オブジェクトへの参照をクリア
        if is_entry: self.strategy.entry_order = None
        if is_exit: self.strategy.exit_orders = []

    def _handle_entry_completion(self, order):
        \"\"\"エントリー注文が約定した際の処理\"\"\"
        self.logger.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
        
        subject = f"【リアルタイム取引】エントリー注文約定 ({self.strategy.data0._name})"
        body = (
            f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\\n"
            f"銘柄: {self.strategy.data0._name}\\n"
            f"ステータス: {order.getstatusname()}\\n"
            f"方向: {'BUY' if order.isbuy() else 'SELL'}\\n"
            f"約定数量: {order.executed.size:.2f}\\n"
            f"約定価格: {order.executed.price:.2f}"
        )
        self.notifier.send(subject, body, immediate=True)

        # バックテストの場合は、ここで決済注文を発注
        if not self.strategy.p.live_trading:
            self.strategy.order_manager.place_backtest_exit_orders()
        else:
            # ライブの場合は、決済価格を再計算・設定
            self.strategy.exit_signal_generator.calculate_and_set_exit_prices(
                entry_price=order.executed.price,
                is_long=order.isbuy()
            )
            esg = self.strategy.exit_signal_generator
            self.logger.log(f"ライブモード決済監視開始: TP={esg.tp_price:.2f}, Initial SL={esg.sl_price:.2f}")


    def _handle_exit_completion(self, order):
        \"\"\"決済注文が約定した際の処理\"\"\"
        pnl = order.executed.pnl
        exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
        
        self.logger.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
        
        subject = f"【リアルタイム取引】決済完了 - {exit_reason} ({self.strategy.data0._name})"
        body = (
            f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\\n"
            f"銘柄: {self.strategy.data0._name}\\n"
            f"ステータス: {order.getstatusname()} ({exit_reason})\\n"
            f"決済数量: {order.executed.size:.2f}\\n"
            f"実現損益: {pnl:,.2f}"
        )
        self.notifier.send(subject, body, immediate=True)
        
        # 決済価格をリセット
        esg = self.strategy.exit_signal_generator
        esg.tp_price, esg.sl_price = 0.0, 0.0

    def _handle_order_failure(self, order):
        \"\"\"注文が失敗・キャンセルされた際の処理\"\"\"
        self.logger.log(f"注文失敗/キャンセル: {order.getstatusname()}")

        subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.strategy.data0._name})"
        body = (f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\\n"
                f"銘柄: {self.strategy.data0._name}\\n"
                f"ステータス: {order.getstatusname()}")
        self.notifier.send(subject, body, immediate=True)
        
        # エントリー注文失敗時は決済価格をリセット
        is_entry = self.strategy.entry_order and self.strategy.entry_order.ref == order.ref
        if is_entry:
            esg = self.strategy.exit_signal_generator
            esg.tp_price, esg.sl_price = 0.0, 0.0

    def _update_trade_persistence(self, order):
        \"\"\"
        リアルタイム取引時に、DBへポジションの状態を永続化する。
        (旧 TradePersistenceAnalyzer の役割)
        \"\"\"
        if not self.strategy.p.live_trading or not self.state_manager:
            return

        symbol = order.data._name
        position = self.strategy.broker.getposition(order.data)

        if position.size == 0:
            # ポジションが決済された場合
            self.state_manager.delete_position(symbol)
            self.logger.log(f"StateManager: ポジションをDBから削除: {symbol}")
        else:
            # ポジションが新規作成/変更された場合
            entry_dt = bt.num2date(order.executed.dt).isoformat()
            self.state_manager.save_position(symbol, position.size, position.price, entry_dt)
            self.logger.log(f"StateManager: ポジションをDBに保存/更新: {symbol} (Size: {position.size})")""",

    "src/core/strategy/strategy_logger.py": """import logging

class StrategyLogger:
    \"\"\"
    責務：整形されたメッセージを受け取り、ログファイルに記録する。
    \"\"\"
    def __init__(self, strategy):
        self.strategy = strategy
        # 銘柄ごとにユニークなロガーを取得
        symbol_str = strategy.data0._name.split('_')[0]
        self.logger = logging.getLogger(f"{strategy.__class__.__name__}-{symbol_str}")

    def log(self, txt, dt=None, level=logging.INFO):
        \"\"\"タイムスタンプ付きでメッセージをログに記録する\"\"\"
        log_time = dt or self.strategy.data.datetime.datetime(0)
        self.logger.log(level, f'{log_time.isoformat()} - {txt}')

    def log_bar_data(self, indicators):
        \"\"\"デバッグレベルが有効な場合、全インジケーターの値を記録する\"\"\"
        if not self.logger.isEnabledFor(logging.DEBUG):
            return
            
        log_msg = f"\\\\n===== Bar Check on {self.strategy.data.datetime.datetime(0).isoformat()} =====\\\\n"
        log_msg += "--- Price Data ---\\\\n"
        # 修正点: self.strategy.datas._feedmanaged.items() -> self.strategy.data_feeds.items()
        for tf_name, data_feed in self.strategy.data_feeds.items():
            if len(data_feed) > 0 and data_feed.close[0] is not None:
                dt = data_feed.datetime.datetime(0)
                log_msg += (f"  [{tf_name.upper():<6}] {dt.isoformat()} | "
                            f"O:{data_feed.open[0]:.2f} H:{data_feed.high[0]:.2f} "
                            f"L:{data_feed.low[0]:.2f} C:{data_feed.close[0]:.2f} "
                            f"V:{data_feed.volume[0]:.0f}\\\\n")
            else:
                log_msg += f"  [{tf_name.upper():<6}] No data available for this bar\\\\n"
        
        log_msg += "--- Indicator Values ---\\\\n"
        for key in sorted(indicators.keys()):
            indicator = indicators[key]
            if len(indicator) > 0 and indicator[0] is not None:
                values = [f"{alias}: {getattr(indicator.lines, alias)[0]:.4f}" for alias in indicator.lines.getlinealiases() if len(getattr(indicator.lines, alias)) > 0]
                if values: log_msg += f"  [{key}]: {', '.join(values)}\\\\n"
        
        self.logger.debug(log_msg)""",

    "src/core/strategy/strategy_notifier.py": """
from datetime import datetime, timedelta
import logging
# 変更: core.util から notifier 本体をインポート
from ..util import notifier

class StrategyNotifier:
    \"\"\"
    責務：整形されたメッセージを受け取り、メールなどの手段で外部に通知する。
    \"\"\"
    def __init__(self, live_trading, strategy):
        self.live_trading = live_trading
        self.strategy = strategy
        self.logger = logging.getLogger(self.__class__.__name__)

    def send(self, subject, body, immediate=False):
        \"\"\"通知内容を外部通知システム（メール）に送信する\"\"\"
        if not self.live_trading:
            return

        # データのタイムスタンプが古すぎる場合は通知を抑制
        bar_datetime = self.strategy.data0.datetime.datetime(0)
        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)

        if datetime.now() - bar_datetime > timedelta(minutes=5):
            self.logger.debug(f"過去データに基づく通知を抑制: {subject}")
            return
            
        self.logger.debug(f"通知リクエストを発行: {subject}")
        # グローバルなnotifierを呼び出す
        notifier.send_email(subject, body, immediate=immediate)
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