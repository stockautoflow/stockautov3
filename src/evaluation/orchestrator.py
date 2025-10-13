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

# ▼▼▼【変更箇所】▼▼▼
# [リファクタリング] 新しいパッケージ構造に合わせてインポートを変更
from . import aggregator
from . import config_evaluation as config # evaluation専用設定をインポート
# ▲▲▲【変更箇所ここまで】▲▲▲

# --- 定数定義 ---
STRATEGY_CATALOG_FILE = 'config/strategy_catalog.yml'
BASE_STRATEGY_FILE = 'config/strategy_base.yml'
BACKTEST_CONFIG_FILE = 'src/backtest/config_backtest.py' # <-- [追加]
RESULTS_ROOT_DIR = 'results/evaluation'
BACKTEST_REPORT_DIR = 'results/backtest'


def run_single_backtest(strategy_def, base_config):
    """
    単一の戦略でバックテストを実行します。
    設定ファイルを一時的に書き換え、実行後に必ず元の状態に戻します。
    """
    strategy_name = strategy_def.get('name', 'Unnamed Strategy')
    logging.info(f"--- 戦略 '{strategy_name}' のバックテストを開始 ---")

    if strategy_def.get('unsupported'):
        logging.warning(f"戦略 '{strategy_name}' は未サポートのためスキップします。理由: {strategy_def.get('reason', 'N/A')}")
        return False

    # ▼▼▼【変更箇所: 全面的なロジック変更】▼▼▼
    original_strategy_content = None
    original_backtest_config_content = None

    try:
        # --- 1. 元の設定ファイルを読み込んで保持 ---
        # a) 戦略ファイル
        with open(BASE_STRATEGY_FILE, 'r', encoding='utf-8') as f:
            original_strategy_content = f.read()
        # b) バックテスト設定ファイル
        with open(BACKTEST_CONFIG_FILE, 'r', encoding='utf-8') as f:
            original_backtest_config_content = f.readlines()

        # --- 2. 設定ファイルを一時的に上書き ---
        # a) 戦略ファイルを今回の戦略内容で上書き
        current_config = base_config.copy()
        current_config['strategy_name'] = strategy_name
        current_config['entry_conditions'] = strategy_def.get('entry_conditions')
        with open(BASE_STRATEGY_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        # b) バックテスト設定ファイルのログレベルを上書き
        level_override = config.BACKTEST_LOG_LEVEL_OVERRIDE
        new_line = f"LOG_LEVEL = None\n" if level_override == 'NONE' else f"LOG_LEVEL = logging.{level_override}\n"
        
        modified_config = []
        for line in original_backtest_config_content:
            if line.strip().startswith('LOG_LEVEL ='):
                modified_config.append(new_line)
            else:
                modified_config.append(line)
        
        with open(BACKTEST_CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.writelines(modified_config)
        logging.info(f"バックテストのログレベルを '{level_override}' に一時変更しました。")

        # --- 3. バックテストのサブプロセスを実行 ---
        logging.info("'run_backtest'モジュールを実行します...")
        python_executable = sys.executable
        result = subprocess.run(
            [python_executable, '-m', 'src.backtest.run_backtest'],
            check=True, text=True, encoding=sys.stdout.encoding, errors='replace',
            capture_output=True
        )

        if result.stdout: logging.info(f"--- 'run_backtest' の出力 ---\n{result.stdout.strip()}")
        logging.info("'run_backtest' が正常に完了しました。")
        return True

    except Exception as e:
        logging.error(f"バックテスト実行中にエラーが発生: {e}", exc_info=True)
        if isinstance(e, subprocess.CalledProcessError):
            if e.stdout: logging.error(f"--- STDOUT ---\n{e.stdout.strip()}")
            if e.stderr: logging.error(f"--- STDERR ---\n{e.stderr.strip()}")
        return False
    
    finally:
        # --- 4. 必ず元のファイル内容に復元 ---
        if original_strategy_content is not None:
            with open(BASE_STRATEGY_FILE, 'w', encoding='utf-8') as f:
                f.write(original_strategy_content)
        if original_backtest_config_content is not None:
            with open(BACKTEST_CONFIG_FILE, 'w', encoding='utf-8') as f:
                f.writelines(original_backtest_config_content)
            logging.info(f"'{BACKTEST_CONFIG_FILE}' を元の状態に復元しました。")
    # ▲▲▲【変更箇所ここまで】▲▲▲


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
    
    # ▼▼▼【変更箇所: ロガー初期化呼び出しを削除】▼▼▼
    # logger_setup.setup_logging('log', log_prefix='evaluation') # この行はrun_evaluation.pyに移動
    # ▲▲▲【変更箇所ここまで】▲▲▲

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

    # [修正] strategy_base.ymlの復元ロジックはrun_single_backtestに移動したため、ここからは削除
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
    
    aggregator.aggregate_all(current_results_dir, timestamp)
    logging.info("全ての戦略の評価が完了しました。")