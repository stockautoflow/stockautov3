import xlwings as xw
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
        self.held_positions = {}

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
        position_sheet = None
        POLLING_INTERVAL = 0.5

        try:
            try:
                book = xw.Book(self.workbook_path)
                data_sheet = book.sheets['リアルタイムデータ']
                position_sheet = book.sheets['position']
                logger.info("データ・ポジション監視スレッドがExcelへの接続を確立しました。")
            except Exception as e:
                logger.critical(f"データ・ポジション監視スレッドがExcelに接続できませんでした: {e}")
                return

            while self.is_running:
                try:
                    market_data_range = data_sheet.range('A2:F10').value
                    cash_value = data_sheet.range('B11').value

                    # --- ポジションリストの読み取り ---
                    positions_range = position_sheet.range('A3:J50').value
                    current_positions = {}
                    for row in positions_range:
                        symbol = row[0]

                        # [修正] "--------" を末尾マーカーとして検知し、ループを抜ける
                        if symbol == "--------":
                            break
                        
                        if symbol is None:
                            continue
                        
                        entry_price = row[9] # J列
                        
                        try:
                            symbol_str = str(int(symbol))
                            if isinstance(entry_price, (int, float)) and entry_price > 0:
                                current_positions[symbol_str] = float(entry_price)
                            else:
                                if entry_price is not None:
                                    logger.warning(f"銘柄 {symbol_str} の建値 '{entry_price}' が不正なため無視します。")
                        except (ValueError, TypeError):
                             logger.warning(f"銘柄コードまたは建値の型変換エラー。Symbol: {symbol}, Price: {entry_price}")


                    with self.lock:
                        for row in market_data_range:
                            symbol = row[0]
                            if symbol is not None:
                                try:
                                    symbol_str = str(int(symbol))
                                    self.latest_data[symbol_str] = {
                                        'close': row[1], 'open': row[2],
                                        'high': row[3], 'low': row[4],
                                        'volume': row[5]
                                    }
                                except (ValueError, TypeError):
                                    # 価格データ部分にもゴミデータが入る可能性を考慮
                                    pass
                        self.latest_data['account'] = {'cash': cash_value}

                        self.held_positions = current_positions

                except Exception as e:
                    logger.error(f"Excelからのデータ読み取り中にエラーが発生しました: {e}")
                    with self.lock:
                        self.held_positions = {}
                
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

    def get_held_positions(self) -> dict:
        """現在保有しているポジションの {銘柄コード: 建値} 辞書を返す。"""
        with self.lock:
            return self.held_positions.copy()

    def place_order(self, symbol, side, qty, order_type, price):
        logger.info(f"【手動発注モード】注文シグナル発生: {side} {symbol} {qty}株")
        logger.info("自動発注は行われません。手動で発注してください。")
        return {"status": "MANUAL_MODE", "order_id": None}