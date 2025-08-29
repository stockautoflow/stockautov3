import os

# ==============================================================================
# ファイル: create_rakuten.py
# 実行方法: python create_rakuten.py
# Ver. 00-03
# 変更点:
#   - src/realtrade/rakuten/rakuten_data.py (_populate_lines):
#     - self.last_dt の設定を `pd.to_datetime(row.name).to_pydatetime()` に
#       変更し、タイムスタンプの型が`pandas.Timestamp`でも`datetime.datetime`
#       でもエラーにならないように堅牢化。
# ==============================================================================

project_files = {
    "src/realtrade/bridge/__init__.py": """
""",

    "src/realtrade/bridge/excel_bridge.py": """import xlwings as xw
import threading
import time
import logging
import pythoncom

logger = logging.getLogger(__name__)

class ExcelBridge:
    def __init__(self, workbook_path: str):
        self.workbook_path = workbook_path
        self.latest_data = {}
        self.lock = threading.Lock()
        self.is_running = False
        self.data_thread = None

    def start(self):
        if self.is_running:
            logger.warning("データリスナーは既に実行中です。")
            return
            
        self.is_running = True
        self.data_thread = threading.Thread(target=self._data_loop, daemon=True)
        self.data_thread.start()
        logger.info("Excelデータリスナースレッドを開始しました。")

    def stop(self):
        self.is_running = False
        if self.data_thread and self.data_thread.is_alive():
            self.data_thread.join(timeout=5)
        logger.info("Excelデータリスナースレッドを停止しました。")

    def _data_loop(self):
        pythoncom.CoInitialize()
        book = None
        data_sheet = None
        POLLING_INTERVAL = 0.5

        try:
            try:
                book = xw.Book(self.workbook_path)
                data_sheet = book.sheets['リアルタイムデータ']
                logger.info("データ監視スレッドがExcelへの接続を確立しました。")
            except Exception as e:
                logger.critical(f"データ監視スレッドがExcelに接続できませんでした: {e}")
                return

            while self.is_running:
                try:
                    market_data_range = data_sheet.range('A2:F10').value
                    cash_value = data_sheet.range('B11').value

                    with self.lock:
                        for row in market_data_range:
                            symbol = row[0]
                            if symbol is not None:
                                symbol_str = str(int(symbol))
                                self.latest_data[symbol_str] = {
                                    'close': row[1], 'open': row[2],
                                    'high': row[3], 'low': row[4],
                                    'volume': row[5]
                                }
                        
                        self.latest_data['account'] = {'cash': cash_value}

                except Exception as e:
                    logger.error(f"Excelからのデータ読み取り中にエラーが発生しました: {e}")
                    self.is_running = False
                    break
                
                time.sleep(POLLING_INTERVAL)
        finally:
            pythoncom.CoUninitialize()
            logger.info("データ監視スレッドがCOMライブラリを解放しました。")

    def get_latest_data(self, symbol: str) -> dict:
        with self.lock:
            return self.latest_data.get(str(symbol), {}).copy()

    def get_cash(self) -> float:
        with self.lock:
            return self.latest_data.get('account', {}).get('cash', 0.0)

    def place_order(self, symbol, side, qty, order_type, price):
        logger.info(f"【手動発注モード】注文シグナル発生: {side} {symbol} {qty}株")
        logger.info("自動発注は行われません。手動で発注してください。")
        return {"status": "MANUAL_MODE", "order_id": None}""",

    "src/realtrade/rakuten/__init__.py": """
""",

    "src/realtrade/rakuten/rakuten_data.py": """import backtrader as bt
from datetime import datetime, timedelta
import logging
import pandas as pd
import threading

logger = logging.getLogger(__name__)

class RakutenData(bt.feeds.PandasData):
    
    params = (
        ('bridge', None),
        ('symbol', None),
        ('timeframe', bt.TimeFrame.Minutes),
        ('heartbeat', 1.0),
    )

    def __init__(self):
        self._hist_df = self.p.dataname
        
        empty_df = pd.DataFrame(
            columns=['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']
        )
        empty_df = empty_df.set_index('datetime')
        self.p.dataname = empty_df
        
        super(RakutenData, self).__init__()
        
        if self.p.bridge is None:
            raise ValueError("ExcelBridgeインスタンスが 'bridge' パラメータとして渡されていません。")
        if self.p.symbol is None:
            raise ValueError("銘柄コードが 'symbol' パラメータとして渡されていません。")
            
        self.bridge = self.p.bridge
        self.symbol = str(self.p.symbol)
        
        self.last_close = None
        self.last_dt = None
        self._stopevent = threading.Event()

    def stop(self):
        self._stopevent.set()

    def _load(self):
        if self._hist_df is not None and not self._hist_df.empty:
            row = self._hist_df.iloc[0]
            self._hist_df = self._hist_df.iloc[1:]
            
            self._populate_lines(row)
            logger.debug(f"[{self.symbol}] 過去データを供給: {row.name}")
            return True

        if self._stopevent.is_set():
            return False

        current_dt = datetime.now()
        if self.last_dt and (current_dt - self.last_dt) < timedelta(seconds=self.p.heartbeat):
            return None
        
        latest_data = self.bridge.get_latest_data(self.symbol)

        if not latest_data or latest_data.get('close') is None or latest_data.get('close') == self.last_close:
            return self._load_heartbeat()

        return self._load_new_bar(latest_data)

    def _load_new_bar(self, data):
        current_dt = datetime.now()
        new_close = data['close']
        
        row = pd.Series({
            'open': data.get('open') if data.get('open') is not None else new_close,
            'high': data.get('high') if data.get('high') is not None else new_close,
            'low': data.get('low') if data.get('low') is not None else new_close,
            'close': new_close,
            'volume': data.get('volume', 0),
            'openinterest': 0
        }, name=current_dt)

        self._populate_lines(row)
        logger.debug(f"[{self.symbol}] 新規バー供給: Close={self.last_close}")
        return True

    def _load_heartbeat(self):
        if self.last_close is None:
            return None
            
        epsilon = 0.0 if self.last_close is None else self.last_close * 0.0001
        
        current_dt = datetime.now()
        row = pd.Series({
            'open': self.last_close,
            'high': self.last_close + epsilon,
            'low': self.last_close,
            'close': self.last_close,
            'volume': 0, 
            'openinterest': 0
        }, name=current_dt)
        
        self._populate_lines(row)
        logger.debug(f"[{self.symbol}] ハートビート供給: Close={self.last_close}")
        return True

    def _populate_lines(self, row):
        self.lines.datetime[0] = self.date2num(row.name)
        self.lines.open[0] = float(row['open'])
        self.lines.high[0] = float(row['high'])
        self.lines.low[0] = float(row['low'])
        self.lines.close[0] = float(row['close'])
        self.lines.volume[0] = float(row.get('volume', 0))
        self.lines.openinterest[0] = float(row.get('openinterest', 0))
        self.last_close = self.lines.close[0]
        self.last_dt = pd.to_datetime(row.name).to_pydatetime()
""",

    "src/realtrade/rakuten/rakuten_broker.py": """
import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class RakutenBroker(bt.brokers.BackBroker):

    def __init__(self, bridge=None, **kwargs):
        super(RakutenBroker, self).__init__(**kwargs)
        if not bridge:
            raise ValueError("ExcelBridgeインスタンスが渡されていません。")
        self.bridge = bridge

    def getcash(self):
        cash = self.bridge.get_cash()
        self.cash = cash if cash is not None else self.cash
        return self.cash

    def buy(self, owner, data, size, price=None, plimit=None, **kwargs):
        logger.info(f"【手動発注モード】買いシグナル発生。自動発注は行いません。")
        order = super().buy(owner, data, size, price, plimit, **kwargs)
        return order

    def sell(self, owner, data, size, price=None, plimit=None, **kwargs):
        logger.info(f"【手動発注モード】売りシグナル発生。自動発注は行いません。")
        order = super().sell(owner, data, size, price, plimit, **kwargs)
        return order

    def cancel(self, order, **kwargs):
        logger.info(f"【手動発注モード】注文キャンセル。")
        return super().cancel(order, **kwargs)
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
    print("--- 楽天証券連携コンポーネントの生成を開始します ---")
    create_files(project_files)
    print("\n楽天証券連携コンポーネントの生成が完了しました。")