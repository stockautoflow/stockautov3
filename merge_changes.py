# ==============================================================================
# ファイル: merge_changes.py
# 説明: このスクリプトは、ファイルシステム上の変更されたプロジェクトファイルを
#       自動的に検出し、元のジェネレータースクリプトにその変更をマージして、
#       新しいジェネレータースクリプトを生成します。
#       生成されるスクリプトは、元のフォーマット（改行やインデント）を維持します。
#
# 使い方:
# 1. このスクリプトをプロジェクトのルートディレクトリに保存します。
# 2. 変更したいファイルを直接編集して保存します。
# 3. ターミナルで以下のコマンドを実行します。
#
# python merge_changes.py [元のジェネレータースクリプト名]
#
# 例:
# python merge_changes.py create_project_files.py
#
# 上記のコマンドを実行すると、変更が検出されたすべてのファイルがマージされた
# `create_project_files_merged.py` という新しいファイルが生成されます。
#
# 依存ライブラリ:
# このスクリプトはPython 3.8以上で動作します。
# 追加のライブラリは不要です。
# ==============================================================================

import ast
import os
import argparse
from pathlib import Path

def extract_project_files_from_ast(tree):
    """
    ASTから 'project_files' 辞書の内容を抽出します。

    Args:
        tree (ast.Module): パースされたソースコードのAST

    Returns:
        dict or None: ファイル名と元の内容を格納した辞書。見つからない場合はNone。
    """
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and
                len(node.targets) == 1 and
                isinstance(node.targets[0], ast.Name) and
                node.targets[0].id == 'project_files' and
                isinstance(node.value, ast.Dict)):
            
            project_files = {}
            for key_node, value_node in zip(node.value.keys, node.value.values):
                # キーと値が文字列リテラルであることを確認
                if isinstance(key_node, ast.Constant) and isinstance(value_node, ast.Constant):
                    key = str(key_node.value)
                    value = str(value_node.value)
                    project_files[key] = value
            return project_files
    return None

def build_project_files_dict_source(updated_files_dict):
    """
    project_files辞書の、読みやすいソースコード表現を文字列として生成します。
    """
    # 文字列を効率的に結合するためにリストを使用
    parts = []
    
    # 辞書の各項目を整形
    for i, (filename, content) in enumerate(updated_files_dict.items()):
        # content内のバックスラッシュと三重引用符をエスケープ
        content_escaped = content.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
        
        # 各エントリをフォーマット。キーと、三重引用符で囲まれた値。
        entry_str = f'    "{filename}": """{content_escaped}"""'
        
        # 最後の項目でなければカンマを追加
        if i < len(updated_files_dict) - 1:
            entry_str += ','
            
        parts.append(entry_str)

    # 各エントリを2つの改行で結合し、読みやすさを向上
    body = "\n\n".join(parts)
    # 全体を中括弧で囲む
    return f"{{\n{body}\n}}"


def main():
    """
    メインの処理を実行する関数。
    """
    parser = argparse.ArgumentParser(
        description="ジェネレータースクリプトに変更されたファイルの内容を自動で検出しマージします。",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""使用例:
  python %(prog)s create_project_files.py
"""
    )
    parser.add_argument("generator_script", help="元のジェネレータースクリプトのパス (例: create_project_files.py)")

    args = parser.parse_args()

    # --- 1. ジェネレータースクリプトの読み込みと解析 ---
    if not os.path.exists(args.generator_script):
        print(f"エラー: ジェネレータースクリプトが見つかりません: {args.generator_script}")
        return

    print(f"'{args.generator_script}' を読み込んで解析しています...")
    with open(args.generator_script, 'r', encoding='utf-8') as f:
        source_code = f.read()
    
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        print(f"エラー: '{args.generator_script}' の解析中に構文エラーが発生しました: {e}")
        return

    original_files = extract_project_files_from_ast(tree)
    if original_files is None:
        print(f"エラー: '{args.generator_script}' 内に 'project_files' 辞書が見つかりませんでした。")
        return

    # --- 2. 変更されたファイルの検出 ---
    changed_files = []
    print("\nファイルシステムの変更を検出しています...")
    for filename, original_content in original_files.items():
        filepath = Path(filename)
        if not filepath.exists():
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            current_content = f.read()
        
        # 元の内容と現在の内容を正規化して比較
        original_stripped = original_content.strip().replace('\r\n', '\n')
        current_normalized = current_content.strip().replace('\r\n', '\n')

        if original_stripped != current_normalized:
            print(f"-> 変更を検出しました: {filename}")
            changed_files.append((filename, current_content))

    if not changed_files:
        print("変更されたファイルはありませんでした。処理を終了します。")
        return

    # --- 3. 新しいジェネレータースクリプトのソースコードを生成 ---
    print("\nジェネレータースクリプトに変更をマージしています...")
    
    # a. 変更を反映した新しい辞書オブジェクトを作成
    updated_files_dict = original_files.copy()
    for filename, new_content in changed_files:
        updated_files_dict[filename] = new_content

    # b. 新しい辞書のソースコード表現を生成
    new_dict_source = build_project_files_dict_source(updated_files_dict)
    new_assignment_source = f"project_files = {new_dict_source}"

    # c. 元のソースコードの該当部分を新しいソースコードで置き換え
    assignment_node = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and
                len(node.targets) == 1 and
                isinstance(node.targets[0], ast.Name) and
                node.targets[0].id == 'project_files'):
            assignment_node = node
            break

    if not assignment_node:
        print(f"エラー: 'project_files' の代入文をAST内で見つけられませんでした。")
        return

    with open(args.generator_script, 'r', encoding='utf-8') as f:
        source_lines = f.readlines()

    # ASTから取得した行番号（1-based）をリストのインデックス（0-based）に変換
    start_line = assignment_node.lineno - 1
    end_line = assignment_node.end_lineno # end_linenoは最後の行を指すため-1しない

    # 元のソースを3つの部分に分割して、中央を置き換え
    lines_before = source_lines[:start_line]
    lines_after = source_lines[end_line:]
    
    new_source_code = "".join(lines_before) + new_assignment_source + "\n\n" + "".join(lines_after)

    # --- 4. 新しいジェネレータースクリプトの保存 ---
    base, ext = os.path.splitext(args.generator_script)
    new_script_path = f"{base}_merged{ext}"

    print(f"\n変更をマージした新しいスクリプトを '{new_script_path}' に保存しています...")
    with open(new_script_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_source_code)

    print("\nマージ処理が正常に完了しました！")
    print(f"新しいジェネレータースクリプト: {new_script_path}")

if __name__ == '__main__':
    main()
