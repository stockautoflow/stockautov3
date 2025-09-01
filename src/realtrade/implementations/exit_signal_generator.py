from src.core.strategy.exit_signal_generator import BaseExitSignalGenerator

class RealTradeExitSignalGenerator(BaseExitSignalGenerator):
    """
    [リファクタリング - 実装]
    毎barの価格を監視し、決済条件を判定する。
    トレーリングストップのロジックもここに実装。
    """
    def check_exit_conditions(self):
        pos = self.strategy.getposition()
        is_long = pos.size > 0
        current_price = self.strategy.datas[0].close[0]
        logger = self.strategy.logger

        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            logger.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
            self.order_manager.close_position()
            return

        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                logger.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                self.order_manager.close_position()
                return
            # トレーリングストップの更新
            new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                logger.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                self.sl_price = new_sl_price