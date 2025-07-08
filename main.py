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
#   - リアルタイム取引を実行:       python main.py run realtrade
#
# 使い方 (短縮コマンド):
#   - generate all:       python main.py ga
#   - run backtest:       python main.py rb
#   - run realtrade:      python main.py rr
#   - run evaluation:     python main.py re
# ==============================================================================

# --- グローバル設定 ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 各生成スクリプトのパス
GENERATION_SCRIPTS = {
    "initialize": "scripts/create_initialize.py",
    "core": "scripts/create_core.py",
    "backtest": "scripts/create_backtest.py",
    "evaluation": "scripts/create_evaluation.py",
    "realtrade": "scripts/create_realtrade.py",
    "dashboard": "scripts/create_dashboard.py",
}

# 実行モジュールの定義 (backtest, realtrade を追加)
RUNNABLE_MODULES = {
    "backtest": "src.backtest.run_backtest",
    "realtrade": "src.realtrade.run_realtrade",
    "evaluation": "src.evaluation.run_evaluation",
    "dashboard": "src.dashboard.app"
}

# 短縮コマンドの定義 (rb, rr を追加)
ALIASES = {
    # generate commands
    "ga": ("generate", ["all"]),
    "gi": ("generate", ["initialize"]),
    "gc": ("generate", ["core"]),
    "gb": ("generate", ["backtest"]),
    "ge": ("generate", ["evaluation"]),
    "gr": ("generate", ["realtrade"]),
    "gd": ("generate", ["dashboard"]),
    # run commands
    "rb": ("run", ["backtest"]),
    "rr": ("run", ["realtrade"]),
    "re": ("run", ["evaluation"]),
    "rd": ("run", ["dashboard"]),
}

def execute_script(script_path):
    """指定されたPythonスクリプトを実行する"""
    full_path = os.path.join(PROJECT_ROOT, script_path)
    if not os.path.exists(full_path):
        print(f"エラー: スクリプトが見つかりません: {full_path}")
        return False

    print(f"\n--- 実行中: {script_path} ---")
    try:
        result = subprocess.run(
            [sys.executable, full_path],
            check=True,
            text=True,
            encoding='utf-8'
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
        # 実際のコマンド引数をモジュールに渡すために sys.argv を調整
        # 例: `python main.py rb arg1 --flag` -> `python -m src.backtest.run_backtest arg1 --flag`
        args_to_pass = sys.argv[2:]
        command = [sys.executable, "-m", RUNNABLE_MODULES[module_name]] + args_to_pass
        
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"エラー: モジュール {module_name} の実行に失敗しました。")
        return False
    except FileNotFoundError:
        print(f"エラー: Python実行ファイルが見つかりません: {sys.executable}")
        return False


def generate_components(components):
    """指定されたコンポーネント、またはすべてを生成する"""
    if "all" in components:
        component_order = ["initialize", "core", "backtest", "evaluation", "realtrade", "dashboard"]
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
    # runコマンドでは通常１つのコンポーネントのみ実行
    comp_to_run = components[0]
    if not execute_module(comp_to_run):
        print(f"{comp_to_run} の実行に失敗しました。")


def main():
    """コマンドライン引数を解釈して適切な処理を実行する"""
    if len(sys.argv) > 1 and sys.argv[1] in ALIASES:
        command, components = ALIASES[sys.argv[1]]
        if command == "generate":
            generate_components(components)
        elif command == "run":
            # 短縮コマンドからの実行を`run_components`に渡す
            run_components(components)
        return

    parser = argparse.ArgumentParser(
        description="株自動トレードシステムの統合管理ツール",
        formatter_class=argparse.RawTextHelpFormatter
    )
    alias_help = "\n利用可能な短縮コマンド:\n"
    for alias, (cmd, comps) in ALIASES.items():
        alias_help += f"  {alias:<5} -> {cmd} {' '.join(comps)}\n"
    parser.epilog = alias_help

    subparsers = parser.add_subparsers(dest="command", help="実行するコマンド")

    parser_gen = subparsers.add_parser(
        "generate",
        aliases=["g"],
        help="プロジェクトの各コンポーネントを生成します。"
    )
    parser_gen.add_argument(
        "component",
        nargs="+",
        choices=list(GENERATION_SCRIPTS.keys()) + ["all"]
    )

    parser_run = subparsers.add_parser(
        "run",
        aliases=["r"],
        help="特定の機能を実行します。"
    )
    # 実行するコンポーネント名と、それに続く追加の引数をキャッチ
    parser_run.add_argument(
        "component",
        choices=list(RUNNABLE_MODULES.keys())
    )
    # 不明な引数をすべて受け取る
    parser_run.add_argument('extra_args', nargs=argparse.REMAINDER)

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        return

    # エイリアスでない場合、最初の2つの引数のみで解析
    # これにより、追加の引数がエラーと見なされるのを防ぐ
    known_args, unknown_args = parser.parse_known_args()
    sys.argv = [sys.argv[0], known_args.command, known_args.component] + unknown_args


    if known_args.command in ["generate", "g"]:
        generate_components(known_args.component if isinstance(known_args.component, list) else [known_args.component])
    elif known_args.command in ["run", "r"]:
        run_components([known_args.component])


if __name__ == "__main__":
    main()