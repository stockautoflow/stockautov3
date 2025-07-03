import logging
logger = logging.getLogger(__name__)
class SBIStore:
    def __init__(self, api_key, api_secret, paper_trading=True):
        self.api_key, self.api_secret, self.paper_trading = api_key, api_secret, paper_trading
        logger.info(f"SBIStoreを初期化しました。ペーパートレード: {self.paper_trading}")
    def get_cash(self): return 10000000 
    def get_value(self): return 10000000
    def get_positions(self): return [] 
    def place_order(self, order): logger.info(f"【API連携】注文送信: {order}"); return f"api-order-{id(order)}"
    def cancel_order(self, order_id): logger.info(f"【API連携】注文キャンセル送信: OrderID={order_id}")
    def get_historical_data(self, dataname, timeframe, compression, period): logger.info(f"【API連携】履歴データ取得: {dataname} ({period}本)"); return None