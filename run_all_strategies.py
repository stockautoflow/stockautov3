# ==============================================================================
# ファイル: run_all_strategies.py
# 説明: 'strategies.yml'から全戦略を読み込み、自動的にバックテストを実行します。
# 作成日: 2023-10-27
# バージョン: 3.0 (YAMLファイルベースの読み込みに移行)
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
# [変更] 入力ファイルをYAMLに変更
STRATEGIES_YML_FILE = 'strategies.yml' 
BASE_STRATEGY_YML = 'strategy.yml'

# 出力ディレクトリとファイル
RESULTS_ROOT_DIR = 'all_strategies_results'
BACKTEST_REPORT_DIR = os.path.join('backtest_results', 'report')
FINAL_SUMMARY_FILENAME = 'all_strategies_summary.csv'


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
    
    # 未サポートの戦略はスキップ
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
            
            # [追加] ファイルが使用中でないか確認する簡単なリトライ処理
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


def create_summary_report(results_dir):
    """
    全戦略の結果をまとめた統合サマリーレポートを生成します。
    """
    logging.info("--- 統合サマリーレポートの生成を開始 ---")
    summary_files = glob.glob(os.path.join(results_dir, "**", "summary.csv"), recursive=True)
    
    if not summary_files:
        logging.warning("警告: サマリーファイルが見つかりません。統合レポートは生成されません。")
        return

    all_summaries = []
    for f in summary_files:
        try:
            strategy_name = os.path.basename(os.path.dirname(f))
            df = pd.read_csv(f)
            series = df.set_index('項目')['結果']
            
            summary_data = {
                "Strategy Name": strategy_name,
                "純利益": series.get("純利益", "N/A"),
                "プロフィットファクター": series.get("プロフィットファクター", "N/A"),
                "勝率": series.get("勝率", "N/A"),
                "総トレード数": series.get("総トレード数", "N/A"),
                "リスクリワードレシオ": series.get("リスクリワードレシオ", "N/A"),
                "総利益": series.get("総利益", "N/A"),
                "総損失": series.get("総損失", "N/A"),
            }
            all_summaries.append(summary_data)
        except Exception as e:
            logging.error(f"ファイル '{f}' の処理中にエラー: {e}")

    if not all_summaries:
        logging.warning("警告: 有効なサマリーデータがありませんでした。")
        return

    summary_df = pd.DataFrame(all_summaries)
    
    for col in ["純利益", "プロフィットファクター", "総トレード数", "リスクリワードレシオ", "総利益", "総損失"]:
        if col in summary_df.columns:
            summary_df[col] = summary_df[col].astype(str).str.replace(r'[¥,]', '', regex=True)
            summary_df[col] = pd.to_numeric(summary_df[col], errors='coerce')

    summary_df = summary_df.sort_values(by="純利益", ascending=False).reset_index(drop=True)

    output_path = os.path.join(results_dir, FINAL_SUMMARY_FILENAME)
    try:
        summary_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logging.info(f"統合サマリーレポートを '{output_path}' に保存しました。")
    except IOError as e:
        logging.error(f"統合サマリーレポートの保存に失敗しました: {e}")


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
    
    create_summary_report(current_results_dir)
    
    logging.info("全ての戦略のバックテストが完了しました。")


if __name__ == '__main__':
    main()
