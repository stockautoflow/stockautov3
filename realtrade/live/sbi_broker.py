import backtrader as bt
import logging
from backtrader.position import Position

logger = logging.getLogger(__name__)

class SBIBroker(bt.brokers.BrokerBase):
    def __init__(self, store, persisted_positions=None):
        super(SBIBroker, self).__init__()
        self.store = store
        self.orders = []
        self.persisted_positions = persisted_positions or {}
        logger.info("SBIBrokerを初期化しました。")

    def start(self):
        super(SBIBroker, self).start()
        self.cash = self.store.get_cash()
        self.value = self.store.get_value()
        logger.info(f"Brokerを開始しました。現金: {self.cash}, 資産価値: {self.value}")
        if self.persisted_positions:
            self.restore_positions(self.persisted_positions, self.cerebro.datasbyname)

    def restore_positions(self, db_positions, datasbyname):
        logger.info("データベースからポジション情報を復元中 (SBIBroker)...")
        for symbol, pos_data in db_positions.items():
            if symbol in datasbyname:
                data_feed = datasbyname[symbol]
                size = pos_data.get('size')
                price = pos_data.get('price')
                if size is not None and price is not None:
                    pos = self.positions.get(data_feed, Position())
                    pos.size = size
                    pos.price = price
                    self.positions[data_feed] = pos
                    self.cash -= size * price # 現金を調整
                    logger.info(f"  -> 復元完了: {symbol}, Size: {size}, Price: {price}, Cash Adjusted: {-size * price}")
                else:
                    logger.warning(f"  -> 復元失敗: {symbol} のデータが不完全です。{pos_data}")
            else:
                logger.warning(f"  -> 復元失敗: 銘柄 '{symbol}' に対応するデータフィードが見つかりません。")

    def buy(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None, **kwargs):
        order = super().buy(owner, data, size, price, plimit, exectype, valid, tradeid, oco, trailamount, trailpercent, **kwargs)
        order.api_id = self.store.place_order(order)
        self.orders.append(order)
        self.notify(order)
        return order

    def sell(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None, **kwargs):
        order = super().sell(owner, data, size, price, plimit, exectype, valid, tradeid, oco, trailamount, trailpercent, **kwargs)
        order.api_id = self.store.place_order(order)
        self.orders.append(order)
        self.notify(order)
        return order

    def cancel(self, order):
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            self.store.cancel_order(order.api_id)
            order.cancel()
            self.notify(order)
        return order