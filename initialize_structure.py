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

def migrate_config_files():
    """
    既存の設定ファイルを新しい`config`ディレクトリにリネームして移動します。
    """
    # [旧ファイルパス, 新ファイルパス] のマッピング
    files_to_migrate = {
        'strategy.yml': 'config/strategy_base.yml',
        'strategies.yml': 'config/strategy_catalog.yml',
        'email_config.yml': 'config/email_config.yml'
    }

    print("--- 2. 設定ファイルの移行を開始します ---")
    all_successful = True
    for old_path, new_path in files_to_migrate.items():
        try:
            if os.path.exists(old_path):
                # shutil.moveはディレクトリが存在しない場合にエラーになるため、os.renameを使用
                os.rename(old_path, new_path)
                print(f"  - 移行成功: '{old_path}' -> '{new_path}'")
            else:
                print(f"  - スキップ: '{old_path}' が見つかりません。")
        except Exception as e:
            print(f"  - 移行失敗: '{old_path}' の移行中にエラーが発生しました。 - {e}")
            all_successful = False

    if all_successful:
        print("設定ファイルの移行が正常に完了しました。")
    else:
        print("一部の設定ファイルの移行に失敗しました。")
    return all_successful

if __name__ == '__main__':
    print("リファクタリングの初期セットアップを開始します。\n")
    if create_directory_structure():
        migrate_config_files()
    print("\nセットアップが完了しました。")

