import sys
import subprocess

#-------------------------------------
# 使用法: python run_merge.py <引数>
# Example: $ python run_merge.py c
# 有効な引数と対応するファイル名:
#   i: initialize
#   c: core
#   b: backtest
#   e: evaluation
#   r: realtrade
#   d: dashboard
#   db: db
#   rakuten: rakuten
#   all: all (上記を順にすべて実行)
#-------------------------------------

def print_usage_and_exit(error_message=None):
    """
    エラーメッセージとスクリプトの使用法を表示して終了します。
    """
    if error_message:
        print(f"エラー: {error_message}")
    
    script_name = sys.argv[0]
    print(f"\n使用法: python {script_name} <引数>")
    print("\n有効な引数と対応するファイル名:")
    print("  i: initialize")
    print("  c: core")
    print("  b: backtest")
    print("  e: evaluation")
    print("  r: realtrade")
    print("  d: dashboard")
    print("  db: db")
    print("  rakuten: rakuten")
    print("  all: all (上記を順にすべて実行)")
    sys.exit(1)

def execute_script(filename):
    """
    指定されたファイル名に対応するスクリリプトを実行するヘルパー関数
    """
    print(f"\n--- 実行中: {filename} ---")
    target_script = f"scripts/create_{filename}.py"
    command = ["python", "./tools/merge/merge_changes.py", target_script]

    try:
        subprocess.run(command, check=True)
        print(f"--- 完了: {filename} ---")
        return True
    except FileNotFoundError:
        print("エラー: コマンド 'python' が見つかりませんでした。パスを確認してください。")
        return False
    except subprocess.CalledProcessError as e:
        print(f"エラー: {filename} の実行に失敗しました (リターンコード: {e.returncode})。")
        return False

def main():
    """
    メイン処理
    """
    arg_map = {
        "i": "initialize",
        "c": "core",
        "b": "backtest",
        "e": "evaluation",
        "r": "realtrade",
        "d": "dashboard",
        "rakuten": "rakuten",
        "db": "db",
    }

    if len(sys.argv) < 2:
        print_usage_and_exit("引数が指定されていません。")

    arg_key = sys.argv[1].lower()

    if arg_key == "all":
        print("すべてのスクリプトを順番に実行します...")
        
        # --- ▼▼▼ ここから変更 ▼▼▼ ---
        # 全てのスクリプトを対象にする
        all_scripts = arg_map.values()
        for filename in all_scripts:
            if not execute_script(filename):
                print("\nエラーが発生したため、処理を中断しました。")
                sys.exit(1)
        # --- ▲▲▲ ここまで変更 ▲▲▲ ---
        
        print("\n✅ すべてのスクリプトの実行が正常に完了しました。")
    
    else:
        filename = arg_map.get(arg_key)
        if filename is None:
            print_usage_and_exit(f"無効な引数 '{sys.argv[1]}' が指定されました。")
        
        if execute_script(filename):
            print("\n✅ スクリプトの実行が正常に完了しました。")
        else:
            sys.exit(1)

if __name__ == "__main__":
    main()