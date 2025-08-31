import logging

class StrategyLogger:
    """
    責務：整形されたメッセージを受け取り、ログファイルに記録する。
    """
    def __init__(self, strategy):
        self.strategy = strategy
        # 銘柄ごとにユニークなロガーを取得
        symbol_str = strategy.data0._name.split('_')[0]
        self.logger = logging.getLogger(f"{strategy.__class__.__name__}-{symbol_str}")

    def log(self, txt, dt=None, level=logging.INFO):
        """タイムスタンプ付きでメッセージをログに記録する"""
        log_time = dt or self.strategy.data.datetime.datetime(0)
        self.logger.log(level, f'{log_time.isoformat()} - {txt}')

    def log_bar_data(self, indicators):
        """デバッグレベルが有効な場合、全インジケーターの値を記録する"""
        if not self.logger.isEnabledFor(logging.DEBUG):
            return
            
        log_msg = f"\\n===== Bar Check on {self.strategy.data.datetime.datetime(0).isoformat()} =====\\n"
        log_msg += "--- Price Data ---\\n"
        # 修正点: self.strategy.datas._feedmanaged.items() -> self.strategy.data_feeds.items()
        for tf_name, data_feed in self.strategy.data_feeds.items():
            if len(data_feed) > 0 and data_feed.close[0] is not None:
                dt = data_feed.datetime.datetime(0)
                log_msg += (f"  [{tf_name.upper():<6}] {dt.isoformat()} | "
                            f"O:{data_feed.open[0]:.2f} H:{data_feed.high[0]:.2f} "
                            f"L:{data_feed.low[0]:.2f} C:{data_feed.close[0]:.2f} "
                            f"V:{data_feed.volume[0]:.0f}\\n")
            else:
                log_msg += f"  [{tf_name.upper():<6}] No data available for this bar\\n"
        
        log_msg += "--- Indicator Values ---\\n"
        for key in sorted(indicators.keys()):
            indicator = indicators[key]
            if len(indicator) > 0 and indicator[0] is not None:
                values = [f"{alias}: {getattr(indicator.lines, alias)[0]:.4f}" for alias in indicator.lines.getlinealiases() if len(getattr(indicator.lines, alias)) > 0]
                if values: log_msg += f"  [{key}]: {', '.join(values)}\\n"
        
        self.logger.debug(log_msg)