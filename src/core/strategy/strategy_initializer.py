import backtrader as bt
import inspect
import logging

# 変更: core パッケージからインポート
from ..indicators import SafeStochastic, VWAP, SafeADX

class StrategyInitializer:
    """
    責務：戦略の実行に必要な設定を読み込み、インジケーター群を生成する。
    """
    def __init__(self, strategy_params):
        self.strategy_params = strategy_params
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_indicator_key(self, timeframe, name, params):
        """インジケーターを一意に識別するためのキーを生成する"""
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def create_indicators(self, data_feeds):
        """設定に基づき、Backtraderのインジケーターオブジェクトを動的に生成する"""
        indicators, unique_defs = {}, {}

        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            key = self._get_indicator_key(timeframe, **ind_def)
            if key not in unique_defs: unique_defs[key] = (timeframe, ind_def)

        # エントリー条件から必要なインジケーターを収集
        if isinstance(self.strategy_params.get('entry_conditions'), dict):
            for cond_list in self.strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict): continue
                    tf = cond.get('timeframe')
                    if not tf: continue
                    add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                    if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target']['indicator'])
        
        # 決済条件から必要なインジケーターを収集
        if isinstance(self.strategy_params.get('exit_conditions'), dict):
            for exit_type in ['take_profit', 'stop_loss']:
                cond = self.strategy_params['exit_conditions'].get(exit_type, {})
                if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                    atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                    add_def(cond.get('timeframe'), {'name': 'atr', 'params': atr_params})

        # 収集した定義に基づき、インジケーターをインスタンス化
        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = self._find_indicator_class(name)

            if ind_cls:
                self.logger.debug(f"インジケーター作成: {key} using class {ind_cls.__name__}")
                indicators[key] = ind_cls(data_feeds[timeframe], plot=False, **params)
            else:
                self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        # クロスオーバー用のインジケーターを追加
        if isinstance(self.strategy_params.get('entry_conditions'), dict):
            for cond_list in self.strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict) or cond.get('type') not in ['crossover', 'crossunder']: continue
                    k1 = self._get_indicator_key(cond['timeframe'], **cond['indicator1']); k2 = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    if k1 in indicators and k2 in indicators:
                        cross_key = f"cross_{k1}_vs_{k2}"
                        if cross_key not in indicators: indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2], plot=False)
        
        return indicators

    def _find_indicator_class(self, name):
        """文字列からBacktraderのインジケータークラスを見つける"""
        custom_indicators = {'stochastic': SafeStochastic, 'vwap': VWAP, 'adx': SafeADX}
        if name.lower() in custom_indicators:
            return custom_indicators[name.lower()]
        
        for n_cand in [name, name.upper(), name.capitalize(), f"{name.capitalize()}Safe", f"{name.upper()}_Safe"]:
            cls_candidate = getattr(bt.indicators, n_cand, None)
            if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator):
                return cls_candidate
        return None