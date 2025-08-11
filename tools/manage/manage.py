# tools/manage/manage.py (Project Management CLI)
import sys
import subprocess
import argparse
import yaml
import os

# このスクリプトがサブディレクトリから実行されても、他のモジュールを正しく見つけられるようにする
# 1. このファイルの場所からプロジェクトのルートディレクトリを特定
#    (.../tools/manage/manage.py -> .../)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
# 2. Pythonの検索パスにプロジェクトルートを追加
sys.path.append(PROJECT_ROOT)

# ▼▼▼ 修正箇所 2/3: importパスを新しい配置場所に合わせて修正 ▼▼▼
from tools.manage.component_discovery import discover_components

os.system('') # for Windows ANSI color support

class Clr:
    OKGREEN = '\033[92m'
    FAIL = '\033[91m'
    WARNING = '\033[93m'
    OKBLUE = '\033[94m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'

def print_header(message, color=Clr.OKBLUE):
    print(f"\n{color}{Clr.BOLD}{'='*15} {message} {'='*15}{Clr.ENDC}")

def print_progress(message):
    print(f"\n--- {message} ---")

def load_config(path="config/commands.yml") -> dict:
    config_path = os.path.join(PROJECT_ROOT, path)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"{Clr.FAIL}致命的エラー: 設定ファイル '{config_path}' が見つかりません。{Clr.ENDC}")
        sys.exit(1)
    return {}

def execute_command(command_args: list) -> int:
    try:
        result = subprocess.run(command_args, text=True, encoding='utf-8', cwd=PROJECT_ROOT)
        return result.returncode
    except KeyboardInterrupt:
        print(f"{Clr.WARNING}ユーザーにより中断されました。{Clr.ENDC}")
        return -1
    except FileNotFoundError:
        print(f"{Clr.FAIL}エラー: コマンド '{command_args[0]}' が見つかりません。{Clr.ENDC}")
        return 1

def setup_parser(config: dict, components: dict) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="プロジェクト統合管理ツール")
    subparsers = parser.add_subparsers(dest="command", help="実行コマンド", required=True)
    aliases = config.get('aliases', {})
    component_aliases = {k for k, v in aliases.items() if isinstance(v, str) and v not in ['generate', 'run', 'tool']}
    component_choices = set(components.keys()) | component_aliases | {'all'}
    p_gen = subparsers.add_parser("generate", aliases=[k for k, v in aliases.items() if v == 'generate'], help="コンポーネントを生成")
    p_gen.add_argument("component", choices=component_choices, help="生成対象")
    p_run = subparsers.add_parser("run", aliases=[k for k, v in aliases.items() if v == 'run'], help="モジュールを実行")
    p_run.add_argument("component", choices=config.get('runnable_modules', {}).keys(), help="実行対象")
    p_run.add_argument('extra_args', nargs=argparse.REMAINDER)
    p_tool = subparsers.add_parser("tool", aliases=[k for k, v in aliases.items() if v == 'tool'], help="各種ツールを実行")
    tool_subparsers = p_tool.add_subparsers(dest="tool_command", help="ツールコマンド", required=True)
    p_merge = tool_subparsers.add_parser("merge", help="ジェネレータースクリプトに変更をマージ")
    p_merge.add_argument("component", choices=component_choices, help="マージ対象")
    tool_subparsers.add_parser("db_view", help="DB閲覧ツール")
    tool_subparsers.add_parser("db_gen", help="サンプルDB生成ツール")
    return parser

