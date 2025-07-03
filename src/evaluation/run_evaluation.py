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