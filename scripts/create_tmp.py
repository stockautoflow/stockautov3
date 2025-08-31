import os

# ==============================================================================
# ファイル: create_tmp.py
# 説明: リアルタイム取引のエラーを修正するための、関連ファイル3点の
#       修正後全文を生成します。
# 実行方法: python create_tmp.py
# ==============================================================================

project_files = {
    "src/core/strategy/strategy_orchestrator.py": """
import backtrader as bt
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
        self.position_manager.on_trade_update(trade, self)
""",

    "src/core/strategy/event_handler.py": """
import backtrader as bt

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
            self.logger.log(f"StateManager: ポジションをDBに保存/更新: {symbol} (Size: {position.size})")
""",

    "src/realtrade/run_realtrade.py": """
import logging
import time
import yaml
import pandas as pd
import glob
import os
import sys
import backtrader as bt
import threading
import copy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.core.util import logger as logger_setup
from src.core.util import notifier
from src.core.strategy.strategy_orchestrator import DynamicStrategy
from src.core.data_preparer import prepare_data_feeds
from . import config_realtrade as config
from .state_manager import StateManager

if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'YAHOO':
        from .live.yahoo_store import YahooStore as LiveStore
    elif config.DATA_SOURCE == 'RAKUTEN':
        from .bridge.excel_bridge import ExcelBridge
        from .rakuten.rakuten_data import RakutenData
        from .rakuten.rakuten_broker import RakutenBroker
    else:
        raise ValueError(f"サポートされていないDATA_SOURCEです: {config.DATA_SOURCE}")
else:
    from .mock.data_fetcher import MockDataFetcher

class NoCreditInterest(bt.CommInfoBase):
    \"\"\"
    金利計算を無効にするためのカスタムCommissionInfoクラス。
    get_credit_interestが常に0を返すようにオーバーライドする。
    \"\"\"
    def get_credit_interest(self, data, pos, dt):
        return 0.0

logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.state_manager = StateManager(os.path.join(config.BASE_DIR, "results", "realtrade", "realtrade_state.db"))
        
        self.persisted_positions = self.state_manager.load_positions()
        if self.persisted_positions:
            logger.info(f"DBから{len(self.persisted_positions)}件の既存ポジションを検出しました。")

        self.threads = []
        self.cerebro_instances = []
        
        self.bridge = None
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            if self.bridge is None:
                logger.info("楽天証券(Excelハブ)モードで初期化します。")
                self.bridge = ExcelBridge(workbook_path=config.EXCEL_WORKBOOK_PATH)
                self.bridge.start()

    def _load_yaml(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"設定ファイル '{filepath}' が見つかりません。")
            raise
        
    def _load_strategy_assignments(self, filepath_pattern):
        files = glob.glob(filepath_pattern)
        if not files:
            raise FileNotFoundError(f"銘柄・戦略対応ファイルが見つかりません: {filepath_pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"最新の対応ファイルをロード: {latest_file}")
        df = pd.read_csv(latest_file)
        return pd.Series(df.iloc[:, 0].values, index=df.iloc[:, 1].astype(str)).to_dict()

    def _run_cerebro(self, cerebro_instance):
        try:
            cerebro_instance.run()
        except Exception as e:
            logger.error(f"Cerebroスレッド ({threading.current_thread().name}) でエラーが発生: {e}", exc_info=True)
        finally:
            logger.info(f"Cerebroスレッド ({threading.current_thread().name}) が終了しました。")

    def _create_cerebro_for_symbol(self, symbol):
        strategy_name = self.strategy_assignments.get(str(symbol))
        if not strategy_name:
            logger.warning(f"銘柄 {symbol} に割り当てられた戦略がありません。スキップします。")
            return None
        
        entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
        if not entry_strategy_def:
            logger.warning(f"戦略カタログに '{strategy_name}' が見つかりません。スキップします。")
            return None

        strategy_params = copy.deepcopy(self.base_strategy_params)
        strategy_params.update(entry_strategy_def)
        cerebro = bt.Cerebro(runonce=False)
        
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            if not self.bridge:
                logger.error("ExcelBridgeが初期化されていません。")
                return None
            
            cerebro.setbroker(RakutenBroker(bridge=self.bridge))
            cerebro.broker.set_cash(100_000_000_000)
            cerebro.broker.addcommissioninfo(NoCreditInterest())

            short_tf_config = strategy_params['timeframes']['short']
            compression = short_tf_config['compression']
            search_pattern = os.path.join(config.DATA_DIR, f"{symbol}_{compression}m_*.csv")
            files = glob.glob(search_pattern)

            hist_df = pd.DataFrame()
            if files:
                latest_file = max(files, key=os.path.getctime)
                try:
                    df = pd.read_csv(latest_file, index_col='datetime', parse_dates=True)
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    df.columns = [x.lower() for x in df.columns]
                    hist_df = df
                    logger.info(f"[{symbol}] 過去データとして '{os.path.basename(latest_file)}' ({len(hist_df)}件) を読み込みました。")
                except Exception as e:
                    logger.error(f"[{symbol}] 過去データCSVの読み込みに失敗: {e}")
            else:
                logger.warning(f"[{symbol}] 過去データCSVが見つかりません (パターン: {search_pattern})。リアルタイムデータのみで開始します。")

            primary_data = RakutenData(
                dataname=hist_df,
                bridge=self.bridge,
                symbol=symbol,
                timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']),
                compression=short_tf_config['compression']
            )
            
            cerebro.adddata(primary_data, name=str(symbol))
            logger.info(f"[{symbol}] RakutenData (短期) を追加しました。")

            for tf_name in ['medium', 'long']:
                tf_config = strategy_params['timeframes'].get(tf_name)
                if tf_config:
                    cerebro.resampledata(
                        primary_data,
                        timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                        compression=tf_config['compression'],
                        name=tf_name
                    )
                    logger.info(f"[{symbol}] {tf_name}データをリサンプリングで追加しました。")
        else:
            store = LiveStore() if config.LIVE_TRADING and config.DATA_SOURCE == 'YAHOO' else None
            cerebro.setbroker(bt.brokers.BackBroker())
            cerebro.broker.set_cash(config.INITIAL_CAPITAL)
            cerebro.broker.addcommissioninfo(NoCreditInterest())
            
            success = prepare_data_feeds(cerebro, strategy_params, symbol, config.DATA_DIR,
                                         is_live=config.LIVE_TRADING, live_store=store)
            if not success:
                return None

        symbol_str = str(symbol)
        persisted_position = self.persisted_positions.get(symbol_str)
        if persisted_position:
            logger.info(f"[{symbol_str}] の既存ポジション情報を戦略に渡します: {persisted_position}")

        cerebro.addstrategy(DynamicStrategy,
                            strategy_params=strategy_params,
                            live_trading=config.LIVE_TRADING,
                            persisted_position=persisted_position,
                            state_manager=self.state_manager)
        
        return cerebro

    def start(self):
        logger.info("システムを開始します。")
        if self.bridge:
            self.bridge.start()
            
        for symbol in self.symbols:
            logger.info(f"--- 銘柄 {symbol} のセットアップを開始 ---")
            cerebro_instance = self._create_cerebro_for_symbol(symbol)
            if cerebro_instance:
                self.cerebro_instances.append(cerebro_instance)
                t = threading.Thread(target=self._run_cerebro, args=(cerebro_instance,), name=f"Cerebro-{symbol}", daemon=False)
                self.threads.append(t)
                t.start()
                logger.info(f"Cerebroスレッド (Cerebro-{symbol}) を開始しました。")

    def stop(self):
        logger.info("システムを停止します。全データフィードに停止信号を送信...")
        for cerebro in self.cerebro_instances:
            if cerebro.datas and len(cerebro.datas) > 0 and hasattr(cerebro.datas[0], 'stop'):
                try:
                    cerebro.datas[0].stop()
                except Exception as e:
                    logger.error(f"データフィードの停止中にエラー: {e}")
        
        if self.bridge:
            self.bridge.stop()

        logger.info("全Cerebroスレッドの終了を待機中...")
        for t in self.threads:
            t.join(timeout=10)
        if self.state_manager: self.state_manager.close()
        logger.info("システムが正常に停止しました。")

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime', level=config.LOG_LEVEL)
    notifier.start_notifier()
    logger.info("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        
        while True:
            if not trader.threads or not any(t.is_alive() for t in trader.threads):
                logger.warning("稼働中の取引スレッドがありません。システムを終了します。")
                break
            time.sleep(5)

    except KeyboardInterrupt:
        logger.info("\\nCtrl+Cを検知しました。システムを優雅に停止します。")
    except Exception as e:
        logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if trader:
            trader.stop()
        notifier.stop_notifier()
    logger.info("--- リアルタイムトレードシステム終了 ---")

if __name__ == '__main__':
    main()
"""
}


def create_files(files_dict):
    """
    指定された辞書に基づいてプロジェクトファイルとディレクトリを生成します。
    """
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
    print("--- 修正ファイルを一時的に生成します ---")
    create_files(project_files)
    print("\\nファイルの生成が完了しました。")