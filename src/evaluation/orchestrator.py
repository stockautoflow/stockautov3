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
            logging.info(f"--- 'run_backtest' の出力 ---\n{result.stdout.strip()}")

        logging.info("'run_backtest' が正常に完了しました。")
        return True

    except FileNotFoundError:
        logging.error(f"エラー: Python実行ファイル '{python_executable}' が見つかりません。")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"'run_backtest' の実行に失敗しました。リターンコード: {e.returncode}")
        if e.stdout:
            logging.error(f"--- 'run_backtest' の標準出力 ---\n{e.stdout.strip()}")
        if e.stderr:
            logging.error(f"--- 'run_backtest' の標準エラー出力 ---\n{e.stderr.strip()}")
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
                logging.error(f"'{latest_file}' の移動に失敗しました。")

        except Exception as e:
            logging.error(f"レポートファイル '{report_type}' の移動中に予期せぬエラーが発生しました: {e}")


def main():
    """
    スクリプトのメイン処理。
    """
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
            sanitized_name = re.sub(r'[^\w\s-]', '', strategy_name).strip().replace(' ', '_')
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