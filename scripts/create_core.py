import os
import sys
import copy
import logging

project_files = {
    "src/core/__init__.py": """
# src/core/__init__.py
# パッケージ内のモジュールをインポート可能にする
from . import strategy
from . import indicators
from . import data_preparer
from . import strategy_initializer
from . import trade_evaluator
from . import order_executor
from . import position_manager
from . import notification_manager
from . import util
""",

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

    "src/core/util/__init__.py": """""",

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
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self._db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
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
        if self.conn:
            self.conn.close()""",

    "src/core/strategy_initializer.py": """import yaml
import copy
import logging
import inspect
import backtrader as bt
from .indicators import SafeStochastic, VWAP, SafeADX

logger = logging.getLogger(__name__)

class StrategyInitializer:
    def __init__(self, strategy_catalog_file, base_strategy_file):
        self.strategy_catalog = self._load_yaml(strategy_catalog_file)
        self.base_strategy_params = self._load_yaml(base_strategy_file)

    def _load_yaml(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"設定ファイル '{filepath}' が見つかりません。")
            return {}
        except Exception as e:
            logger.error(f"'{filepath}' の読み込み中にエラー: {e}")
            return {}
    
    # initializeメソッドを削除し、このクラスは単にYAMLファイルを読み込む役割に限定""",

    "src/core/trade_evaluator.py": """import logging
import backtrader as bt
import inspect

class TradeEvaluator:
    def __init__(self, strategy_params, data_feeds, indicators):
        self.strategy_params = strategy_params
        self.data_feeds = data_feeds
        self.indicators = indicators
        self.logger = logging.getLogger(self.__class__.__name__)
        self.timeframe_map = {
            'short': self.data_feeds['short'],
            'medium': self.data_feeds['medium'],
            'long': self.data_feeds['long'],
        }

    def evaluate_entry_conditions(self):
        # ロジックの複雑さを軽減するために、主要な条件チェックを別のプライベートメソッドに分割
        # Buy/Sell条件のチェックを抽象化
        if self._check_conditions(self.strategy_params.get('entry_conditions', {}).get('long', []), 'long'):
            self.entry_reason = 'long'
            return 'long'
        elif self._check_conditions(self.strategy_params.get('entry_conditions', {}).get('short', []), 'short'):
            self.entry_reason = 'short'
            return 'short'
        return None

    def evaluate_exit_conditions(self, close_price, is_long_position):
        # 損切り・利確条件のチェック
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        
        # 損切り（Stop Loss）チェック
        stop_loss_triggered, sl_reason = self._check_exit_condition(
            exit_conditions.get('stop_loss', {}), close_price, is_long_position)
        if stop_loss_triggered:
            return sl_reason

        # 利確（Take Profit）チェック
        take_profit_triggered, tp_reason = self._check_exit_condition(
            exit_conditions.get('take_profit', {}), close_price, is_long_position)
        if take_profit_triggered:
            return tp_reason
        
        return None

    def _check_conditions(self, conditions, trade_type):
        # 条件リストのAND/OR評価
        for cond in conditions:
            if not self._evaluate_single_condition(cond, trade_type):
                return False
        return True

    def _evaluate_single_condition(self, condition, trade_type):
        cond_type = condition.get('type')
        timeframe = condition.get('timeframe')
        data_feed = self.timeframe_map.get(timeframe)
        
        if not data_feed or len(data_feed) < 2:
            return False
            
        if cond_type == 'crossover':
            ind1_def = condition.get('indicator1')
            ind2_def = condition.get('indicator2')
            
            # `crossover`インジケーターは、クロスした方向を示す値を返す。
            # ロジックは呼び出し元で再構築する必要があるため、ここではキーを返して呼び出し元で解決する。
            return True
        
        return False

    def _check_exit_condition(self, cond, close_price, is_long_position):
        cond_type = cond.get('type')
        
        if cond_type == 'atr_multiple':
            atr_key = self._get_atr_key_for_exit('stop_loss' if 'stop_loss' in cond else 'take_profit')
            atr_ind = self.indicators.get(atr_key)
            if not atr_ind or len(atr_ind) == 0 or atr_ind[0] is None:
                return False, None
            
            atr_val = atr_ind[0]
            multiplier = cond.get('params', {}).get('multiplier', 1.0)
            
            # ロジックは別途実装...
            return False, None
        
        return False, None

    def _get_atr_key_for_exit(self, exit_type):
        
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        cond = exit_conditions.get(exit_type, {})
        if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
            timeframe = cond.get('timeframe')
            if timeframe:
                atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                param_str = "_".join(f"{k}_{v}" for k, v in sorted(atr_params.items()))
                return f"{timeframe}_atr_{param_str}"
        return None""",

    "src/core/order_executor.py": """
import logging
import backtrader as bt
import copy

logger = logging.getLogger(__name__)

class OrderExecutor:
    def __init__(self, strategy_params, data_feeds, indicators):
        self.strategy_params = strategy_params
        self.data_feeds = data_feeds
        self.indicators = indicators

    def place_entry_order(self, strategy, trade_type, entry_reason, risk_per_share):
        if not risk_per_share or risk_per_share <= 1e-9:
            logger.warning("計算されたリスクが0のため、エントリーをスキップします。")
            return None

        entry_price = self.data_feeds['short'].close[0]
        sizing = self.strategy_params.get('sizing', {})
        
        size = min(
            (strategy.broker.getcash() * sizing.get('risk_per_trade', 0.01)) / risk_per_share,
            sizing.get('max_investment_per_trade', 10000000) / entry_price if entry_price > 0 else float('inf')
        )
        
        if size <= 0:
            logger.warning("計算された注文数量が0以下のため、エントリーをスキップします。")
            return None

        is_long = trade_type == 'long'
        
        sl_price = entry_price - risk_per_share if is_long else entry_price + risk_per_share
        
        tp_cond = self.strategy_params.get('exit_conditions', {}).get('take_profit')
        tp_price = 0.0
        if tp_cond:
            tp_key = self._get_atr_key_for_exit('take_profit')
            tp_atr_indicator = self.indicators.get(tp_key)
            if tp_atr_indicator and len(tp_atr_indicator) > 0:
                current_tp_atr_val = tp_atr_indicator[0]
                if current_tp_atr_val and current_tp_atr_val > 1e-9:
                    tp_multiplier = tp_cond.get('params', {}).get('multiplier', 5.0)
                    tp_price = entry_price + current_tp_atr_val * tp_multiplier if is_long else entry_price - current_tp_atr_val * tp_multiplier

        logger.info(f"{'BUY' if is_long else 'SELL'} 注文実行中。数量: {size:.2f}, TP: {tp_price:.2f}, SL: {sl_price:.2f}")

        strategy.entry_reason = entry_reason
        strategy.tp_price = tp_price
        strategy.sl_price = sl_price
        
        return strategy.buy(size=size) if is_long else strategy.sell(size=size)

    def place_exit_orders(self, strategy, live_trading, exit_reason):
        if not strategy.getposition().size: return

        if live_trading:
            logger.info(f"ライブモードで決済実行: {exit_reason}")
            return strategy.close()
        else:
            logger.info(f"バックテストモードで決済実行: {exit_reason}")
            exit_conditions = self.strategy_params.get('exit_conditions', {})
            sl_cond = exit_conditions.get('stop_loss', {}); tp_cond = exit_conditions.get('take_profit', {})
            is_long, size = strategy.getposition().size > 0, abs(strategy.getposition().size)
            limit_order, stop_order = None, None

            if tp_cond and strategy.tp_price != 0:
                limit_order = strategy.sell(exectype=bt.Order.Limit, price=strategy.tp_price, size=size, transmit=False) if is_long else strategy.buy(exectype=bt.Order.Limit, price=strategy.tp_price, size=size, transmit=False)
                logger.info(f"利確(Limit)注文を作成: Price={strategy.tp_price:.2f}")

            if sl_cond and sl_cond.get('type') == 'atr_stoptrail':
                stop_order = strategy.sell(exectype=bt.Order.StopTrail, trailamount=strategy.risk_per_share, size=size, oco=limit_order) if is_long else strategy.buy(exectype=bt.Order.StopTrail, trailamount=strategy.risk_per_share, size=size, oco=limit_order)
                logger.info(f"損切(StopTrail)注文をOCOで発注: TrailAmount={strategy.risk_per_share:.2f}")

            return [o for o in [limit_order, stop_order] if o is not None]

    def _get_atr_key_for_exit(self, exit_type):
        exit_cond = self.strategy_params.get('exit_conditions', {}).get(exit_type)
        if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']:
            return None
        atr_params = {k: v for k, v in exit_cond.get('params', {}).items() if k != 'multiplier'}
        return self._get_indicator_key(exit_cond.get('timeframe', 'short'), 'atr', atr_params)
    
    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"
""",

    "src/core/position_manager.py": """
import logging
from datetime import datetime
import copy

logger = logging.getLogger(__name__)

class PositionManager:
    def __init__(self, strategy_params, data_feeds, indicators):
        self.strategy_params = strategy_params
        self.data_feeds = data_feeds
        self.indicators = indicators
        
    def restore_state(self, strategy, persisted_position):
        pos_info = persisted_position
        size, price = pos_info['size'], pos_info['price']
        
        strategy.position.size = size
        strategy.position.price = price
        strategy.current_position_entry_dt = datetime.fromisoformat(pos_info['entry_datetime'])
        
        self._recalculate_exit_prices(strategy, entry_price=price, is_long=(size > 0))
        logger.info(f"ポジション復元完了。Size: {strategy.position.size}, Price: {strategy.position.price}, SL: {strategy.sl_price:.2f}, TP: {strategy.tp_price:.2f}")

    def _recalculate_exit_prices(self, strategy, entry_price, is_long):
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss')
        tp_cond = exit_conditions.get('take_profit')
        strategy.sl_price, strategy.tp_price, strategy.risk_per_share = 0.0, 0.0, 0.0

        if sl_cond:
            sl_atr_key = self._get_atr_key_for_exit('stop_loss')
            sl_atr_indicator = self.indicators.get(sl_atr_key)
            if sl_atr_indicator and len(sl_atr_indicator) > 0:
                atr_val = sl_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    strategy.risk_per_share = atr_val * sl_cond['params']['multiplier']
                    strategy.sl_price = entry_price - strategy.risk_per_share if is_long else entry_price + strategy.risk_per_share

        if tp_cond:
            tp_atr_key = self._get_atr_key_for_exit('take_profit')
            tp_atr_indicator = self.indicators.get(tp_atr_key)
            if tp_atr_indicator and len(tp_atr_indicator) > 0:
                atr_val = tp_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    strategy.tp_price = entry_price + (atr_val * tp_cond['params']['multiplier']) if is_long else entry_price - (atr_val * tp_cond['params']['multiplier'])

    def _get_atr_key_for_exit(self, exit_type):
        exit_cond = self.strategy_params.get('exit_conditions', {}).get(exit_type)
        if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']:
            return None
        atr_params = {k: v for k, v in exit_cond.get('params', {}).items() if k != 'multiplier'}
        return self._get_indicator_key(exit_cond.get('timeframe', 'short'), 'atr', atr_params)

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"
""",

    "src/core/notification_manager.py": """
import logging
from datetime import datetime, timedelta
from .util import notifier

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, live_trading, notifier_instance):
        self.live_trading = live_trading
        self.notifier = notifier_instance
        self.symbol_str = ""

    def handle_order_notification(self, order, data_feed):
        self.symbol_str = data_feed._name.split('_')[0]
        is_entry = order.info.get('is_entry')
        is_exit = order.info.get('is_exit')
        
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if not is_entry and not is_exit:
            return

        subject = ""
        body = ""
        is_immediate = False

        if order.status == order.Completed:
            if is_entry:
                subject = f"【リアルタイム取引】エントリー注文約定 ({self.symbol_str})"
                body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\\n"
                        f"銘柄: {self.symbol_str}\\n"
                        f"ステータス: {order.getstatusname()}\\n"
                        f"方向: {'BUY' if order.isbuy() else 'SELL'}\\n"
                        f"約定数量: {order.executed.size:.2f}\\n"
                        f"約定価格: {order.executed.price:.2f}")
                is_immediate = True
            elif is_exit:
                pnl = order.executed.pnl
                exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
                subject = f"【リアルタイム取引】決済完了 - {exit_reason} ({self.symbol_str})"
                body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\\n"
                        f"銘柄: {self.symbol_str}\\n"
                        f"ステータス: {order.getstatusname()} ({exit_reason})\\n"
                        f"方向: {'決済BUY' if order.isbuy() else '決済SELL'}\\n"
                        f"決済数量: {order.executed.size:.2f}\\n"
                        f"決済価格: {order.executed.price:.2f}\\n"
                        f"実現損益: {pnl:,.2f}")
                is_immediate = True
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.symbol_str})"
            body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\\n"
                    f"銘柄: {self.symbol_str}\\n"
                    f"ステータス: {order.getstatusname()}\\n"
                    f"詳細: {order.info.get('reason', 'N/A')}")
            is_immediate = True

        if subject and body:
            self._send_notification(subject, body, is_immediate)

    def log_trade_event(self, trade, logger_instance):
        if trade.isopen:
            logger_instance.info(f"トレード開始: {'BUY' if trade.long else 'SELL'}, Size: {trade.size}, Price: {trade.price}")
        elif trade.isclosed:
            logger_instance.info(f"トレード終了: PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")

    def _send_notification(self, subject, body, immediate=False):
        if not self.live_trading:
            return

        bar_datetime = datetime.now()
        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)

        if datetime.now() - bar_datetime > timedelta(minutes=5):
            logger.debug(f"過去データに基づく通知を抑制: {subject} (データ時刻: {bar_datetime})")
            return

        logger.debug(f"通知リクエストを発行: {subject} (Immediate: {immediate})")
        notifier.send_email(subject, body, immediate=immediate)
""",

    "src/core/strategy.py": """import backtrader as bt
import logging
import copy
from datetime import datetime, timedelta

from . import strategy_initializer
from . import trade_evaluator
from . import order_executor
from . import position_manager
from . import notification_manager
from .indicators import SafeStochastic, VWAP, SafeADX
from .util import notifier

class DynamicStrategy(bt.Strategy):
    params = (
        ('strategy_params', None),
        ('strategy_catalog', None),
        ('strategy_assignments', None),
        ('live_trading', False),
        ('persisted_position', None),
    )

    def __init__(self):
        print("DEBUG: DynamicStrategy.__init__を開始")
        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = {}
        self.strategy_params = {}
        self.live_trading = self.p.live_trading
        
        self.initializer = strategy_initializer.StrategyInitializer('config/strategy_catalog.yml', 'config/strategy_base.yml')
        
        symbol_str = self.data0._name.split('_')[0]
        strategy_assignments = self.p.strategy_assignments
        strategy_catalog = self.p.strategy_catalog

        if strategy_assignments is None:
            self.strategy_params = copy.deepcopy(self.initializer.base_strategy_params)
            strategy_name = self.strategy_params['strategy_name']
            self.logger = logging.getLogger(f"{self.__class__.__name__}-{symbol_str}")
            self.logger.info(f"個別バックテストモード: ベース戦略 '{strategy_name}' を使用します。")
        else:
            strategy_name = strategy_assignments.get(str(symbol_str))
            if not strategy_name:
                self.logger.warning(f"銘柄 {symbol_str} に戦略が割り当てられていません。ベース戦略を使用します。")
                self.strategy_params = copy.deepcopy(self.initializer.base_strategy_params)
            else:
                catalog_to_use = strategy_catalog if strategy_catalog is not None else self.initializer.strategy_catalog
                entry_strategy_def = next((item for item in catalog_to_use if item["name"] == strategy_name), None)
                if not entry_strategy_def:
                    self.logger.error(f"エントリー戦略カタログに '{strategy_name}' が見つかりません。ベース戦略を使用します。")
                    self.strategy_params = copy.deepcopy(self.initializer.base_strategy_params)
                else:
                    self.strategy_params = copy.deepcopy(self.initializer.base_strategy_params)
                    self.strategy_params.update(entry_strategy_def)
        
        print("DEBUG: _create_indicatorsを呼び出し")
        self.indicators = self._create_indicators(self.strategy_params)
        
        print("DEBUG: evaluatorを初期化")
        self.evaluator = trade_evaluator.TradeEvaluator(self.strategy_params, self.data_feeds, self.indicators)
        print("DEBUG: executorを初期化")
        self.executor = order_executor.OrderExecutor(self.strategy_params, self.data_feeds, self.indicators)
        print("DEBUG: pos_managerを初期化")
        self.pos_manager = position_manager.PositionManager(self.strategy_params, self.data_feeds, self.indicators)
        print("DEBUG: notif_managerを初期化")
        self.notif_manager = notification_manager.NotificationManager(self.live_trading, notifier)
        
        self.entry_order = None
        self.exit_orders = []
        self.entry_reason = ""
        self.executed_size = 0
        self.risk_per_share = 0.0
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.current_position_entry_dt = None
        self.live_trading_started = False
        
        self.is_restoring = self.p.persisted_position is not None
        print("DEBUG: DynamicStrategy.__init__を完了")

    def _create_indicators(self, strategy_params):
        print("DEBUG: _create_indicatorsを開始")
        indicators, unique_defs = {}, {}
        
        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            params = ind_def.get('params', {})
            param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
            key = f"{timeframe}_{ind_def['name']}_{param_str}"
            if key not in unique_defs: unique_defs[key] = (timeframe, ind_def)

        if isinstance(strategy_params.get('entry_conditions'), dict):
            for cond_list in strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict): continue
                    tf = cond.get('timeframe')
                    if not tf: continue
                    add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                    if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target']['indicator'])

        if isinstance(strategy_params.get('exit_conditions'), dict):
            for exit_type in ['take_profit', 'stop_loss']:
                cond = strategy_params['exit_conditions'].get(exit_type, {})
                if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                    atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                    add_def(cond.get('timeframe'), {'name': 'atr', 'params': atr_params})
        
        backtrader_indicators = {
            'ema': bt.indicators.EMA, 'rsi': bt.indicators.RSI, 'atr': bt.indicators.ATR,
            'macd': bt.indicators.MACD, 'bollingerbands': bt.indicators.BollingerBands,
            'sma': bt.indicators.SMA, 'stochastic': SafeStochastic, 'vwap': VWAP, 'adx': SafeADX
        }
        
        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = backtrader_indicators.get(name.lower())
            
            if ind_cls:
                try:
                    indicators[key] = ind_cls(self.data_feeds[timeframe], plot=False, **params)
                    self.logger.info(f"インジケーターを生成: {name} (Timeframe: {timeframe})")
                except Exception as e:
                    self.logger.error(f"インジケーター '{name}' の生成に失敗しました: {e}")
            else:
                self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        for cond_list in strategy_params.get('entry_conditions', {}).values():
            for cond in cond_list:
                if cond.get('type') in ['crossover', 'crossunder']:
                    ind1_key = self._get_indicator_key(cond['timeframe'], **cond['indicator1'])
                    ind2_key = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    cross_key = f"cross_{ind1_key}_vs_{ind2_key}"
                    if ind1_key in indicators and ind2_key in indicators and cross_key not in indicators:
                        indicators[cross_key] = bt.indicators.CrossOver(indicators[ind1_key], indicators[ind2_key], plot=False)

        print("DEBUG: _create_indicatorsを完了")
        return indicators

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def start(self):
        self.live_trading_started = True

    def notify_order(self, order):
        self.notif_manager.handle_order_notification(order, self.data0)
        
        is_entry = order.info.get('is_entry')
        is_exit = order.info.get('is_exit')
        
        if order.status == order.Completed:
            if is_entry:
                if not self.live_trading:
                    self.exit_orders = self.executor.place_exit_orders(self, self.live_trading, "Backtest")
                
                self.executed_size = order.executed.size
                self.entry_reason_for_trade = self.entry_reason
            
            if is_exit:
                self.sl_price, self.tp_price = 0.0, 0.0

        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            if is_entry:
                self.sl_price, self.tp_price = 0.0, 0.0
        
        if is_entry: self.entry_order = None
        if is_exit: self.exit_orders = []
        
    def notify_trade(self, trade):
        self.notif_manager.log_trade_event(trade, self.logger)
        if trade.isopen:
            self.current_position_entry_dt = self.data.datetime.datetime(0)
            self.executed_size = trade.size
            self.entry_reason_for_trade = self.entry_reason
        elif trade.isclosed:
            trade.executed_size = self.executed_size
            trade.entry_reason_for_trade = self.entry_reason_for_trade
            self.current_position_entry_dt, self.executed_size = None, 0
            self.entry_reason, self.entry_reason_for_trade = "", ""
    
    def next(self):
        if self.logger.isEnabledFor(logging.DEBUG):
            self._log_debug_info()
        
        if len(self.data) == 0 or not self.live_trading_started or self.data.volume[0] == 0:
            return

        if self.is_restoring:
            if not self.evaluator._get_atr_key_for_exit('stop_loss') or len(self.indicators.get(self.evaluator._get_atr_key_for_exit('stop_loss'))) > 0:
                self.pos_manager.restore_state(self, self.p.persisted_position)
                self.is_restoring = False
            else:
                self.logger.info("ポジション復元待機中: インジケーターが未計算です...")
                return

        if self.entry_order or (self.live_trading and self.exit_orders):
            return

        pos_size = self.getposition().size
        if pos_size:
            if self.live_trading:
                exit_reason = self.evaluator.evaluate_exit_conditions(self.data.close[0], pos_size > 0)
                if exit_reason:
                    self.exit_orders.append(self.executor.place_exit_orders(self, self.live_trading, exit_reason))
            return
        
        if not self._check_indicators_ready():
            self.logger.debug("インジケーターが未計算のため、スキップします。")
            return

        trade_type = self.evaluator.evaluate_entry_conditions()
        if not trade_type:
            return

        exit_conditions = self.strategy_params['exit_conditions']
        sl_cond = exit_conditions['stop_loss']
        atr_key = self.evaluator._get_atr_key_for_exit('stop_loss')
        atr_indicator = self.indicators.get(atr_key)
        
        if not atr_indicator or len(atr_indicator) == 0:
            self.logger.debug(f"ATRインジケーター '{atr_key}' が未計算のためスキップします。")
            return
        
        atr_val = atr_indicator[0]
        if not atr_val or atr_val <= 1e-9:
            self.logger.debug(f"ATR値が0のためスキップします。")
            return
        
        self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
        
        self.entry_order = self.executor.place_entry_order(self, trade_type, self.evaluator.entry_reason, self.risk_per_share)
            
    def _check_indicators_ready(self):
        for data_feed in self.data_feeds.values():
            if not len(data_feed) > data_feed.p.plotandlearn:
                return False
        return True

    def _log_debug_info(self):
        log_msg = f"\\n===== Bar Check on {self.data.datetime.datetime(0).isoformat()} =====\\n"
        log_msg += "--- Price Data ---\\n"
        for tf_name, data_feed in self.data_feeds.items():
            if len(data_feed) > 0 and data_feed.close[0] is not None:
                dt = data_feed.datetime.datetime(0)
                log_msg += (f"  [{tf_name.upper():<6}] {dt.isoformat()} | "
                            f"O:{data_feed.open[0]:.2f} H:{data_feed.high[0]:.2f} "
                            f"L:{data_feed.low[0]:.2f} C:{data_feed.close[0]:.2f} "
                            f"V:{data_feed.volume[0]:.0f}\\n")
            else:
                log_msg += f"  [{tf_name.upper():<6}] No data available for this bar\\n"
        log_msg += "--- Indicator Values ---\\n"
        sorted_indicator_keys = sorted(self.indicators.keys())
        for key in sorted_indicator_keys:
            indicator = self.indicators[key]
            if len(indicator) > 0 and indicator[0] is not None:
                values = []
                for line_name in indicator.lines.getlinealiases():
                    line = getattr(indicator.lines, line_name)
                    if len(line) > 0 and line[0] is not None:
                        values.append(f"{line_name}: {line[0]:.4f}")
                if values:
                    log_msg += f"  [{key}]: {', '.join(values)}\\n"
                else:
                    log_msg += f"  [{key}]: Value not ready\\n"
            else:
                log_msg += f"  [{key}]: Not calculated yet\\n"
        self.logger.debug(log_msg)
        
    def log(self, txt, dt=None, level=logging.INFO):
        log_time = dt or self.data.datetime.datetime(0)
        self.logger.log(level, f'{log_time.isoformat()} - {txt}')
        if level >= logging.CRITICAL:
            subject = f"【リアルタイム取引】システム警告 ({self.data0._name})"
            self.notif_manager._send_notification(subject, txt, immediate=False)"""
}





def create_files(files_dict):
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        content = content.strip()
        if content:
            try:
                with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                print(f"  - ファイル作成: {filename}")
            except IOError as e:
                print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- 2. コアモジュールの統合を開始します ---")
    create_files(project_files)
    print("コアモジュールの統合が完了しました。")