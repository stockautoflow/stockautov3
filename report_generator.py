import pandas as pd
import config_backtrader as config
from datetime import datetime

def generate_report(all_results, strategy_params, start_date, end_date):
    """
    集計結果から詳細なレポートを生成する
    """
    # --- パフォーマンス指標の集計 ---
    total_net_profit = sum(r['pnl_net'] for r in all_results)
    total_gross_won = sum(r['gross_won'] for r in all_results)
    total_gross_lost = sum(r['gross_lost'] for r in all_results)
    total_trades = sum(r['total_trades'] for r in all_results)
    total_win_trades = sum(r['win_trades'] for r in all_results)

    win_rate = (total_win_trades / total_trades) * 100 if total_trades > 0 else 0
    profit_factor = abs(total_gross_won / total_gross_lost) if total_gross_lost != 0 else float('inf')
    avg_profit = total_gross_won / total_win_trades if total_win_trades > 0 else 0
    avg_loss = total_gross_lost / (total_trades - total_win_trades) if (total_trades - total_win_trades) > 0 else 0
    risk_reward_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')

    # --- 評価コメントの生成 ---
    pnl_eval = "プラス。戦略は利益を生んでいますが、他の指標と合わせて総合的に評価する必要があります。" if total_net_profit > 0 else "マイナス。戦略の見直しが必要です。"
    pf_eval = "良好。安定して利益を出せる可能性が高いです。" if profit_factor > 1.3 else "改善の余地あり。1.0以上が必須です。"
    win_rate_eval = f"{win_rate:.2f}% ({total_win_trades}勝 / {total_trades}トレード)"
    rr_eval = "1.0を上回っており、「利大損小」の傾向が見られます。この数値を維持・向上させることが目標です。" if risk_reward_ratio > 1.0 else "1.0を下回っており、「利小損大」の傾向です。決済ルールの見直しが必要です。"

    # --- レポートデータの構築 ---
    sp_desc = strategy_params['descriptions']
    report_data = {
        '項目': [
            "分析対象データ日付", "データ期間", "初期資金", "トレード毎のリスク", "手数料率", "スリッページ",
            "使用戦略", "足種", "環境認識ロジック", "有効なエントリーシグナル", "有効な損切りシグナル", "有効な利確シグナル",
            "---", "純利益", "総利益", "総損失", "プロフィットファクター", "勝率", "総トレード数",
            "勝ちトレード数", "負けトレード数", "平均利益", "平均損失", "リスクリワードレシオ",
            "---", "総損益", "プロフィットファクター (PF)", "勝率", "総トレード数", "リスクリワードレシオ"
        ],
        '結果': [
            datetime.now().strftime('%Y年%m月%d日'),
            f"{start_date.strftime('%Y年%m月%d日 %H:%M')} 〜 {end_date.strftime('%Y年%m月%d日 %H:%M')}",
            f"¥{config.INITIAL_CAPITAL:,.0f}", f"{sp_desc['risk_per_trade']:.1%}",
            f"{config.COMMISSION_PERC:.3%}", f"{config.SLIPPAGE_PERC:.3%}",
            sp_desc['strategy'], sp_desc['timeframe'], sp_desc['environment_logic'],
            sp_desc['entry_signal'], sp_desc['stop_loss_signal'], sp_desc['take_profit_signal'],
            "---",
            f"¥{total_net_profit:,.0f}", f"¥{total_gross_won:,.0f}", f"¥{total_gross_lost:,.0f}",
            f"{profit_factor:.2f}", f"{win_rate:.2f}%", total_trades, total_win_trades,
            total_trades - total_win_trades, f"¥{avg_profit:,.0f}", f"¥{avg_loss:,.0f}",
            f"{risk_reward_ratio:.2f}",
            "---",
            f"{total_net_profit:,.0f}円", f"{profit_factor:.2f}", win_rate_eval,
            f"{total_trades}回", f"{risk_reward_ratio:.2f}"
        ],
        '評価': [
            "", "", "", "", "", "", "", "", "", "", "", "", "---", "", "", "", "", "", "", "", "", "", "", "", "---",
            pnl_eval, pf_eval, "50%を下回っています。エントリーシグナルの精度向上が課題となります。" if win_rate < 50 else "良好。50%以上を維持することが望ましいです。",
            "テスト期間に対して十分な取引機会があったか評価してください。", rr_eval
        ]
    }
    return pd.DataFrame(report_data)
