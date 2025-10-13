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

# ▼▼▼【変更箇所】▼▼▼
from src.evaluation.orchestrator import main
from src.core.util import logger as logger_setup
from . import config_evaluation as config

if __name__ == '__main__':
    # evaluationモジュール自体のロガーを、設定ファイルに基づいてセットアップ
    logger_setup.setup_logging('log', log_prefix='evaluation', level=config.LOG_LEVEL)
    main()
# ▲▲▲【変更箇所ここまで】▲▲▲