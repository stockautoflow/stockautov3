# [修正] src/evaluation/aggregator.py (ケリー基準対応版)

import os
import glob
import pandas as pd
import logging
import re
from datetime import datetime
import numpy as np # <-- [追加]
from src.core.util.kelly_criterion import calculate_raw_kelly # <-- [追加]

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
    [修正] ケリー基準 (Raw / Adj) を計算して追加します。
    """
    logging.info("--- 全銘柄別詳細レポートの生成を開始 ---")
    strategy_dirs = [d for d in glob.glob(os.path.join(results_dir, "strategy_*")) if os.path.isdir(d)]
    
    if not strategy_dirs:
        logging.warning("評価結果が格納された戦略ディレクトリが見つかりません。")
        return None

    all_details_list = []
    for strategy_dir in strategy_dirs:
        try:
            strategy_name = "Unknown"
            summary_path = os.path.join(strategy_dir, 'summary.csv')
            if os.path.exists(summary_path):
                strategy_name = get_strategy_name_from_summary(summary_path, os.path.basename(strategy_dir))

            detail_path = os.path.join(strategy_dir, 'detail.csv')
            history_path = os.path.join(strategy_dir, 'trade_history.csv')

            detail_df = pd.DataFrame()
            if os.path.exists(detail_path):
                try:
                    detail_df = pd.read_csv(detail_path)
                    if not detail_df.empty:
                        detail_df.insert(0, '戦略名', strategy_name)
                        
                        # --- ▼▼▼ 挿入ブロック START (設計 1.3.3 - 2, 3) ▼▼▼
                        
                        # 1.3.3 - 2: Kelly_Raw カラムを生成
                        if '勝率' in detail_df.columns and 'RR比' in detail_df.columns:
                            detail_df['Kelly_Raw'] = detail_df.apply(
                                lambda row: calculate_raw_kelly(row['勝率'], row['RR比']),
                                axis=1
                            )
                        else:
                            detail_df['Kelly_Raw'] = np.nan

                        # 1.3.3 - 3: Kelly_Adj カラムを生成 (仕様 1.3.2準拠)
                        def calculate_adjusted_kelly(kelly_raw):
                            if pd.isna(kelly_raw) or kelly_raw < 0.05:
                                return 0.0  # 0%
                            elif kelly_raw < 0.15:
                                return 0.05 # 5%
                            else:
                                return 0.10 # 10%
                        
                        detail_df['Kelly_Adj'] = detail_df['Kelly_Raw'].apply(calculate_adjusted_kelly)
                        
                        # --- ▲▲▲ 挿入ブロック END ▲▲▲ ---

                except pd.errors.EmptyDataError:
                    logging.warning(f"詳細レポートファイルが空です: {detail_path}")
                except Exception as e:
                    logging.error(f"詳細レポートファイル '{detail_path}' の読み込み中にエラー: {e}")

            # トレード履歴があり、詳細集計にない銘柄を検出
            if os.path.exists(history_path):
                try:
                    history_df = pd.read_csv(history_path)
                    if not history_df.empty:
                        traded_symbols = set(history_df['銘柄'].astype(str))
                        detailed_symbols = set()
                        if not detail_df.empty:
                            detailed_symbols = set(detail_df['銘柄'].astype(str))
                        
                        missing_symbols = traded_symbols - detailed_symbols
                        
                        if missing_symbols:
                            logging.warning(f"戦略 '{strategy_name}' で集計漏れの銘柄を検出: {missing_symbols}")
                            for symbol in missing_symbols:
                                # 5. 欠損値対応 (設計 1.3.3 - 4)
                                missing_row = {
                                    "戦略名": strategy_name,
                                    "銘柄": symbol,
                                    "純利益": "集計エラー",
                                    "総トレード数": len(history_df[history_df['銘柄'].astype(str) == symbol]),
                                    "Kelly_Raw": np.nan,  # <-- [追加]
                                    "Kelly_Adj": np.nan   # <-- [追加]
                                }
                                temp_df = pd.DataFrame([missing_row])
                                detail_df = pd.concat([detail_df, temp_df], ignore_index=True)

                except Exception as e:
                    logging.error(f"トレード履歴ファイル '{history_path}' の処理中にエラー: {e}")

            if not detail_df.empty:
                all_details_list.append(detail_df)

        except Exception as e:
            logging.error(f"戦略ディレクトリ '{strategy_dir}' の処理中に予期せぬエラー: {e}")

    if not all_details_list:
        logging.warning("有効な詳細レポートデータがありませんでした。")
        return None

    combined_details_df = pd.concat(all_details_list, ignore_index=True)

    # --- ▼▼▼ 挿入ブロック START (設計 1.3.3 - 5) ▼▼▼ ---
    # 1.3.3 - 5: 出力フォーマットの指定 (仕様 1.3.2準拠)
    if 'Kelly_Raw' in combined_details_df.columns:
        combined_details_df['Kelly_Raw'] = combined_details_df['Kelly_Raw'].apply(
            lambda x: f"{x:.4f}" if pd.notna(x) else "N/A"
        )
    if 'Kelly_Adj' in combined_details_df.columns:
        combined_details_df['Kelly_Adj'] = combined_details_df['Kelly_Adj'].apply(
            lambda x: f"{x:.4f}" if pd.notna(x) else "N/A"
        )
    # --- ▲▲▲ 挿入ブロック END ▲▲▲ ---

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
            summary_path = os.path.join(os.path.dirname(f), 'summary.csv')
            strategy_name = get_strategy_name_from_summary(summary_path, os.path.basename(os.path.dirname(f)))

            trade_df = pd.read_csv(f)
            if trade_df.empty:
                logging.info(f"トレード履歴ファイルが空のためスキップ: {f}")
                continue

            trade_df.insert(0, '戦略名', strategy_name)
            all_trades_list.append(trade_df)
        except pd.errors.EmptyDataError:
            logging.warning(f"トレード履歴ファイルが空です: {f}")
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
        # '純利益' カラムに数値でない値が含まれる可能性があるため、エラーを無視して数値に変換
        df['純利益_数値'] = df['純利益'].astype(str).str.replace(r'[¥,]', '', regex=True)
        df['純利益_数値'] = pd.to_numeric(df['純利益_数値'], errors='coerce')
        
        # 数値に変換できた行のみを対象にする
        df_numeric = df.dropna(subset=['純利益_数値'])
        if df_numeric.empty:
            logging.warning("有効な純利益データがないため、推奨レポートは生成できません。")
            return

        best_indices = df_numeric.groupby('銘柄')['純利益_数値'].idxmax()
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