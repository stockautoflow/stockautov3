import os
import sys

# ==============================================================================
# ファイル: create_evaluation.py
# 説明: リファクタリング計画に基づき、全戦略の評価と集計を行う`evaluation`パッケージを生成します。
#       このスクリプトは、リファクタリングのフェーズ2.2で一度だけ実行することを想定しています。
# 実行方法: python create_evaluation.py
# Ver. 00-02
# ==============================================================================

project_files = {
    # パッケージ初期化ファイル
    "src/evaluation/__init__.py": "",

    # 実行スクリプト
    "src/evaluation/run_evaluation.py": """
import sys
import os

# ------------------------------------------------------------------------------
# このスクリプトを直接実行することで、全戦略の評価プロセスを開始します。
# `python -m src.evaluation.run_evaluation`
# ------------------------------------------------------------------------------

# プロジェクトのルートディレクトリをPythonのパスに追加
# これにより、`src`パッケージ内のモジュールを正しくインポートできます。
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.evaluation.orchestrator import main

if __name__ == '__main__':
    main()
""",

    # 全戦略の実行管理モジュール
    "src/evaluation/orchestrator.py": """
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

# [リファクタリング] 新しいパッケージ構造に合わせてインポートを変更
from src.core.util import logger as logger_setup
from . import aggregator

# --- 定数定義 ---
# [リファクタリング] 設定ファイルのパスを修正
STRATEGY_CATALOG_FILE = 'config/strategy_catalog.yml'
BASE_STRATEGY_FILE = 'config/strategy_base.yml'

# [リファクタリング] 結果の保存先ディレクトリを変更
RESULTS_ROOT_DIR = 'results/evaluation'
# [リファクタリング] 個別バックテストのレポートパスを変更
BACKTEST_REPORT_DIR = 'results/backtest'


def run_single_backtest(strategy_def, base_config):
    \"\"\"
    単一の戦略でバックテストを実行します。
    \"\"\"
    strategy_name = strategy_def.get('name', 'Unnamed Strategy')
    logging.info(f"--- 戦略 '{strategy_name}' のバックテストを開始 ---")

    if strategy_def.get('unsupported'):
        logging.warning(f"戦略 '{strategy_name}' は未サポートのためスキップします。理由: {strategy_def.get('reason', 'N/A')}")
        return False

    current_config = base_config.copy()
    current_config['strategy_name'] = strategy_name
    current_config['entry_conditions'] = strategy_def.get('entry_conditions')

    try:
        # ベース設定ファイルを現在評価中の戦略で一時的に上書き
        with open(BASE_STRATEGY_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logging.info(f"'{BASE_STRATEGY_FILE}' を '{strategy_name}' の設定で更新しました。")
    except IOError as e:
        logging.error(f"'{BASE_STRATEGY_FILE}' の書き込みに失敗しました: {e}")
        return False

    try:
        logging.info("'run_backtest'モジュールを実行します...")
        python_executable = sys.executable
        result = subprocess.run(
            [python_executable, '-m', 'src.backtest.run_backtest'],
            check=True, text=True, encoding=sys.stdout.encoding, errors='replace',
            capture_output=True
        )

        if result.stdout:
            logging.info(f"--- 'run_backtest' の出力 ---\\n{result.stdout.strip()}")

        logging.info("'run_backtest' が正常に完了しました。")
        return True

    except FileNotFoundError:
        logging.error(f"エラー: Python実行ファイル '{python_executable}' が見つかりません。")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"'run_backtest' の実行に失敗しました。リターンコード: {e.returncode}")
        if e.stdout:
            logging.error(f"--- 'run_backtest' の標準出力 ---\\n{e.stdout.strip()}")
        if e.stderr:
            logging.error(f"--- 'run_backtest' の標準エラー出力 ---\\n{e.stderr.strip()}")
        return False


def move_and_rename_reports(strategy_result_dir):
    \"\"\"
    生成された最新のレポートファイルを戦略ごとのディレクトリに移動・リネームします。
    \"\"\"
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
                logging.error(f"'{latest_file}' の移動に失敗しました。")

        except Exception as e:
            logging.error(f"レポートファイル '{report_type}' の移動中に予期せぬエラーが発生しました: {e}")


def main():
    \"\"\"
    スクリプトのメイン処理。
    \"\"\"
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    current_results_dir = os.path.join(RESULTS_ROOT_DIR, timestamp)
    os.makedirs(current_results_dir, exist_ok=True)

    logger_setup.setup_logging('log', log_prefix='evaluation')

    logging.info(f"結果保存ディレクトリ: '{current_results_dir}'")

    try:
        with open(STRATEGY_CATALOG_FILE, 'r', encoding='utf-8') as f:
            strategies = yaml.safe_load(f)
        logging.info(f"{len(strategies)} 件の戦略を '{STRATEGY_CATALOG_FILE}' から正常に読み込みました。")
    except Exception as e:
        logging.error(f"'{STRATEGY_CATALOG_FILE}' の読み込みに失敗しました: {e}")
        return

    try:
        with open(BASE_STRATEGY_FILE, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f)
    except Exception as e:
        logging.error(f"'{BASE_STRATEGY_FILE}' の読み込みに失敗しました: {e}")
        return

    original_base_config_content = ""
    try:
        with open(BASE_STRATEGY_FILE, 'r', encoding='utf-8') as f:
            original_base_config_content = f.read()

        total_strategies = len(strategies)
        for i, strategy_def in enumerate(strategies):
            strategy_name = strategy_def.get('name', f"Strategy_{i+1}")
            sanitized_name = re.sub(r'[^\\w\\s-]', '', strategy_name).strip().replace(' ', '_')
            strategy_result_dir = os.path.join(current_results_dir, f"strategy_{i+1:02d}_{sanitized_name}")
            os.makedirs(strategy_result_dir, exist_ok=True)

            logging.info(f"===== 戦略 {i+1}/{total_strategies}: '{strategy_name}' を処理中 =====")
            success = run_single_backtest(strategy_def, base_config)
            if success:
                move_and_rename_reports(strategy_result_dir)
            else:
                logging.error(f"戦略 '{strategy_name}' のバックテストに失敗したため、結果の移動をスキップします。")
    
    finally:
        if original_base_config_content:
            with open(BASE_STRATEGY_FILE, 'w', encoding='utf-8') as f:
                f.write(original_base_config_content)
            logging.info(f"'{BASE_STRATEGY_FILE}' を元の状態に復元しました。")

    aggregator.aggregate_all(current_results_dir, timestamp)
    logging.info("全ての戦略の評価が完了しました。")
""",

    # レポート集計モジュール
    "src/evaluation/aggregator.py": """
import os
import glob
import pandas as pd
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

def get_strategy_name_from_summary(summary_file_path, default_name="Unknown"):
    \"\"\"サマリーファイルから元の戦略名を取得するヘルパー関数。\"\"\"
    try:
        if os.path.exists(summary_file_path):
            summary_df = pd.read_csv(summary_file_path)
            return summary_df.set_index('項目')['結果'].get("戦略名", default_name)
    except Exception as e:
        logger.error(f"サマリーファイル '{summary_file_path}' の読み込み中にエラー: {e}")
    return default_name

def aggregate_summaries(results_dir, timestamp):
    \"\"\"
    全戦略のサマリーレポートを一つのファイルに統合します。
    \"\"\"
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
    \"\"\"
    全戦略の銘柄別詳細レポートを一つのファイルに統合します。
    \"\"\"
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
    \"\"\"
    全戦略のトレード履歴を一つのファイルに統合します。
    \"\"\"
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
    \"\"\"
    全詳細レポートから、各銘柄で最も純利益が高かった戦略を抽出します。
    \"\"\"
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
    \"\"\"
    全ての集計処理を実行します。
    \"\"\"
    aggregate_summaries(results_dir, timestamp)
    all_detail_path = aggregate_details(results_dir, timestamp)
    aggregate_trade_histories(results_dir, timestamp)
    create_recommend_report(all_detail_path, results_dir, timestamp)
"""
}

def create_files(files_dict):
    """
    指定された辞書に基づいてプロジェクトファイルとディレクトリを生成します。
    """
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))

        content = content.strip()
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"  - ファイル作成: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- 5. evaluationパッケージの生成を開始します ---")
    create_files(project_files)
    print("evaluationパッケージの生成が完了しました。")

