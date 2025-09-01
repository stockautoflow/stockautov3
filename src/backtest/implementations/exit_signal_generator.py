from src.core.strategy.exit_signal_generator import BaseExitSignalGenerator

class BacktestExitSignalGenerator(BaseExitSignalGenerator):
    """
    [リファクタリング - 実装]
    バックテストでは何もしない。
    決済はBrokerのネイティブOCO注文に完全に委任するため。
    """
    def check_exit_conditions(self):
        pass