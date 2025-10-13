import os
import logging

# ==============================================================================
# [リファクタリング]
# プロジェクトルートからの相対パスで各ディレクトリを定義します。
# このファイルが `src/backtest/` に配置されることを想定しています。
# ==============================================================================

# --- ディレクトリ設定 ---
# このファイルの場所からプロジェクトルートを特定
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_DIR = os.path.join(BASE_DIR, 'results', 'backtest') # 個別バックテストの結果保存先
LOG_DIR = os.path.join(BASE_DIR, 'log')

# --- バックテスト設定 ---
INITIAL_CAPITAL = 50000000000000 # 初期資金
COMMISSION_PERC = 0.00 # 0.00%
SLIPPAGE_PERC = 0.0002 # 0.02%

# --- ロギング設定 ---
# ▼▼▼【変更箇所】▼▼▼
# バックテスト単体実行時のデフォルトログレベル。
# evaluation実行時は、この値がconfig_evaluation.pyの設定で一時的に上書きされます。
LOG_LEVEL = logging.INFO # INFO or DEBUG or None
# ▲▲▲【変更箇所ここまで】▲▲▲