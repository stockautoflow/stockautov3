# main.py
import argparse
import subprocess
import sys
import os

# ==============================================================================
# プロジェクト統合管理スクリプト (エイリアス対応)
# ------------------------------------------------------------------------------
# 使い方 (通常コマンド):
#   - すべてのコンポーネントを生成: python main.py generate all
#   - バックテストを実行:           python main.py run backtest
#   - DBユーティリティを実行:     python main.py db view
#   - マージツールを実行:         python main.py merge core
#
# 使い方 (短縮コマンド):
#   - generate all:         python main.py gall
#   - run backtest:         python main.py rb
#   - tool merge db:        python main.py tmdb
#   - tool db view:         python main.py tdv
# ==============================================================================

# --- グローバル設定 ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 各生成スクリプトのパス
GENERATION_SCRIPTS = {
    "initialize": "scripts/create_initialize.py",
    "core": "scripts/create_core.py",
    "backtest": "scripts/create_backtest.py",
    "evaluation": "scripts/create_evaluation.py",
    "rakuten": "scripts/create_rakuten.py",
    "realtrade": "scripts/create_realtrade.py",
    "dashboard": "scripts/create_dashboard.py",
    "db": "scripts/create_db.py",
}

# 実行モジュールの定義
RUNNABLE_MODULES = {
    "backtest": "src.backtest.run_backtest",
    "realtrade": "src.realtrade.run_realtrade",
    "evaluation": "src.evaluation.run_evaluation",
    "dashboard": "src.dashboard.app"
}

# 短縮コマンドの定義
ALIASES = {
    # generate commands
    "gall": ("generate", ["all"]),
    "gi": ("generate", ["initialize"]),
    "gc": ("generate", ["core"]),
    "gb": ("generate", ["backtest"]),
    "ge": ("generate", ["evaluation"]),
    "grk": ("generate", ["rakuten"]),
    "gr": ("generate", ["realtrade"]),
    "gd": ("generate", ["dashboard"]),
    "gdb": ("generate", ["db"]),
    # run commands
    "rb": ("run", ["backtest"]),
    "rr": ("run", ["realtrade"]),
    "re": ("run", ["evaluation"]),
    "rd": ("run", ["dashboard"]),
    # tool commands
    "tmi":   ("tool", ["tools/merge/run_merge.py", "i"]),
    "tmc":   ("tool", ["tools/merge/run_merge.py", "c"]),
    "tmb":   ("tool", ["tools/merge/run_merge.py", "b"]),
    "tme":   ("tool", ["tools/merge/run_merge.py", "e"]),
    "tmr":   ("tool", ["tools/merge/run_merge.py", "r"]),
    "tmd":   ("tool", ["tools/merge/run_merge.py", "d"]),
    "tmrk":  ("tool", ["tools/merge/run_merge.py", "rakuten"]),
    "tmall": ("tool", ["tools/merge/run_merge.py", "all"]),
    "tmdb":  ("tool", ["tools/merge/run_merge.py", "db"]),
    "tdv":   ("tool", ["tools/db/view_db.py"]),
    "tdg":   ("tool", ["tools/db/generate_sample_db.py"]),
}

def execute_script(script_path):
    """指定されたPythonスクリプトを実行する"""
    full_path = os.path.join(PROJECT_ROOT, script_path)
    if not os.path.exists(full_path):
        print(f"エラー: スクリプトが見つかりません: {full_path}")
        return False

    print(f"\n--- 実行中: {script_path} ---")
    try:
        subprocess.run(
            [sys.executable, full_path],
            check=True, text=True, encoding='utf-8'
        )
        print(f"--- 完了: {script_path} ---")
        return True
    except subprocess.CalledProcessError as e:
        print(f"エラー: {script_path} の実行に失敗しました。リターンコード: {e.returncode}")
        print("--- 標準出力 ---\n" + e.stdout if e.stdout else "")
        print("--- 標準エラー出力 ---\n" + e.stderr if e.stderr else "")
        return False
    except FileNotFoundError:
        print(f"エラー: Python実行ファイルが見つかりません: {sys.executable}")
        return False


