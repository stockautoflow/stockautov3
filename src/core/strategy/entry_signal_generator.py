class EntrySignalGenerator:
    """
    責務：価格やインジケーターの情報に基づき、新規エントリーのシグナル（買い/売り）を生成する。
    このクラスは状態を持たない（stateless）。
    """
    def __init__(self, indicators, data_feeds):
        self.indicators = indicators
        self.data_feeds = data_feeds

    def check_entry_signal(self, strategy_params):
        """ロングとショート、両方のエントリー条件をチェックし、シグナルを返す"""
        trading_mode = strategy_params.get('trading_mode', {})
        
        if trading_mode.get('long_enabled', True):
            is_met, reason = self._check_all_conditions('long', strategy_params)
            if is_met:
                return 'long', reason

        if trading_mode.get('short_enabled', True):
            is_met, reason = self._check_all_conditions('short', strategy_params)
            if is_met:
                return 'short', reason
        
        return None, None

    def _check_all_conditions(self, trade_type, strategy_params):
        """指定されたタイプの全エントリー条件が満たされているか評価する"""
        conditions = strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not conditions:
            return False, ""

        reason_details = []
        all_conditions_met = True
        for c in conditions:
            is_met, reason_str = self._evaluate_condition(c)
            if not is_met:
                all_conditions_met = False
                break
            reason_details.append(reason_str)

        return (all_conditions_met, " / ".join(reason_details)) if all_conditions_met else (False, "")

    def _evaluate_condition(self, cond):
        """単一の条件式を評価する"""
        tf, cond_type = cond['timeframe'], cond.get('type')
        data_feed = self.data_feeds[tf]
        if len(data_feed) == 0:
            return False, ""

        # クロスオーバー/クロスアンダー条件の評価
        if cond_type in ['crossover', 'crossunder']:
            from .strategy_initializer import StrategyInitializer
            si = StrategyInitializer({}) # ヘルパーメソッドのためだけにインスタンス化
            k1 = si._get_indicator_key(tf, **cond['indicator1'])
            k2 = si._get_indicator_key(tf, **cond['indicator2'])
            cross_indicator = self.indicators.get(f"cross_{k1}_vs_{k2}")
            
            if cross_indicator is None or len(cross_indicator) == 0: return False, ""

            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or \
                     (cross_indicator[0] < 0 and cond_type == 'crossunder')
            
            p1 = ",".join(map(str, cond['indicator1'].get('params', {}).values()))
            p2 = ",".join(map(str, cond['indicator2'].get('params', {}).values()))
            reason = f"{tf[0].upper()}: {cond_type}({cond['indicator1']['name']}({p1}),{cond['indicator2']['name']}({p2})) [{is_met}]"
            return is_met, reason

        # 通常の比較条件の評価
        from .strategy_initializer import StrategyInitializer
        si = StrategyInitializer({}) # ヘルパーメソッドのためだけにインスタンス化
        ind = self.indicators.get(si._get_indicator_key(tf, **cond['indicator']))
        if ind is None or len(ind) == 0: return False, ""

        val, compare, target = ind[0], cond['compare'], cond['target']
        target_type, target_val, target_val_str = target.get('type'), None, ""

        if target_type == 'data':
            target_val = getattr(data_feed, target['value'])[0]
            target_val_str = f"{target['value']} [{target_val:.2f}]"
        elif target_type == 'indicator':
            target_ind = self.indicators.get(si._get_indicator_key(tf, **target['indicator']))
            if target_ind is None or len(target_ind) == 0: return False, ""
            target_val = target_ind[0]
            target_val_str = f"{target['indicator']['name']}(...) [{target_val:.2f}]"
        elif target_type == 'values':
            target_val = target['value']
            target_val_str = f"[{target_val[0]},{target_val[1]}]" if compare == 'between' else f"[{target_val}]"

        if target_val is None: return False, ""

        is_met = False
        if compare == '>': is_met = val > (target_val[0] if isinstance(target_val, list) else target_val)
        elif compare == '<': is_met = val < (target_val[0] if isinstance(target_val, list) else target_val)
        elif compare == 'between': is_met = target_val[0] < val < target_val[1]
        
        params_str = ",".join(map(str, cond['indicator'].get('params', {}).values()))
        reason = f"{tf[0].upper()}: {cond['indicator']['name']}({params_str}) [{val:.2f}] {compare} {target_val_str}"
        return is_met, reason