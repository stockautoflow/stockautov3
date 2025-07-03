import logging

logger = logging.getLogger(__name__)

class SBIStore:
    def __init__(self, api_key, api_secret, paper_trading=True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper_trading = paper_trading
        logger.info(f"SBIStoreを初期化しました。ペーパートレード: {self.paper_trading}")

    def get_cash(self): return 10000000 
    def get_value(self): return 10000000
    
    def get_positions(self):
        # 本来はAPIから取得する。ここではダミーを返す。
        logger.info("【API連携】口座のポジション情報を取得します... (現在はダミー)")
        return [] 
    
    def place_order(self, order):
        logger.info(f"【API連携】注文を送信します: {order}")
        return f"api-order-{id(order)}"
        
    def cancel_order(self, order_id):
        logger.info(f"【API連携】注文キャンセルを送信します: OrderID={order_id}")

    def get_historical_data(self, dataname, timeframe, compression, period):
        logger.info(f"【API連携】履歴データを取得します: {dataname} ({period}本)")
        return None