import xlwings as xw
import threading
import time
import logging
import pythoncom
import os

from .excel_reader import ExcelReader

logger = logging.getLogger(__name__)

class ExcelConnector:
    """
    Excelとの接続、データ取得スレッドの管理、最新データの保持を行うサービス。
    システムの他の部分はこのクラスを介してExcelのデータにアクセスする。
    """
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
        """データ取得を行うバックグラウンドスレッドを起動する。"""
        if self.is_running:
            logger.warning("Data listener thread is already running.")
            return
        self.is_running = True
        self.data_thread = threading.Thread(target=self._data_loop, daemon=True, name="ExcelConnectorThread")
        self.data_thread.start()
        logger.info("Excel data listener thread started.")

    def stop(self):
        """バックグラウンドスレッドを安全に停止する。"""
        self.is_running = False
        if self.data_thread and self.data_thread.is_alive():
            self.data_thread.join(timeout=5)
        logger.info("Excel data listener thread stopped.")

    def _data_loop(self):
        """
        バックグラウンドで実行され、ExcelReader を使って定期的にデータを更新する。
        """
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
        """最新の市場データを取得する。"""
        with self.lock:
            return self.latest_data.get(str(symbol), {}).copy()

    def get_cash(self) -> float:
        """最新の現金残高を取得する。"""
        with self.lock:
            return self.latest_data.get('account', {}).get('cash', 0.0)

    def get_positions(self) -> dict:
        """最新の建玉情報を取得する。"""
        with self.lock:
            return self.latest_positions.copy()