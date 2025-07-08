import sys
import subprocess

#-------------------------------------
# 使用法: python run_merge.py <引数>
# Example: $ python run_merge.py
# 有効な引数と対応するファイル名:
#   i: initialize
#   c: core
#   b: backtest
#   e: evaluation
#   r: realtime
#   d: dashboard
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
    print("  r: realtime")
    print("  d: dashboard")
    print(" all: all (上記を順にすべて実行)")  # 'all'の説明に更新
    sys.exit(1)

def execute_script(filename):
    """
    指定されたファイル名に対応するスクリリプトを実行するヘルパー関数
    """
    print(f"\n--- 実行中: {filename} ---")
    target_script = f"scripts/create_{filename}.py"
    command = ["python", "./tools/merge_changes.py", target_script]

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
        "r": "realtime",
        "d": "dashboard",
    }

    if len(sys.argv) < 2:
        print_usage_and_exit("引数が指定されていません。")

    arg_key = sys.argv[1].lower()

    # 'all' が指定された場合の処理
    if arg_key == "all": # 'al' から 'all' に変更
        print("すべてのスクリプトを順番に実行します...")
        
        for filename in arg_map.values():
            if not execute_script(filename):
                print("\nエラーが発生したため、処理を中断しました。")
                sys.exit(1)
        
        print("\n✅ すべてのスクリプトの実行が正常に完了しました。")
    
    # 'all' 以外（個別実行）の場合の処理
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