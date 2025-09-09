import xlwings as xw
import threading
import time
import logging
import pythoncom
import os

logger = logging.getLogger(__name__)

class ExcelBridge:
    def __init__(self, workbook_path: str):
        if not os.path.isabs(workbook_path):
            self.workbook_path = os.path.abspath(workbook_path)
        else:
            self.workbook_path = workbook_path
            
        self.latest_data = {}
        self.latest_positions = {}
        self.lock = threading.Lock()
        self.is_running = False
        self.data_thread = None
        logger.info(f"ExcelBridge initialized for workbook: {self.workbook_path}")

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
        POLLING_INTERVAL = 1
        
        try:
            try:
                book = xw.Book(self.workbook_path)
                data_sheet = book.sheets['リアルタイムデータ']
                position_sheet = book.sheets['position']
                logger.info("データ監視スレッドがExcelへの接続を確立しました。")
            except Exception as e:
                logger.critical(f"データ監視スレッドがExcelに接続できませんでした: {e}")
                self.is_running = False
                return

            while self.is_running:
                try:
                    market_data_range = data_sheet.range('A2:F10').value
                    cash_value = data_sheet.range('B11').value
                    position_data_range = position_sheet.range('A3:J203').value

                    with self.lock:
                        current_market_data = {}
                        for row in market_data_range:
                            symbol = row[0]
                            if symbol is not None:
                                try:
                                    symbol_str = str(int(symbol))
                                    current_market_data[symbol_str] = {
                                        'close': row[1], 'open': row[2],
                                        'high': row[3], 'low': row[4], 'volume': row[5]
                                    }
                                except (ValueError, TypeError): continue
                        current_market_data['account'] = {'cash': cash_value}
                        self.latest_data = current_market_data

                        current_positions = {}
                        for row in position_data_range:
                            symbol_val = row[0]
                            if symbol_val == '--------' or not symbol_val: break
                            try:
                                symbol = str(int(symbol_val))
                                side = str(row[6]); quantity = float(row[7]); price = float(row[9])
                                size = quantity if side == '買建' else -quantity if side == '売建' else 0
                                if size != 0:
                                    current_positions[symbol] = {'size': size, 'price': price}
                            except (ValueError, TypeError, IndexError): continue
                        self.latest_positions = current_positions
                        
                        # [修正] logger.traceをlogger.debugに変更
                        logger.debug(f"Excelから取得したポジション詳細: {self.latest_positions}")

                except Exception as e:
                    logger.error(f"Excelからのデータ読み取り中にエラーが発生しました: {e}")
                    self.is_running = False
                    break
                
                time.sleep(POLLING_INTERVAL)
        finally:
            pythoncom.CoUninitialize()
            logger.info("データ監視スレッドがリソースを解放し、終了しました。")

    def get_latest_data(self, symbol: str) -> dict:
        with self.lock:
            return self.latest_data.get(str(symbol), {}).copy()

    def get_cash(self) -> float:
        with self.lock:
            return self.latest_data.get('account', {}).get('cash', 0.0)

    def get_positions(self) -> dict:
        with self.lock:
            return self.latest_positions.copy()

    def place_order(self, symbol, side, qty, order_type, price):
        logger.info(f"【手動発注モード】注文シグナル発生: {side} {symbol} {qty}株")
        logger.info("自動発注は行われません。手動で発注してください。")
        return {"status": "MANUAL_MODE", "order_id": None}