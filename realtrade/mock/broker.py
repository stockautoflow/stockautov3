from realtrade.broker_bridge import BrokerBridge, OrderStatus
import logging

class MockBrokerBridge(BrokerBridge):
    """
    実際のAPIに接続せず、ダミーデータを返す模擬ブローカー。
    システムの基本ロジックをテストするために使用します。
    """
    def start(self):
        print("MockBroker: 接続しました。")

    def stop(self):
        print("MockBroker: 接続を終了しました。")

    def get_cash(self):
        # ダミーの現金額を返す
        return 10000000.0

    def get_position(self, data, clone=True):
        # 常にポジション0を返す
        return 0.0

    def place_order(self, order):
        print(f"MockBroker: 注文リクエスト受信: {order.info}")
        # 即座に約定したと仮定して通知
        order.executed.price = order.price
        order.executed.size = order.size
        self.notify(order)

    def cancel_order(self, order):
        print(f"MockBroker: 注文キャンセルリクエスト受信: {order.ref}")
        self.notify(order) # キャンセルを通知

    def poll_orders(self):
        # モックなので何もしない
        pass