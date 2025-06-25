# ==============================================================================
# ファイル: run_all_strategies.py
# 説明: 'strategies.yml'から全戦略を読み込み、自動的にバックテストを実行します。
# 作成日: 2023-10-27
# バージョン: 7.0
# 主な変更点:
#   - 各銘柄で最も純利益が高かった戦略を抽出する「推奨レポート」機能を追加。
# ==============================================================================

import os
import re
import sys
import yaml
import subprocess
import shutil
import glob
from datetime import datetime
import pandas as pd
import logging
import time

# --- 定数定義 ---
STRATEGIES_YML_FILE = 'strategies.yml'
BASE_STRATEGY_YML = 'strategy.yml'

# 出力ディレクトリとファイル
RESULTS_ROOT_DIR = 'all_strategies_results'
BACKTEST_REPORT_DIR = os.path.join('backtest_results', 'report')
FINAL_SUMMARY_PREFIX = 'all_summary'
FINAL_TRADE_HISTORY_PREFIX = 'all_trade_history'
FINAL_DETAIL_PREFIX = 'all_detail'
# [新規追加] 推奨レポートのファイル名プレフィックス
FINAL_RECOMMEND_PREFIX = 'all_recommend'


def setup_logging(log_dir, timestamp):
    """
    ファイルとコンソールの両方に出力するロギングを設定します。
    """
    log_filename = f"run_all_strategies_{timestamp}.log"
    log_filepath = os.path.join(log_dir, log_filename)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logging.info(f"ログファイルが '{log_filepath}' に設定されました。")


def load_strategies_from_yaml(filepath):
    """
    YAMLファイルから戦略のリストを読み込みます。
    """
    logging.info(f"'{filepath}' から戦略定義を読み込んでいます...")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            strategies = yaml.safe_load(f)
        logging.info(f"{len(strategies)} 件の戦略を正常に読み込みました。")
        return strategies
    except FileNotFoundError:
        logging.error(f"エラー: 戦略定義ファイル '{filepath}' が見つかりません。")
        return []
    except yaml.YAMLError as e:
        logging.error(f"'{filepath}' のYAML解析中にエラーが発生しました: {e}")
        return []


def run_single_backtest(strategy_def, base_config):
    """
    単一の戦略でバックテストを実行します。
    """
    strategy_name = strategy_def.get('name', 'Unnamed Strategy')
    logging.info(f"--- 戦略 '{strategy_name}' のバックテストを開始 ---")

    if strategy_def.get('unsupported'):
        logging.warning(f"戦略 '{strategy_name}' は未サポートのためスキップします。理由: {strategy_def.get('reason', 'N/A')}")
        return False

    current_config = base_config.copy()
    current_config['strategy_name'] = strategy_name
    current_config['entry_conditions'] = strategy_def.get('entry_conditions')

    try:
        with open(BASE_STRATEGY_YML, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logging.info(f"'{BASE_STRATEGY_YML}' を '{strategy_name}' の設定で更新しました。")
    except IOError as e:
        logging.error(f"'{BASE_STRATEGY_YML}' の書き込みに失敗しました: {e}")
        return False

    try:
        logging.info("'run_backtrader.py' を実行します...")
        python_executable = sys.executable
        result = subprocess.run(
            [python_executable, 'run_backtrader.py'],
            check=True, text=True, encoding=sys.stdout.encoding, errors='replace',
            capture_output=True
        )

        if result.stdout:
            logging.info(f"--- 'run_backtrader.py' の出力 ---\n{result.stdout.strip()}")

        logging.info("'run_backtrader.py' が正常に完了しました。")
        return True

    except FileNotFoundError:
        logging.error(f"エラー: Python実行ファイル '{python_executable}' が見つかりません。")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"'run_backtrader.py' の実行に失敗しました。リターンコード: {e.returncode}")
        if e.stdout:
            logging.error(f"--- 'run_backtrader.py' の標準出力 ---\n{e.stdout.strip()}")
        if e.stderr:
            logging.error(f"--- 'run_backtrader.py' の標準エラー出力 ---\n{e.stderr.strip()}")
        return False


def move_and_rename_reports(strategy_result_dir):
    """
    生成された最新のレポートファイルを戦略ごとのディレクトリに移動・リネームします。
    """
    report_types = ['summary', 'detail', 'trade_history']
    for report_type in report_types:
        try:
            search_pattern = os.path.join(BACKTEST_REPORT_DIR, f"{report_type}_*.csv")
            list_of_files = glob.glob(search_pattern)
            if not list_of_files:
                logging.warning(f"警告: '{report_type}' のレポートファイルが見つかりません。")
                continue

            latest_file = max(list_of_files, key=os.path.getctime)
            destination_path = os.path.join(strategy_result_dir, f"{report_type}.csv")

            for _ in range(3):
                try:
                    shutil.move(latest_file, destination_path)
                    logging.info(f"'{os.path.basename(latest_file)}' を '{destination_path}' に移動しました。")
                    break
                except PermissionError:
                    logging.warning(f"'{latest_file}' の移動に失敗しました。0.5秒待機してリトライします。")
                    time.sleep(0.5)
            else:
                logging.error(f"'{latest_file}' の移動に失敗しました。ファイルが他のプロセスによって使用されている可能性があります。")

        except Exception as e:
            logging.error(f"レポートファイル '{report_type}' の移動中に予期せぬエラーが発生しました: {e}")


