import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class TradePersistenceAnalyzer(bt.Analyzer):
    params = (('state_manager', None),)
    
    def __init__(self):
        if not self.p.state_manager: raise ValueError("StateManagerがAnalyzerに渡されていません。")
        self.state_manager = self.p.state_manager
        logger.info("TradePersistenceAnalyzer initialized.")

    def notify_trade(self, trade):
        super().notify_trade(trade)
        symbol = trade.data._name
        
        if trade.isclosed:
            # ポジションが決済されたので、DBから削除する
            self.state_manager.delete_position(symbol)
            logger.info(f"StateManager: ポジションをDBから削除: {symbol}")
        
        elif trade.isopen:
            # ポジションが新規にオープンされたので、DBに保存/更新する
            pos = self.strategy.broker.getposition(trade.data)
            if pos.size != 0:
                entry_dt = bt.num2date(trade.dtopen).isoformat()
                self.state_manager.save_position(symbol, pos.size, pos.price, entry_dt)
                logger.info(f"StateManager: ポジションをDBに保存/更新: {symbol} (New Size: {pos.size})")
            else:
                # ポジションクローズ時にisopenが呼ばれることがあるため、その場合は無視する
                logger.info(f"StateManager: isopen通知を受けましたがポジションサイズが0のため無視します: {symbol}")