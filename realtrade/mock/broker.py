from realtrade.broker_bridge import BrokerBridge
import backtrader as bt
import logging

class MockBrokerBridge(BrokerBridge):
    def __init__(self, config):
        super().__init__(config)
        self.positions = {}

    def start(self):
        print("MockBroker: 接続しました。")
        # [修正] 起動時の現金をstartingcashとして保存
        self.startingcash = self.getcash()

    def stop(self):
        print("MockBroker: 接続を終了しました。")

    def getcash(self):
        return 10000000.0

    def getposition(self, data, clone=True):
        return self.positions.get(data._name, self.Position(size=0, price=0.0))

    def getvalue(self, datas=None):
        val = self.getcash()
        for pos in self.positions.values():
            val += pos.size * pos.price
        return val

    def place_order(self, order):
        exec_price = order.price or order.data.close[0]
        exec_size = order.size if order.isbuy() else -order.size
        
        pos = self.getposition(order.data)
        
        new_size = pos.size + exec_size
        if new_size != 0:
            if pos.size == 0:
                pos.price = exec_price
            else:
                pos.price = ((pos.price * pos.size) + (exec_price * exec_size)) / new_size
        
        pos.size = new_size
        self.positions[order.data._name] = pos

        order.executed.price = exec_price
        order.executed.size = order.size
        order.executed.dt = self.env.datetime.datetime(0)
        
        self.notification_queue.append(order)
        logging.info(f"MockBroker: 注文約定 {order.data._name} Size:{exec_size} @{exec_price:.2f}, New Position Size: {pos.size}")

    def cancel_order(self, order):
        logging.info(f"MockBroker: 注文キャンセルリクエスト受信: {order.ref}")
        self.notification_queue.append(order)

    def poll_orders(self):
        pass