def execute_module(module_name):
    """指定されたモジュールを 'python -m' で実行する"""
    if module_name not in RUNNABLE_MODULES:
        print(f"エラー: 不明なモジュール名です: {module_name}")
        return False

    print(f"\n--- モジュール実行中: {RUNNABLE_MODULES[module_name]} ---")
    try:
        args_to_pass = sys.argv[2:]
        command = [sys.executable, "-m", RUNNABLE_MODULES[module_name]] + args_to_pass
        
        subprocess.run(command, check=True)
        return True
    except KeyboardInterrupt:
        print(f"\n[main.py] ユーザー割り込みを検知しました。プログラムを終了します。")
        return True
    except subprocess.CalledProcessError:
        print(f"エラー: モジュール {module_name} の実行に失敗しました。")
        return False
    except FileNotFoundError:
        print(f"エラー: Python実行ファイルが見つかりません: {sys.executable}")
        return False

def execute_tool(tool_args):
    """指定されたツールスクリプトを、後続の引数とともに実行する"""
    if not tool_args:
        print("エラー: ツールスクリプトが指定されていません。")
        return False

    script_relative_path = tool_args[0]
    script_absolute_path = os.path.join(PROJECT_ROOT, script_relative_path)
    script_arguments = tool_args[1:]

    if not os.path.exists(script_absolute_path):
        print(f"エラー: ツールスクリプトが見つかりません: {script_absolute_path}")
        return False

    command = [sys.executable, script_absolute_path] + script_arguments
    
    print(f"\n--- ツール実行中: {' '.join(command).replace(sys.executable, 'python')} ---")
    try:
        subprocess.run(command, check=True, text=True, encoding='utf-8')
        print(f"--- 完了: {script_relative_path} ---")
        return True
    except subprocess.CalledProcessError as e:
        print(f"エラー: ツールの実行に失敗しました (リターンコード: {e.returncode})。")
        return False
    except FileNotFoundError:
        print(f"エラー: Python実行ファイルが見つかりません: {sys.executable}")
        return False

def generate_components(components):
    """指定されたコンポーネント、またはすべてを生成する"""
    if "all" in components:
        # --- ▼▼▼ ここから変更 ▼▼▼ ---
        # 'db' も含め、すべてのコンポーネントを対象にする
        component_order = ["initialize", "core", "backtest", "evaluation", "rakuten", "realtrade", "dashboard", "db"]
        # --- ▲▲▲ ここまで変更 ▲▲▲ ---
        print("すべてのコンポーネントを生成します...")
        for comp in component_order:
            script_path = GENERATION_SCRIPTS.get(comp)
            if not script_path or not execute_script(script_path):
                print(f"{comp} の生成に失敗したため、処理を中断します。")
                return
        print("\nすべてのコンポーネントの生成が完了しました。")
    else:
        for comp in components:
            script_path = GENERATION_SCRIPTS.get(comp)
            if not script_path:
                print(f"警告: '{comp}' に対応する生成スクリプトが見つかりません。スキップします。")
                continue
            if not execute_script(script_path):
                print(f"{comp} の生成に失敗しました。")


def run_components(components):
    """指定されたコンポーネントを実行する"""
    comp_to_run = components[0]
    if not execute_module(comp_to_run):
        print(f"{comp_to_run} の実行に失敗しました。")


