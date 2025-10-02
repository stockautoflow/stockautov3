import logging
try:
    import xlwings as xw
except ImportError:
    xw = None

logger = logging.getLogger(__name__)

class ExcelReader:
    """
    Excelシートの構造を熟知し、指定されたセルのデータを読み取って
    Pythonで扱える形式に変換・整形する責務を持つ。
    このクラスは状態を持たない (Stateless)。
    """
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
        """
        市場データと現金残高を読み取り、整形された辞書を返す。
        """
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
        """
        建玉情報を読み取り、整形された辞書を返す。
        """
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