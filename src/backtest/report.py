import pandas as pd
from datetime import datetime
# [リファクタリング] configモジュールのインポート先を変更
from . import config_backtest as config

def _format_condition_for_report(cond):
    """YAMLの条件定義を人間が読みやすい文字列にフォーマットします。"""
    tf = cond['timeframe'][0].upper()
    cond_type = cond.get('type')

    if cond_type in ['crossover', 'crossunder']:
        i1 = cond['indicator1']
        i2 = cond['indicator2']
        p1 = ",".join(map(str, i1.get('params', {}).values()))
        p2 = ",".join(map(str, i2.get('params', {}).values()))
        op = " crosses over " if cond_type == 'crossover' else " crosses under "
        return f"{tf}: {i1['name']}({p1}){op}{i2['name']}({p2})"

    ind_def = cond['indicator']
    ind_str = f"{ind_def['name']}({','.join(map(str, ind_def.get('params', {}).values()))})"
    comp_str = 'is between' if cond['compare'] == 'between' else cond['compare']
    
    tgt = cond['target']
    tgt_type = tgt.get('type')
    tgt_str = ""

    if tgt_type == 'data':
        tgt_str = tgt.get('value', '')
    elif tgt_type == 'indicator':
        tgt_ind_def = tgt.get('indicator', {})
        tgt_params_str = ",".join(map(str, tgt_ind_def.get('params', {}).values()))
        tgt_str = f"{tgt_ind_def.get('name', '')}({tgt_params_str})"
    elif tgt_type == 'values':
        value = tgt.get('value')
        tgt_str = f"{value[0]} and {value[1]}" if isinstance(value, list) and len(value) > 1 else str(value)

    return f"{tf}: {ind_str} {comp_str} {tgt_str}"

def _format_exit_for_report(exit_cond):
    """YAMLの決済条件を人間が読みやすい文字列にフォーマットします。"""
    p = exit_cond.get('params', {})
    tf = exit_cond.get('timeframe','?')[0]
    mult = p.get('multiplier')
    period = p.get('period')
    
    if exit_cond.get('type') == 'atr_multiple':
        return f"Fixed ATR(t:{tf}, p:{period}) * {mult}"
    if exit_cond.get('type') == 'atr_stoptrail':
        return f"Native StopTrail ATR(t:{tf}, p:{period}) * {mult}"
    return "Unknown"

def generate_report(all_results, strategy_params, start_date, end_date):
    """
    バックテスト結果全体からサマリーレポートを生成します。
    """
    total_net = sum(r['pnl_net'] for r in all_results)
    total_won = sum(r['gross_won'] for r in all_results)
    total_lost = sum(r['gross_lost'] for r in all_results)
    total_trades = sum(r['total_trades'] for r in all_results)
    total_win = sum(r['win_trades'] for r in all_results)
    
    win_rate = (total_win / total_trades) * 100 if total_trades > 0 else 0
    pf = abs(total_won / total_lost) if total_lost != 0 else float('inf')
    avg_profit = total_won / total_win if total_win > 0 else 0
    avg_loss = total_lost / (total_trades - total_win) if (total_trades - total_win) > 0 else 0
    rr = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')

    p = strategy_params
    long_c = "Long: " + " AND ".join([_format_condition_for_report(c) for c in p.get('entry_conditions',{}).get('long',[])]) if p.get('trading_mode',{}).get('long_enabled') else ""
    short_c = "Short: " + " AND ".join([_format_condition_for_report(c) for c in p.get('entry_conditions',{}).get('short',[])]) if p.get('trading_mode',{}).get('short_enabled') else ""
    tp_desc = _format_exit_for_report(p.get('exit_conditions',{}).get('take_profit',{})) if p.get('exit_conditions',{}).get('take_profit') else "N/A"
    
    return pd.DataFrame({
        '項目': ["分析日時", "分析期間", "初期資金", "トレード毎リスク", "手数料", "スリッページ", "戦略名", "エントリーロジック", "損切りロジック", "利確ロジック", "---", "純利益", "総利益", "総損失", "PF", "勝率", "総トレード数", "勝トレード", "負トレード", "平均利益", "平均損失", "RR比"],
        '結果': [datetime.now().strftime('%Y-%m-%d %H:%M'), f"{start_date.strftime('%y/%m/%d')}-{end_date.strftime('%y/%m/%d')}", f"¥{config.INITIAL_CAPITAL:,.0f}", f"{p.get('sizing',{}).get('risk_per_trade',0):.1%}", f"{config.COMMISSION_PERC:.3%}", f"{config.SLIPPAGE_PERC:.3%}", p.get('strategy_name','N/A'), " | ".join(filter(None, [long_c, short_c])), _format_exit_for_report(p.get('exit_conditions',{}).get('stop_loss',{})), tp_desc, "---", f"¥{total_net:,.0f}", f"¥{total_won:,.0f}", f"¥{total_lost:,.0f}", f"{pf:.2f}", f"{win_rate:.2f}%", total_trades, total_win, total_trades-total_win, f"¥{avg_profit:,.0f}", f"¥{avg_loss:,.0f}", f"{rr:.2f}"],
    })