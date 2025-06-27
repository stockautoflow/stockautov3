from realtrade.broker_bridge import BrokerBridge, OrderStatus
import logging

class MockBrokerBridge(BrokerBridge):
    def start(self): print("MockBroker: 接続しました。")
    def stop(self): print("MockBroker: 接続を終了しました。")
    def get_cash(self): return 10000000.0
    def get_position(self, data, clone=True): return 0.0
    def place_order(self, order):
        print(f"MockBroker: 注文リクエスト受信: {order.info}")
        order.executed.price = order.price
        order.executed.size = order.size
        self.notify(order)
    def cancel_order(self, order):
        print(f"MockBroker: 注文キャンセルリクエスト受信: {order.ref}")
        self.notify(order)
    def poll_orders(self): pass