import os
import shutil

# ==============================================================================
# ファイル: initialize_structure.py
# 説明: リファクタリング計画に基づき、新しいプロジェクトのディレクトリ構造を生成し、
#       既存の設定ファイルを新しい場所に移行します。
# 実行方法: python initialize_structure.py
# Ver. 00-00
# ==============================================================================

def create_directory_structure():
    """
    リファクタリング計画書で定義されたディレクトリ構造を作成します。
    """
    dirs_to_create = [
        "results/backtest",
        "results/evaluation",
        "data",
        "log",
        "config",
        "src/core/util",
        "src/backtest",
        "src/realtrade/live",
        "src/realtrade/mock",
        "src/dashboard/templates",
        "src/evaluation",
    ]

    print("--- 1. ディレクトリ構造の作成を開始します ---")
    for d in dirs_to_create:
        try:
            os.makedirs(d, exist_ok=True)
            print(f"  - ディレクトリ作成: {d}")
            gitkeep_path = os.path.join(d, ".gitkeep")
            if not os.path.exists(gitkeep_path) and not os.listdir(d):
                with open(gitkeep_path, 'w') as f:
                    pass
        except OSError as e:
            print(f"エラー: ディレクトリ '{d}' の作成に失敗しました。 - {e}")
            return False
    print("ディレクトリ構造の作成が正常に完了しました。\n")
    return True

if __name__ == '__main__':
    print("初期セットアップを開始します。\n")
    create_directory_structure()
