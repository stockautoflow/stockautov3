import os
import sys

# ==============================================================================
# 設定ここから
# ==============================================================================

# ▼▼▼ 1. 分割するサイズをメガバイト単位で指定してください ▼▼▼
CHUNK_SIZE_MB = 90

# ▼▼▼ 2. 分割したいファイルがあるディレクトリを指定してください ▼▼▼
# 空白 "" のままにすると、このスクリプトファイルがあるディレクトリを対象とします。
# Windowsのパスを指定する場合、先頭に 'r' を付けると便利です (例: r"C:\Users\YourName\Documents")
# Mac/Linux例: "/home/user/data"
TARGET_DIRECTORY = r"C:\stockautov3\log"

# ==============================================================================
# 設定ここまで
# ==============================================================================

# --- 使い方と実行例 (ターミナルで実行) ---
#
# 1. スクリプト冒頭の CHUNK_SIZE_MB と TARGET_DIRECTORY を設定します。
# 2. ターミナルを開き、このスクリプトファイルがあるディレクトリに移動します。
# 3. 以下の形式でコマンドを実行します。
#
# ◆ 基本的な使い方
# (例) large_data.csv というファイルを分割する場合:
# python log_splitter.py large_data.csv
#
# ◆ 別のディレクトリを指定した場合
# (例) TARGET_DIRECTORY = r"C:\Work\Data" と設定し、その中にある big_log.txt を分割する場合:
# python log_splitter.py big_log.txt
#
# ◆ ファイル名にスペースが含まれる場合
# (例) "my large file.zip" というファイルを分割する場合 (ファイル名を引用符で囲む):
# python log_splitter.py "my large file.zip"
# ------


def split_file_by_size(file_path, chunk_size_mb):
    """
    指定されたファイルを特定のサイズ（MB）以下のチャンクに分割する関数。

    Args:
        file_path (str): 分割したいファイルのパス。
        chunk_size_mb (int): 1ファイルあたりの最大サイズ（メガバイト単位）。
    """
    # ファイルが存在しない場合はエラーメッセージを表示して終了
    if not os.path.isfile(file_path):
        print(f"エラー: ファイル '{file_path}' が見つかりません。パスが正しいか確認してください。")
        return

    print(f"ファイルを分割しています: {file_path}")
    print(f"分割サイズ: {chunk_size_mb} MB")

    # チャンクサイズをバイト単位に変換
    chunk_size_bytes = chunk_size_mb * 1024 * 1024
    
    # 保存先のディレクトリと、ファイル名・拡張子を取得
    output_dir = os.path.dirname(file_path)
    base_name, extension = os.path.splitext(os.path.basename(file_path))
    
    part_num = 1
    
    try:
        # 元のファイルをバイナリ読み込みモードで開く
        with open(file_path, 'rb') as source_file:
            while True:
                # 指定したチャンクサイズ分だけファイルを読み込む
                chunk = source_file.read(chunk_size_bytes)
                
                # 読み込むデータがなくなったらループを終了
                if not chunk:
                    break
                
                # 新しいファイル名を生成 (例: my_document_01.txt)
                new_file_name = f"{base_name}_{part_num:02d}{extension}"
                # 保存先のパスを結合
                new_file_path = os.path.join(output_dir, new_file_name)
                
                print(f"作成中: {new_file_path}")
                
                # 新しいファイルをバイナリ書き込みモードで開き、読み込んだデータを書き込む
                with open(new_file_path, 'wb') as part_file:
                    part_file.write(chunk)
                
                # 次のファイル番号へ
                part_num += 1

        print("\nファイルの分割が完了しました。")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

# --- ここから実行部分 (この下は通常変更する必要はありません) ---
if __name__ == "__main__":
    # コマンドライン引数の数をチェック
    if len(sys.argv) < 2:
        print("エラー: 分割したいファイル名を引数として指定してください。")
        script_name = os.path.basename(__file__)
        print(f"使い方: python {script_name} <ファイル名>")
        sys.exit(1)

    # 最初の引数をファイル名として取得
    file_name = sys.argv[1]
    
    # ディレクトリパスとファイル名を結合して、完全なファイルパスを作成
    target_file_path = os.path.join(TARGET_DIRECTORY, file_name)
    
    # ファイル分割関数を呼び出し
    split_file_by_size(target_file_path, CHUNK_SIZE_MB)
