import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class SBIBroker(bt.brokers.BrokerBase):
    """
    backtraderのBrokerとして振る舞い、SBIStore経由で実際の取引を行う。
    """
    def __init__(self, store):
        super(SBIBroker, self).__init__()
        self.store = store
        self.orders = [] # 未約定の注文を管理
        logger.info("SBIBrokerを初期化しました。")

    def start(self):
        super(SBIBroker, self).start()
        self.cash = self.store.get_cash()
        self.value = self.store.get_value()
        logger.info(f"Brokerを開始しました。現金: {self.cash}, 資産価値: {self.value}")

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None, **kwargs):
        
        order = super().buy(owner, data, size, price, plimit,
                            exectype, valid, tradeid, oco,
                            trailamount, trailpercent, **kwargs)
        # 実際のAPIに注文を送信
        api_order_id = self.store.place_order(order)
        order.api_id = api_order_id # APIの注文IDを保存
        self.orders.append(order)
        self.notify(order)
        return order

    def sell(self, owner, data, size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None, **kwargs):

        order = super().sell(owner, data, size, price, plimit,
                             exectype, valid, tradeid, oco,
                             trailamount, trailpercent, **kwargs)
        # 実際のAPIに注文を送信
        api_order_id = self.store.place_order(order)
        order.api_id = api_order_id # APIの注文IDを保存
        self.orders.append(order)
        self.notify(order)
        return order

    def cancel(self, order):
        if order.status == bt.Order.Submitted or order.status == bt.Order.Accepted:
            self.store.cancel_order(order.api_id)
            order.cancel()
            self.notify(order)
        return order