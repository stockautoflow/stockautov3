import yaml
import copy
import logging
import inspect
import backtrader as bt
from .indicators import SafeStochastic, VWAP, SafeADX

logger = logging.getLogger(__name__)

class StrategyInitializer:
    def __init__(self, strategy_catalog_file, base_strategy_file):
        self.strategy_catalog = self._load_yaml(strategy_catalog_file)
        self.base_strategy_params = self._load_yaml(base_strategy_file)

    def _load_yaml(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"設定ファイル '{filepath}' が見つかりません。")
            return {}
        except Exception as e:
            logger.error(f"'{filepath}' の読み込み中にエラー: {e}")
            return {}
    
    def create_indicators(self, strategy, strategy_params):
        indicators, unique_defs = {}, {}
        
        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            params = ind_def.get('params', {})
            param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
            key = f"{timeframe}_{ind_def['name']}_{param_str}"
            if key not in unique_defs: unique_defs[key] = (timeframe, ind_def)

        if isinstance(strategy_params.get('entry_conditions'), dict):
            for cond_list in strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict): continue
                    tf = cond.get('timeframe')
                    if not tf: continue
                    add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                    if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target']['indicator'])

        if isinstance(strategy_params.get('exit_conditions'), dict):
            for exit_type in ['take_profit', 'stop_loss']:
                cond = strategy_params['exit_conditions'].get(exit_type, {})
                if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                    atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                    add_def(cond.get('timeframe'), {'name': 'atr', 'params': atr_params})
        
        backtrader_indicators = {
            'ema': bt.indicators.EMA, 'rsi': bt.indicators.RSI, 'atr': bt.indicators.ATR,
            'macd': bt.indicators.MACD, 'bollingerbands': bt.indicators.BollingerBands,
            'sma': bt.indicators.SMA, 'stochastic': SafeStochastic, 'vwap': VWAP, 'adx': SafeADX
        }
        
        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = backtrader_indicators.get(name.lower())
            
            if ind_cls:
                try:
                    indicators[key] = ind_cls(strategy.data_feeds[timeframe], plot=False, **params)
                    strategy.logger.info(f"インジケーターを生成: {name} (Timeframe: {timeframe})")
                except Exception as e:
                    strategy.logger.error(f"インジケーター '{name}' の生成に失敗しました: {e}")
            else:
                strategy.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        for cond_list in strategy_params.get('entry_conditions', {}).values():
            for cond in cond_list:
                if cond.get('type') in ['crossover', 'crossunder']:
                    ind1_key = self._get_indicator_key(cond['timeframe'], **cond['indicator1'])
                    ind2_key = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    cross_key = f"cross_{ind1_key}_vs_{ind2_key}"
                    if ind1_key in indicators and ind2_key in indicators and cross_key not in indicators:
                        indicators[cross_key] = bt.indicators.CrossOver(indicators[ind1_key], indicators[ind2_key], plot=False)

        return indicators

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"