def handle_command(args: argparse.Namespace, config: dict, components: dict):
    python_exec = sys.executable
    aliases = config.get('aliases', {})
    def resolve_alias(name):
        return aliases.get(name, name)

    if args.command in ["generate", "g"]:
        comp_name = resolve_alias(args.component)
        components_to_process = config.get('component_order', []) if comp_name == 'all' else [comp_name]
        print_header(f"コンポーネント生成: {comp_name}")
        success_list, failure_list = [], []
        for i, name in enumerate(components_to_process):
            if name in components:
                print_progress(f"[{i+1}/{len(components_to_process)}] '{name}' を生成中...")
                if execute_command([python_exec, components[name]]) == 0:
                    success_list.append(name)
                else:
                    failure_list.append(name); break
            else:
                print(f"{Clr.FAIL}エラー: コンポーネント '{name}' が見つかりません。{Clr.ENDC}"); failure_list.append(name); break
        if comp_name == 'all':
            print_header("生成処理サマリー", Clr.WARNING)
            total_components = len(config.get('component_order', []))
            if failure_list: print(f"{Clr.FAIL}{Clr.BOLD}ステータス: ❌ エラーにより処理が中断されました。{Clr.ENDC}")
            else: print(f"{Clr.OKGREEN}{Clr.BOLD}ステータス: ✅ 全てのコンポーネントが正常に生成されました。{Clr.ENDC}")
            if success_list:
                print(f"\n[ 成功したコンポーネント ({len(success_list)}/{total_components}) ]"); print("-" * 50)
                for item in success_list: print(f" {Clr.OKGREEN}✔{Clr.ENDC} {item}")
                print("-" * 50)
            if failure_list:
                print(f"\n[ 失敗したコンポーネント ({len(failure_list)}/{total_components}) ]"); print("-" * 50)
                for item in failure_list: print(f" {Clr.FAIL}✖{Clr.ENDC} {item}")
                print("-" * 50)

    elif args.command in ["run", "r"]:
        module_name = config['runnable_modules'][args.component]
        execute_command([python_exec, "-m", module_name] + args.extra_args)

    elif args.command in ["tool", "t"]:
        tool_scripts = config.get('tool_scripts', {})
        if args.tool_command == "merge":
            comp_name = resolve_alias(args.component)
            components_to_process = config.get('component_order', []) if comp_name == 'all' else [comp_name]
            print_header(f"変更マージ: {comp_name}")
            results = []
            for i, name in enumerate(components_to_process):
                if name in components:
                    print_progress(f"[{i+1}/{len(components_to_process)}] '{name}' の変更をマージ中...")
                    return_code = execute_command([python_exec, os.path.join(PROJECT_ROOT, tool_scripts['merge']), components[name]])
                    if return_code == 0: results.append({'name': name, 'status': 'MERGED'})
                    elif return_code == 2: results.append({'name': name, 'status': 'NO_CHANGES'})
                    else: results.append({'name': name, 'status': 'FAILED'}); break
                else:
                    print(f"{Clr.FAIL}エラー: コンポーネント '{name}' が見つかりません。{Clr.ENDC}"); results.append({'name': name, 'status': 'FAILED'}); break
            if comp_name == 'all':
                print_header("マージ処理サマリー", Clr.WARNING)
                has_failed = any(r['status'] == 'FAILED' for r in results)
                if has_failed: print(f"{Clr.FAIL}{Clr.BOLD}ステータス: ❌ エラーにより処理が中断されました。{Clr.ENDC}")
                else: print(f"{Clr.OKGREEN}{Clr.BOLD}ステータス: ✅ 全てのコンポーネントのマージが完了しました。{Clr.ENDC}")
                print(f"\n[ 処理結果 ]"); print("-" * 50)
                for res in results:
                    if res['status'] == 'MERGED': print(f" {Clr.OKGREEN}✔ マージ完了{Clr.ENDC}   : {res['name']}")
                    elif res['status'] == 'NO_CHANGES': print(f" {Clr.WARNING}✓ 変更なし{Clr.ENDC}     : {res['name']}")
                    elif res['status'] == 'FAILED': print(f" {Clr.FAIL}✖ 失敗{Clr.ENDC}         : {res['name']}")
                print("-" * 50)
        
        elif args.tool_command in ["db_view", "db_gen"]:
            execute_command([python_exec, os.path.join(PROJECT_ROOT, tool_scripts[args.tool_command])])

def main():
    config = load_config()
    all_components = discover_components(os.path.join(PROJECT_ROOT, "scripts"))
    aliases = config.get('aliases', {})
    args_list = sys.argv[1:]
    if not args_list:
        setup_parser(config, all_components).print_help(sys.stderr); return
    first_arg = args_list[0]
    if first_arg in aliases and isinstance(aliases.get(first_arg), list):
        args_list = aliases[first_arg]
    parser = setup_parser(config, all_components)
    args = parser.parse_args(args_list)
    handle_command(args, config, all_components)

if __name__ == "__main__":
    main()