# tools/merge/merge_changes.py (最新版)
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
# python tools/merge/merge_changes.py create_project_files.py
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
import sys

# --- 終了コードの定義 ---
# 0: 正常終了（マージが発生）
# 1: エラー終了
# 2: 正常終了（変更なし）

def extract_project_files_from_ast(tree):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and
                len(node.targets) == 1 and
                isinstance(node.targets[0], ast.Name) and
                node.targets[0].id == 'project_files' and
                isinstance(node.value, ast.Dict)):
            project_files = {}
            for key_node, value_node in zip(node.value.keys, node.value.values):
                if isinstance(key_node, ast.Constant) and isinstance(value_node, ast.Constant):
                    key = str(key_node.value)
                    value = str(value_node.value)
                    project_files[key] = value
            return project_files
    return None

# ▼▼▼【修正箇所 1/2】この関数を丸ごと置き換える ▼▼▼
def build_project_files_dict_source(updated_files_dict):
    """
    更新された辞書から、正しいフォーマットのPythonソースコード文字列を生成します。
    """
    parts = []
    for i, (filename, content) in enumerate(updated_files_dict.items()):
        # コンテンツ内のバックスラッシュとトリプルクォートをエスケープ
        content_escaped = content.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
        # インデント（4つのスペース）を付けて整形
        entry_str = f'    "{filename}": """{content_escaped}"""'
        # 最後の要素以外にはカンマを追加
        if i < len(updated_files_dict) - 1:
            entry_str += ','
        parts.append(entry_str)
    
    # 実際の改行文字 `\n` で各パーツを結合
    body = "\n\n".join(parts)
    # 辞書全体を波括弧で囲み、ここでも実際の改行を使用
    return "{\n" + body + "\n}"
# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

def main():
    parser = argparse.ArgumentParser(description="ジェネレータースクリプトに変更されたファイルの内容を自動で検出しマージします。")
    parser.add_argument("generator_script", help="元のジェネレータースクリプトのパス")
    args = parser.parse_args()

    if not os.path.exists(args.generator_script):
        print(f"エラー: ジェネレータースクリプトが見つかりません: {args.generator_script}")
        sys.exit(1)

    with open(args.generator_script, 'r', encoding='utf-8') as f:
        source_code = f.read()
    
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        print(f"エラー: '{args.generator_script}' の解析中に構文エラーが発生しました: {e}")
        sys.exit(1)

    original_files = extract_project_files_from_ast(tree)
    if original_files is None:
        print(f"エラー: '{args.generator_script}' 内に 'project_files' 辞書が見つかりませんでした。")
        sys.exit(1)

    changed_files = []
    for filename, original_content in original_files.items():
        filepath = Path(filename)
        if not filepath.exists(): continue
        with open(filepath, 'r', encoding='utf-8') as f:
            current_content = f.read()
        original_stripped = original_content.strip().replace('\\r\\n', '\\n')
        current_normalized = current_content.strip().replace('\\r\\n', '\\n')
        if original_stripped != current_normalized:
            print(f"-> 変更を検出しました: {filename}")
            changed_files.append((filename, current_content))

    if not changed_files:
        print("変更されたファイルはありませんでした。")
        sys.exit(2)

    updated_files_dict = original_files.copy()
    for filename, new_content in changed_files:
        updated_files_dict[filename] = new_content
    new_dict_source = build_project_files_dict_source(updated_files_dict)
    new_assignment_source = f"project_files = {new_dict_source}"
    assignment_node = next((node for node in ast.walk(tree) if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'project_files'), None)

    if not assignment_node:
        print(f"エラー: 'project_files' の代入文をAST内で見つけられませんでした。")
        sys.exit(1)

    with open(args.generator_script, 'r', encoding='utf-8') as f:
        source_lines = f.readlines()
    start_line, end_line = assignment_node.lineno - 1, assignment_node.end_lineno
    
    # ▼▼▼【修正箇所 2/2】 "\\n\\n" を "\n\n" に変更 ▼▼▼
    new_source_code = "".join(source_lines[:start_line]) + new_assignment_source + "\n\n" + "".join(source_lines[end_line:])
    
    base, ext = os.path.splitext(args.generator_script)
    new_script_path = f"{base}_merged{ext}"
    with open(new_script_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_source_code)
    print(f"\nマージ処理が正常に完了しました！新しいスクリプト: {new_script_path}")
    sys.exit(0)

if __name__ == '__main__':
    main()