def create_summary_report(results_dir, timestamp):
    """
    全戦略の結果をまとめた統合サマリーレポートを生成します。
    """
    logging.info("--- 統合サマリーレポートの生成を開始 ---")
    summary_files = glob.glob(os.path.join(results_dir, "**", "summary.csv"), recursive=True)

    if not summary_files:
        logging.warning("警告: サマリーファイルが見つかりません。統合レポートは生成されません。")
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

            summary_data = {}
            for col in report_columns:
                if col == "戦略名":
                    summary_data[col] = series.get("戦略名", os.path.basename(os.path.dirname(f)))
                else:
                    summary_data[col] = series.get(col, "N/A")

            all_summaries.append(summary_data)
        except Exception as e:
            logging.error(f"ファイル '{f}' の処理中にエラー: {e}")

    if not all_summaries:
        logging.warning("警告: 有効なサマリーデータがありませんでした。")
        return

    summary_df = pd.DataFrame(all_summaries)
    numeric_cols = [col for col in report_columns if col != "戦略名"]
    for col in numeric_cols:
        if col in summary_df.columns:
            summary_df[col] = summary_df[col].astype(str).str.replace(r'[¥,%]', '', regex=True)
            summary_df[col] = pd.to_numeric(summary_df[col], errors='coerce')

    summary_df = summary_df.sort_values(by="純利益", ascending=False).reset_index(drop=True)
    
    formatted_timestamp = timestamp.replace('_', '-')
    output_filename = f"{FINAL_SUMMARY_PREFIX}_{formatted_timestamp}.csv"
    output_path = os.path.join(results_dir, output_filename)

    try:
        summary_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"統合サマリーレポートを '{output_path}' に保存しました。")
    except IOError as e:
        logging.error(f"統合サマリーレポートの保存に失敗しました: {e}")


def create_trade_history_report(results_dir, timestamp):
    """
    全戦略のトレード履歴を一つのファイルに統合して出力します。
    """
    logging.info("--- 全トレード履歴レポートの生成を開始 ---")
    history_files = glob.glob(os.path.join(results_dir, "**", "trade_history.csv"), recursive=True)

    if not history_files:
        logging.warning("警告: トレード履歴ファイルが見つかりません。全トレード履歴レポートは生成されません。")
        return

    all_trades_list = []
    for f in history_files:
        try:
            strategy_dir = os.path.dirname(f)
            summary_path = os.path.join(strategy_dir, 'summary.csv')
            
            strategy_name = "Unknown Strategy"
            if os.path.exists(summary_path):
                summary_df = pd.read_csv(summary_path)
                summary_series = summary_df.set_index('項目')['結果']
                strategy_name = summary_series.get("戦略名", os.path.basename(strategy_dir))
            else:
                 strategy_name = os.path.basename(strategy_dir)

            trade_df = pd.read_csv(f)
            trade_df.insert(0, '戦略名', strategy_name)
            all_trades_list.append(trade_df)

        except Exception as e:
            logging.error(f"トレード履歴ファイル '{f}' の処理中にエラー: {e}")

    if not all_trades_list:
        logging.warning("警告: 有効なトレード履歴データがありませんでした。")
        return

    combined_trades_df = pd.concat(all_trades_list, ignore_index=True)
    
    formatted_timestamp = timestamp.replace('_', '-')
    output_filename = f"{FINAL_TRADE_HISTORY_PREFIX}_{formatted_timestamp}.csv"
    output_path = os.path.join(results_dir, output_filename)

    try:
        combined_trades_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"全トレード履歴レポートを '{output_path}' に保存しました。")
    except IOError as e:
        logging.error(f"全トレード履歴レポートの保存に失敗しました: {e}")


