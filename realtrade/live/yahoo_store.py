import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

class YahooStore:
    def __init__(self, **kwargs):
        logger.info("YahooStoreを初期化しました。")

    def get_cash(self): return 0
    def get_value(self): return 0
    def get_positions(self): return []
    def place_order(self, order): return None
    def cancel_order(self, order_id): return None

    def get_historical_data(self, dataname, period, interval='1m'):
        logger.info(f"【Yahoo Finance】履歴データを取得します: {dataname} ({period} {interval})")
        ticker = f"{dataname}.T"
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
            
            if df.empty:
                logger.warning(f"{ticker}のデータ取得に失敗しました。")
                return pd.DataFrame()

            # --- ▼▼▼ ここから修正 ▼▼▼ ---
            # yfinanceがMultiIndexを返す場合に対処
            if isinstance(df.columns, pd.MultiIndex):
                logger.debug(f"[{dataname}] MultiIndexのカラムを平坦化します。")
                # 例: [('Open', '7270.T'), ('High', '7270.T')] -> ['Open', 'High']
                df.columns = [col[0] for col in df.columns]
            # --- ▲▲▲ ここまで修正 ▲▲▲ ---

            df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            
            df['openinterest'] = 0.0
            
            logger.info(f"{dataname}の履歴データを{len(df)}件取得しました。")
            return df
        except Exception as e:
            logger.error(f"{ticker}のデータ取得中にエラーが発生しました: {e}")
            return pd.DataFrame()