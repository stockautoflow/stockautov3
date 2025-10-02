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

    "src/realtrade/bridge/excel_connector.py": """import xlwings as xw
import threading
import time
import logging
import pythoncom
import os

from .excel_reader import ExcelReader

logger = logging.getLogger(__name__)

class ExcelConnector:
    \"\"\"
    Excelとの接続、データ取得スレッドの管理、最新データの保持を行うサービス。
    システムの他の部分はこのクラスを介してExcelのデータにアクセスする。
    \"\"\"
    POLLING_INTERVAL = 1.0  # 1秒ごとにExcelをポーリング

    def __init__(self, workbook_path: str):
        if not os.path.isabs(workbook_path):
            self.workbook_path = os.path.abspath(workbook_path)
        else:
            self.workbook_path = workbook_path
            
        self.reader = None
        self.latest_data = {}
        self.latest_positions = {}
        self.lock = threading.Lock()
        self.is_running = False
        self.data_thread = None
        logger.info(f"ExcelConnector initialized for workbook: {self.workbook_path}")

    def start(self):
        \"\"\"データ取得を行うバックグラウンドスレッドを起動する。\"\"\"
        if self.is_running:
            logger.warning("Data listener thread is already running.")
            return
        self.is_running = True
        self.data_thread = threading.Thread(target=self._data_loop, daemon=True, name="ExcelConnectorThread")
        self.data_thread.start()
        logger.info("Excel data listener thread started.")

    def stop(self):
        \"\"\"バックグラウンドスレッドを安全に停止する。\"\"\"
        self.is_running = False
        if self.data_thread and self.data_thread.is_alive():
            self.data_thread.join(timeout=5)
        logger.info("Excel data listener thread stopped.")

    def _data_loop(self):
        \"\"\"
        バックグラウンドで実行され、ExcelReader を使って定期的にデータを更新する。
        \"\"\"
        pythoncom.CoInitialize()
        book = None
        try:
            book = xw.Book(self.workbook_path)
            self.reader = ExcelReader(book.sheets)
            logger.info("Data monitoring thread established connection to Excel.")

            while self.is_running:
                try:
                    # データ取得と解析はReaderに委譲
                    market_data = self.reader.read_market_data()
                    positions = self.reader.read_positions()

                    # 取得したデータをスレッドセーフに格納
                    with self.lock:
                        self.latest_data = market_data
                        self.latest_positions = positions
                        
                except Exception as e:
                    logger.error(f"Error during data read loop: {e}", exc_info=True)
                    # 接続エラーが発生した場合、再接続を試みるためにループを抜ける
                    self.is_running = False
                    break
                
                time.sleep(self.POLLING_INTERVAL)
        except Exception as e:
            logger.critical(f"Data monitoring thread failed to connect to Excel: {e}", exc_info=True)
            self.is_running = False
        finally:
            if book:
                book.close()
            pythoncom.CoUninitialize()
            logger.info("Data monitoring thread has released resources and is shutting down.")

    def get_latest_data(self, symbol: str) -> dict:
        \"\"\"最新の市場データを取得する。\"\"\"
        with self.lock:
            return self.latest_data.get(str(symbol), {}).copy()

    def get_cash(self) -> float:
        \"\"\"最新の現金残高を取得する。\"\"\"
        with self.lock:
            return self.latest_data.get('account', {}).get('cash', 0.0)

    def get_positions(self) -> dict:
        \"\"\"最新の建玉情報を取得する。\"\"\"
        with self.lock:
            return self.latest_positions.copy()
""",

    "src/realtrade/bridge/excel_reader.py": """import logging
try:
    import xlwings as xw
except ImportError:
    xw = None

logger = logging.getLogger(__name__)

class ExcelReader:
    \"\"\"
    Excelシートの構造を熟知し、指定されたセルのデータを読み取って
    Pythonで扱える形式に変換・整形する責務を持つ。
    このクラスは状態を持たない (Stateless)。
    \"\"\"
    def __init__(self, sheets: 'xw.Sheets'):
        if xw is None:
            raise ImportError("xlwings is not installed. Please install it with 'pip install xlwings'")
            
        try:
            self.data_sheet = sheets['リアルタイムデータ']
            self.position_sheet = sheets['position']
            logger.info("ExcelReader initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to find required sheets ('リアルタイムデータ', 'position'). Error: {e}")
            raise

    def read_market_data(self) -> dict:
        \"\"\"
        市場データと現金残高を読み取り、整形された辞書を返す。
        \"\"\"
        try:
            market_data_range = self.data_sheet.range('A2:F10').value
            cash_value = self.data_sheet.range('B11').value

            current_market_data = {}
            if market_data_range:
                for row in market_data_range:
                    symbol = row[0]
                    if symbol is not None:
                        try:
                            # 銘柄コード、株価、出来高などを辞書に格納
                            symbol_str = str(int(symbol))
                            current_market_data[symbol_str] = {
                                'close': row[1], 'open': row[2],
                                'high': row[3], 'low': row[4], 'volume': row[5]
                            }
                        except (ValueError, TypeError):
                            # 不正なデータが含まれる行はスキップ
                            continue
            
            # 口座情報（現金）を辞書に格納
            current_market_data['account'] = {'cash': cash_value}
            return current_market_data

        except Exception as e:
            logger.error(f"Error reading market data from Excel: {e}", exc_info=True)
            return {'account': {'cash': 0.0}} # エラー発生時はデフォルト値を返す

    def read_positions(self) -> dict:
        \"\"\"
        建玉情報を読み取り、整形された辞書を返す。
        \"\"\"
        try:
            position_data_range = self.position_sheet.range('A3:J203').value

            current_positions = {}
            if not position_data_range:
                return {}

            for row in position_data_range:
                symbol_val = row[0]
                # データ終端マーカーまたは空の行で処理を終了
                if symbol_val == '--------' or not symbol_val:
                    break
                
                try:
                    symbol = str(int(symbol_val))
                    side = str(row[6])
                    quantity = float(row[7])
                    price = float(row[9])
                    
                    # '買建'/'売建'を符号付きのsizeに変換
                    size = quantity if side == '買建' else -quantity if side == '売建' else 0
                    
                    if size != 0:
                        current_positions[symbol] = {'size': size, 'price': price}
                except (ValueError, TypeError, IndexError):
                    # 不正なデータが含まれる行はスキップ
                    continue
            
            return current_positions

        except Exception as e:
            logger.error(f"Error reading position data from Excel: {e}", exc_info=True)
            return {} # エラー発生時は空の辞書を返す
""",

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
        
        # [修正] 履歴データ供給完了フラグ。Strategyがこのフラグを監視する。
        self.history_supplied = False if (self._hist_df is not None and not self._hist_df.empty) else True

    def stop(self):
        self._stopevent.set()

    def _load(self):
        if self._hist_df is not None and not self._hist_df.empty:
            row = self._hist_df.iloc[0]
            self._hist_df = self._hist_df.iloc[1:]
            
            self._populate_lines(row)
            logger.debug(f"[{self.symbol}] 過去データを供給: {row.name}")
            
            # [修正] 供給が完了したらフラグを立てるだけにする。通知は行わない。
            if self._hist_df.empty:
                self.history_supplied = True
            
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
        logger.info("【手動発注モード】買いシグナル発生。自動発注は行いません。")
        order = super().buy(owner, data, size, price, plimit, **kwargs)
        return order

    def sell(self, owner, data, size, price=None, plimit=None, **kwargs):
        logger.info("【手動発注モード】売りシグナル発生。自動発注は行いません。")
        order = super().sell(owner, data, size, price, plimit, **kwargs)
        return order

    def cancel(self, order, **kwargs):
        logger.info("【手動発注モード】注文キャンセル。")
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