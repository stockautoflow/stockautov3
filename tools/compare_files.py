import filecmp
import difflib
import sys
import os

def compare_single_pair(file1_path, file2_path, show_diff=False):
    """
    2つの単一ファイルを比較します。
    """
    if not (file1_path and file2_path):
        print("エラー: 比較するファイルパスを両方指定してください。")
        return

    if not os.path.exists(file1_path):
        print(f"エラー: ファイル '{file1_path}' が見つかりません。")
        return
    if not os.path.exists(file2_path):
        print(f"エラー: ファイル '{file2_path}' が見つかりません。")
        return

    try:
        # filecmp.cmpでファイルの比較（内容とメタデータ）
        if filecmp.cmp(file1_path, file2_path, shallow=False):
            print(f"'{file1_path}' と '{file2_path}' は同一です。")
        else:
            print(f"'{file1_path}' と '{file2_path}' は異なります。")
            if show_diff:
                print("\n--- 差分 ---")
                with open(file1_path, 'r', encoding='utf-8', errors='ignore') as f1, \
                     open(file2_path, 'r', encoding='utf-8', errors='ignore') as f2:
                    
                    diff = difflib.unified_diff(
                        f1.readlines(),
                        f2.readlines(),
                        fromfile=file1_path,
                        tofile=file2_path,
                        lineterm='' # 改行コードをdifflibに含めないようにする
                    )
                    for line in diff:
                        print(line, end='')
                print("------------")

    except Exception as e:
        print(f"'{file1_path}' と '{file2_path}' の比較中にエラーが発生しました: {e}")

def compare_files_from_list(list_file_path, show_diff=False):
    """
    比較リストファイルからファイルペアを読み込み、比較を実行します。

    Args:
        list_file_path (str): 比較するファイルパスが記載されたテキストファイルのパス。
        show_diff (bool): Trueの場合、ファイルに違いがある場合に差分を表示します。
    """
    if not os.path.exists(list_file_path):
        print(f"エラー: 比較リストファイル '{list_file_path}' が見つかりません。")
        print("使用法: python your_script_name.py <比較リストファイルのパス> [--diff]")
        return

    file_paths = []
    try:
        with open(list_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if stripped_line: # 空行を無視
                    file_paths.append(stripped_line)
    except Exception as e:
        print(f"エラー: 比較リストファイル '{list_file_path}' の読み込み中にエラーが発生しました: {e}")
        return

    if len(file_paths) % 2 != 0:
        print("警告: 比較リストファイルの行数が奇数です。最後のファイルは比較されません。")
    
    # 2つずつペアにして比較を実行
    for i in range(0, len(file_paths), 2):
        if i + 1 < len(file_paths):
            file1 = file_paths[i]
            file2 = file_paths[i+1]
            print(f"\n--- {file1} と {file2} の比較 ---")
            compare_single_pair(file1, file2, show_diff)
        else:
            print(f"スキップ: '{file_paths[i]}' に対応する比較対象がありません。")

if __name__ == "__main__":
    args = sys.argv[1:]
    
    list_file = None
    show_diff_option = False

    if len(args) >= 1:
        list_file = args[0]
        if len(args) > 1 and "--diff" in args:
            show_diff_option = True
    else:
        print("エラー: 比較リストファイルのパスを指定してください。")
        print("使用法: python compare_files_from_list.py <比較リストファイルのパス> [--diff]")
        sys.exit(1)
    
    compare_files_from_list(list_file, show_diff_option)