def main():
    """コマンドライン引数を解釈して適切な処理を実行する"""
    if len(sys.argv) > 1 and sys.argv[1] in ALIASES:
        if '-h' in sys.argv or '--help' in sys.argv:
             pass
        else:
            command, components = ALIASES[sys.argv[1]]
            if command == "generate":
                generate_components(components)
            elif command == "run":
                run_components(components)
            elif command == "tool":
                execute_tool(components)
            return

    parser = argparse.ArgumentParser(
        description="株取引自動化プロジェクトの統合管理ツール。\n各コンポーネントの生成、実行、各種ツールの呼び出しをサポートします。",
        formatter_class=argparse.RawTextHelpFormatter
    )

    grouped_aliases = {"generate": [], "run": [], "tool": []}
    for alias, (cmd, comps) in sorted(ALIASES.items()):
        if cmd in grouped_aliases:
            if cmd == 'tool':
                script_name = comps[0].split('/')[-1]
                script_args = ' '.join(comps[1:])
                description = f"{cmd} {script_name} {script_args}".strip()
            else:
                description = f"{cmd} {' '.join(comps)}"
            grouped_aliases[cmd].append(f"  {alias:<5} -> {description}")

    alias_help = "\n利用可能な短縮コマンド (エイリアス):\n"
    if grouped_aliases["generate"]:
        alias_help += "\n--- 生成 (generate) ---\n"
        alias_help += "\n".join(grouped_aliases["generate"]) + "\n"
    if grouped_aliases["run"]:
        alias_help += "\n--- 実行 (run) ---\n"
        alias_help += "\n".join(grouped_aliases["run"]) + "\n"
    if grouped_aliases["tool"]:
        alias_help += "\n--- ツール (tool) ---\n"
        alias_help += "\n".join(grouped_aliases["tool"]) + "\n"

    parser.epilog = alias_help

    subparsers = parser.add_subparsers(dest="command", help="実行するコマンド", metavar="COMMAND")

    parser_gen = subparsers.add_parser("generate", aliases=["g"], help="プロジェクトの各コンポーネントファイルを生成します。")
    parser_gen.add_argument("component", nargs="+", choices=list(GENERATION_SCRIPTS.keys()) + ["all"], help="生成するコンポーネント名。'all' ですべて生成します。")

    parser_run = subparsers.add_parser("run", aliases=["r"], help="バックテストやリアルタイム取引などを実行します。")
    parser_run.add_argument("component", choices=list(RUNNABLE_MODULES.keys()), help="実行する機能名。")
    parser_run.add_argument('extra_args', nargs=argparse.REMAINDER, help="実行モジュールに渡す追加の引数。")

    parser_db = subparsers.add_parser("db", aliases=["td"], help="SQLiteデータベースの参照やサンプルDBを生成します。")
    db_subparsers = parser_db.add_subparsers(dest="db_command", help="DB操作コマンド", required=True, metavar="DB_COMMAND")
    db_subparsers.add_parser("view", help="データベースの内容を表示します (エイリアス: tdv)")
    db_subparsers.add_parser("gen", help="サンプルデータベースを生成します (エイリアス: tdg)")

    parser_merge = subparsers.add_parser("merge", aliases=["tm"], help="各コンポーネントからプロジェクトファイルを生成します。")
    merge_components = sorted(list(set([v[1][1] for k, v in ALIASES.items() if k.startswith('tm')])))
    parser_merge.add_argument("component", choices=merge_components, help="マージ対象のコンポーネント名")

    args = parser.parse_args()

    if hasattr(args, 'command'):
        if args.command in ["generate", "g"]:
            generate_components(args.component if isinstance(args.component, list) else [args.component])
        elif args.command in ["run", "r"]:
            sys.argv = [sys.argv[0]] + [args.component] + args.extra_args
            run_components([args.component])
        elif args.command in ["db", "td"]:
            if args.db_command == "view":
                execute_tool(ALIASES['tdv'][1])
            elif args.db_command == "gen":
                execute_tool(ALIASES['tdg'][1])
        elif args.command in ["merge", "tm"]:
            alias_key_to_find = args.component
            alias_key = "tmrk" if alias_key_to_find == "rakuten" else "tm" + alias_key_to_find
            if alias_key in ALIASES:
                execute_tool(ALIASES[alias_key][1])
            else:
                print(f"エラー: 無効なマージコンポーネント '{args.component}'")
    else:
        parser.print_help(sys.stderr)


if __name__ == "__main__":
    main()