def create_detail_report(results_dir, timestamp):
    """
    全戦略の銘柄別詳細レポートを一つのファイルに統合して出力します。
    """
    logging.info("--- 全銘柄別詳細レポートの生成を開始 ---")
    detail_files = glob.glob(os.path.join(results_dir, "**", "detail.csv"), recursive=True)

    if not detail_files:
        logging.warning("警告: 詳細レポートファイルが見つかりません。全詳細レポートは生成されません。")
        return None # 後続の処理で使うためNoneを返す

    all_details_list = []
    for f in detail_files:
        try:
            strategy_dir = os.path.dirname(f)
            summary_path = os.path.join(strategy_dir, 'summary.csv')

            strategy_name = "Unknown Strategy"
            if os.path.exists(summary_path):
                summary_df = pd.read_csv(summary_path)
                summary_series = summary_df.set_index('項目')['結果']
                strategy_name = summary_series.get("戦略名", os.path.basename(strategy_dir))
            else:
                 strategy_name = os.path.basename(strategy_dir)

            detail_df = pd.read_csv(f)
            detail_df.insert(0, '戦略名', strategy_name)
            all_details_list.append(detail_df)

        except Exception as e:
            logging.error(f"詳細レポートファイル '{f}' の処理中にエラー: {e}")

    if not all_details_list:
        logging.warning("警告: 有効な詳細レポートデータがありませんでした。")
        return None

    combined_details_df = pd.concat(all_details_list, ignore_index=True)
    
    formatted_timestamp = timestamp.replace('_', '-')
    output_filename = f"{FINAL_DETAIL_PREFIX}_{formatted_timestamp}.csv"
    output_path = os.path.join(results_dir, output_filename)

    try:
        combined_details_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"全銘柄別詳細レポートを '{output_path}' に保存しました。")
        return output_path # 後続処理のためにファイルパスを返す
    except IOError as e:
        logging.error(f"全銘柄別詳細レポートの保存に失敗しました: {e}")
        return None


# [新規追加] 銘柄別推奨戦略レポートを生成する関数
def create_recommend_report(all_detail_report_path, results_dir, timestamp):
    """
    全詳細レポートから、各銘柄で最も純利益が高かった戦略を抽出します。
    """
    logging.info("--- 銘柄別推奨戦略レポートの生成を開始 ---")
    if not all_detail_report_path or not os.path.exists(all_detail_report_path):
        logging.warning("警告: 全詳細レポートファイルが見つからないため、推奨レポートは生成できません。")
        return

    try:
        df = pd.read_csv(all_detail_report_path)
        
        # '純利益' 列を数値に変換
        # 注意: この処理は、上流のレポート生成で ¥ や , が含まれる形式であることを想定
        df['純利益_数値'] = df['純利益'].astype(str).str.replace(r'[¥,]', '', regex=True)
        df['純利益_数値'] = pd.to_numeric(df['純利益_数値'], errors='coerce')

        # 各銘柄で純利益が最大の行のインデックスを取得
        best_indices = df.groupby('銘柄')['純利益_数値'].idxmax()
        
        # 推奨戦略のデータフレームを作成
        recommend_df = df.loc[best_indices].drop(columns=['純利益_数値'])

        # ファイルに保存
        formatted_timestamp = timestamp.replace('_', '-')
        output_filename = f"{FINAL_RECOMMEND_PREFIX}_{formatted_timestamp}.csv"
        output_path = os.path.join(results_dir, output_filename)
        
        recommend_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"銘柄別推奨戦略レポートを '{output_path}' に保存しました。")

    except Exception as e:
        logging.error(f"推奨レポートの生成中にエラーが発生しました: {e}")


def main():
    """
    スクリプトのメイン処理。
    """
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    current_results_dir = os.path.join(RESULTS_ROOT_DIR, timestamp)
    os.makedirs(current_results_dir, exist_ok=True)

    setup_logging(current_results_dir, timestamp)

    logging.info(f"結果保存ディレクトリ: '{current_results_dir}'")

    strategies = load_strategies_from_yaml(STRATEGIES_YML_FILE)
    if not strategies:
        logging.error("戦略が抽出できなかったため、処理を中断します。")
        return

    try:
        with open(BASE_STRATEGY_YML, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"'{BASE_STRATEGY_YML}' が見つかりません。`create_project_files.py` を実行してください。")
        return
    except yaml.YAMLError as e:
        logging.error(f"'{BASE_STRATEGY_YML}' の解析に失敗しました: {e}")
        return

    total_strategies = len(strategies)
    for i, strategy_def in enumerate(strategies):
        strategy_name = strategy_def.get('name', f"Strategy_{i+1}")

        sanitized_name = re.sub(r'[^\w\s-]', '', strategy_name).strip()
        sanitized_name = re.sub(r'[-\s]+', '_', sanitized_name)

        strategy_result_dir_name = f"strategy_{i+1:02d}_{sanitized_name}"
        strategy_result_dir = os.path.join(current_results_dir, strategy_result_dir_name)
        os.makedirs(strategy_result_dir, exist_ok=True)

        logging.info(f"===== 戦略 {i+1}/{total_strategies}: '{strategy_name}' を処理中 =====")

        success = run_single_backtest(strategy_def, base_config)

        if success:
            move_and_rename_reports(strategy_result_dir)
        else:
            logging.error(f"戦略 '{strategy_name}' のバックテストに失敗したため、結果の移動をスキップします。")

    # [変更] レポート生成の順序を整理
    create_summary_report(current_results_dir, timestamp)
    create_trade_history_report(current_results_dir, timestamp)
    # detailレポートはrecommendレポートの生成に必要なので、ファイルパスを受け取る
    all_detail_path = create_detail_report(current_results_dir, timestamp)
    # recommendレポートを生成
    create_recommend_report(all_detail_path, current_results_dir, timestamp)

    logging.info("全ての戦略のバックテストが完了しました。")


if __name__ == '__main__':
    main()
