import backtrader as bt
import logging
from backtrader.position import Position

logger = logging.getLogger(__name__)

class CustomBackBroker(bt.brokers.BackBroker):
    def __init__(self, persisted_positions=None, **kwargs):
        super(CustomBackBroker, self).__init__(**kwargs)
        self.persisted_positions = persisted_positions or {}
        logger.info(f"CustomBackBrokerを初期化しました。Initial Cash: {self.startingcash}")

    def start(self):
        super(CustomBackBroker, self).start()
        if self.persisted_positions:
            self.restore_positions(self.persisted_positions, self.cerebro.datasbyname)

    def restore_positions(self, db_positions, datasbyname):
        logger.info("データベースからポジション情報を復元中 (CustomBackBroker)...")
        for symbol, pos_data in db_positions.items():
            if symbol in datasbyname:
                data_feed = datasbyname[symbol]
                size = pos_data.get('size')
                price = pos_data.get('price')
                if size is not None and price is not None:
                    self.positions[data_feed].size = size
                    self.positions[data_feed].price = price
                    self.cash -= size * price # 現金を調整
                    logger.info(f"  -> 復元完了: {symbol}, Size: {size}, Price: {price}, Cash Adjusted: {-size * price}")
                else:
                    logger.warning(f"  -> 復元失敗: {symbol} のデータが不完全です。{pos_data}")
            else:
                logger.warning(f"  -> 復元失敗: 銘柄 '{symbol}' に対応するデータフィードが見つかりません。")