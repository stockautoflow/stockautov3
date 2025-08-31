from datetime import datetime

class PositionManager:
    """
    責務：現在のポジション情報を保持し、システムの再起動時に状態を復元する。
    """
    def __init__(self, persisted_position):
        self.persisted_position = persisted_position
        self.is_restoring = persisted_position is not None
        
        # トレード分析用の情報
        self.current_position_entry_dt = None
        self.entry_reason_for_trade = ""
        self.executed_size = 0

    def restore_state(self, strategy, exit_signal_generator):
        """永続化された情報からポジションの状態を復元する"""
        pos_info = self.persisted_position
        size, price = pos_info['size'], pos_info['price']

        strategy.position.size = size
        strategy.position.price = price
        self.current_position_entry_dt = datetime.fromisoformat(pos_info['entry_datetime'])

        exit_signal_generator.calculate_and_set_exit_prices(entry_price=price, is_long=(size > 0))
        
        strategy.logger.log(
            f"ポジション復元完了。Size: {size}, Price: {price}, "
            f"SL: {exit_signal_generator.sl_price:.2f}, TP: {exit_signal_generator.tp_price:.2f}"
        )
        self.is_restoring = False

    def on_trade_update(self, trade, strategy):
        """トレードの開始/終了イベントを処理する"""
        if trade.isopen:
            strategy.logger.log(f"トレード開始: {'BUY' if trade.long else 'SELL'}, Size: {trade.size}, Price: {trade.price}")
            self.current_position_entry_dt = strategy.data.datetime.datetime(0)
            # エントリー理由はEventHandlerが保持しているものを参照
            self.entry_reason_for_trade = strategy.event_handler.current_entry_reason
            self.executed_size = trade.size
        
        elif trade.isclosed:
            # バックテスト分析用に情報を追加
            trade.executed_size = self.executed_size
            trade.entry_reason_for_trade = self.entry_reason_for_trade
            strategy.logger.log(f"トレード終了: PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")
            self.current_position_entry_dt = None
            self.entry_reason_for_trade = ""
            self.executed_size = 0