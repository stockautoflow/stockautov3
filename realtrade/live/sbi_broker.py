import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class SBIBroker(bt.brokers.BrokerBase):
    def __init__(self, store):
        super(SBIBroker, self).__init__()
        self.store = store
        self.orders = [] 
        logger.info("SBIBrokerを初期化しました。")

    def start(self):
        super(SBIBroker, self).start()
        self.cash = self.store.get_cash()
        self.value = self.store.get_value()
        logger.info(f"Brokerを開始しました。現金: {self.cash}, 資産価値: {self.value}")

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