import os
import glob
import pandas as pd
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

def get_strategy_name_from_summary(summary_file_path, default_name="Unknown"):
    """サマリーファイルから元の戦略名を取得するヘルパー関数。"""
    try:
        if os.path.exists(summary_file_path):
            summary_df = pd.read_csv(summary_file_path)
            return summary_df.set_index('項目')['結果'].get("戦略名", default_name)
    except Exception as e:
        logger.error(f"サマリーファイル '{summary_file_path}' の読み込み中にエラー: {e}")
    return default_name

def aggregate_summaries(results_dir, timestamp):
    """
    全戦略のサマリーレポートを一つのファイルに統合します。
    """
    logging.info("--- 統合サマリーレポートの生成を開始 ---")
    summary_files = glob.glob(os.path.join(results_dir, "**", "summary.csv"), recursive=True)

    if not summary_files:
        logging.warning("サマリーファイルが見つかりません。")
        return

    all_summaries = []
    report_columns = [
        "戦略名", "純利益", "総利益", "総損失", "PF", "勝率",
        "総トレード数", "勝トレード", "負トレード", "平均利益", "平均損失", "RR比"
    ]

    for f in summary_files:
        try:
            df = pd.read_csv(f)
            series = df.set_index('項目')['結果']
            summary_data = {col: series.get(col, "N/A") for col in report_columns}
            all_summaries.append(summary_data)
        except Exception as e:
            logging.error(f"ファイル '{f}' の処理中にエラー: {e}")

    if not all_summaries:
        logging.warning("有効なサマリーデータがありませんでした。")
        return

    summary_df = pd.DataFrame(all_summaries)
    numeric_cols = [col for col in report_columns if col != "戦略名"]
    for col in numeric_cols:
        if col in summary_df.columns:
            summary_df[col] = summary_df[col].astype(str).str.replace(r'[¥,%]', '', regex=True)
            summary_df[col] = pd.to_numeric(summary_df[col], errors='coerce')

    summary_df = summary_df.sort_values(by="純利益", ascending=False).reset_index(drop=True)
    
    output_filename = f"all_summary_{timestamp}.csv"
    output_path = os.path.join(results_dir, output_filename)

    try:
        summary_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"統合サマリーレポートを '{output_path}' に保存しました。")
    except IOError as e:
        logging.error(f"統合サマリーレポートの保存に失敗しました: {e}")

def aggregate_details(results_dir, timestamp):
    """
    全戦略の銘柄別詳細レポートを一つのファイルに統合します。
    """
    logging.info("--- 全銘柄別詳細レポートの生成を開始 ---")
    detail_files = glob.glob(os.path.join(results_dir, "**", "detail.csv"), recursive=True)

    if not detail_files:
        logging.warning("詳細レポートファイルが見つかりません。")
        return None

    all_details_list = []
    for f in detail_files:
        try:
            # [修正] サマリーファイルから元の戦略名を取得
            summary_path = os.path.join(os.path.dirname(f), 'summary.csv')
            strategy_name = get_strategy_name_from_summary(summary_path, os.path.basename(os.path.dirname(f)))
            
            detail_df = pd.read_csv(f)
            detail_df.insert(0, '戦略名', strategy_name)
            all_details_list.append(detail_df)
        except Exception as e:
            logging.error(f"詳細レポートファイル '{f}' の処理中にエラー: {e}")

    if not all_details_list:
        logging.warning("有効な詳細レポートデータがありませんでした。")
        return None

    combined_details_df = pd.concat(all_details_list, ignore_index=True)
    output_filename = f"all_detail_{timestamp}.csv"
    output_path = os.path.join(results_dir, output_filename)

    try:
        combined_details_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"全銘柄別詳細レポートを '{output_path}' に保存しました。")
        return output_path
    except IOError as e:
        logging.error(f"全銘柄別詳細レポートの保存に失敗しました: {e}")
        return None

def aggregate_trade_histories(results_dir, timestamp):
    """
    全戦略のトレード履歴を一つのファイルに統合します。
    """
    logging.info("--- 全トレード履歴レポートの生成を開始 ---")
    history_files = glob.glob(os.path.join(results_dir, "**", "trade_history.csv"), recursive=True)

    if not history_files:
        logging.warning("トレード履歴ファイルが見つかりません。")
        return

    all_trades_list = []
    for f in history_files:
        try:
            # [修正] サマリーファイルから元の戦略名を取得
            summary_path = os.path.join(os.path.dirname(f), 'summary.csv')
            strategy_name = get_strategy_name_from_summary(summary_path, os.path.basename(os.path.dirname(f)))

            trade_df = pd.read_csv(f)
            trade_df.insert(0, '戦略名', strategy_name)
            all_trades_list.append(trade_df)
        except Exception as e:
            logging.error(f"トレード履歴ファイル '{f}' の処理中にエラー: {e}")

    if not all_trades_list:
        logging.warning("有効なトレード履歴データがありませんでした。")
        return

    combined_trades_df = pd.concat(all_trades_list, ignore_index=True)
    output_filename = f"all_trade_history_{timestamp}.csv"
    output_path = os.path.join(results_dir, output_filename)

    try:
        combined_trades_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"全トレード履歴レポートを '{output_path}' に保存しました。")
    except IOError as e:
        logging.error(f"全トレード履歴レポートの保存に失敗しました: {e}")

def create_recommend_report(all_detail_report_path, results_dir, timestamp):
    """
    全詳細レポートから、各銘柄で最も純利益が高かった戦略を抽出します。
    """
    logging.info("--- 銘柄別推奨戦略レポートの生成を開始 ---")
    if not all_detail_report_path or not os.path.exists(all_detail_report_path):
        logging.warning("全詳細レポートファイルが見つからないため、推奨レポートは生成できません。")
        return

    try:
        df = pd.read_csv(all_detail_report_path)
        df['純利益_数値'] = df['純利益'].astype(str).str.replace(r'[¥,]', '', regex=True)
        df['純利益_数値'] = pd.to_numeric(df['純利益_数値'], errors='coerce')
        
        best_indices = df.groupby('銘柄')['純利益_数値'].idxmax()
        recommend_df = df.loc[best_indices].drop(columns=['純利益_数値'])

        output_filename = f"all_recommend_{timestamp}.csv"
        output_path = os.path.join(results_dir, output_filename)
        
        recommend_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"銘柄別推奨戦略レポートを '{output_path}' に保存しました。")
    except Exception as e:
        logging.error(f"推奨レポートの生成中にエラーが発生しました: {e}")

def aggregate_all(results_dir, timestamp):
    """
    全ての集計処理を実行します。
    """
    aggregate_summaries(results_dir, timestamp)
    all_detail_path = aggregate_details(results_dir, timestamp)
    aggregate_trade_histories(results_dir, timestamp)
    create_recommend_report(all_detail_path, results_dir, timestamp)