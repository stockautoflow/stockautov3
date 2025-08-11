# start.py (ラッパー - 更新版)
import sys
import subprocess

def main():
    """
    manage.pyのラッパーとして、全ての引数を引き渡して実行します。
    """
    # ▼▼▼ 修正箇所 ▼▼▼
    # manage.pyの新しいパスを指定
    base_command = [sys.executable, "tools/manage/manage.py"]
    # ▲▲▲ 修正箇所ここまで ▲▲▲
    
    forwarded_args = sys.argv[1:]
    full_command = base_command + forwarded_args
    
    try:
        subprocess.run(full_command, check=True)
    except FileNotFoundError:
        print(f"エラー: '{' '.join(base_command)}' が見つかりませんでした。")
    except subprocess.CalledProcessError:
        pass

if __name__ == "__main__":
    main()