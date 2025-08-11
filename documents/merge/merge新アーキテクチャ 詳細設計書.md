はい、承知いたしました。
先に検討した「新アーキテクチャ基本仕様」に基づき、具体的な実装を行うための詳細設計書を作成します。

-----

## **新アーキテクチャ 詳細設計書**

### 1\. 概要

本設計書は、コンポーネントの自動検出を中核とする新アーキテクチャへの移行に関する、ファイル構成、モジュール設計、および実装コードを詳細に定義する。本設計の適用により、プロジェクトの保守性と拡張性を抜本的に改善する。

### 2\. 対象ファイル

  * **新規作成**:
      * `config.yml` (新しい設定ファイル)
      * `tools/discover.py` (コンポーネント検出モジュール)
  * **修正**:
      * `main.py` (コマンドラインエントリーポイント)
  * **変更なし**:
      * `tools/merge/merge_changes.py` (マージ処理エンジン)
  * **廃止**:
      * `config/cli_config.yml` (旧設定ファイル)
      * `tools/merge/run_merge.py` (マージ実行スクリプト)

### 3\. 設計詳細

#### 3.1. 新規設定ファイル: `config.yml`

自動検出できない情報のみを集約した、単一の設定ファイルを定義する。

  * **ファイルパス**: `config.yml`

  * **詳細な構造**:

    ```yaml
    # `gall`や`tmall`など、'all'指定で実行する際のコンポーネントの順序
    component_order:
      - "initialize"
      - "core"
      - "backtest"
      - "evaluation"
      - "rakuten"
      - "realtrade"
      - "dashboard"
      - "db"

    # 'python -m' で実行するモジュール定義
    runnable_modules:
      backtest: "src.backtest.run_backtest"
      evaluation: "src.evaluation.run_evaluation"
      realtrade: "src.realtrade.run_realtrade"
      dashboard: "src.dashboard.app"

    # コマンドのエイリアス定義
    # キーがエイリアス、値が元のコマンド名
    aliases:
      # メインコマンドのエイリアス
      g: "generate"
      r: "run"
      t: "tool"

      # コンポーネント名のエイリアス (generate, tool merge で使用)
      i: "initialize"
      c: "core"
      b: "backtest"
      e: "evaluation"
      rk: "rakuten"
      rt: "realtrade"
      d: "dashboard"
      # 'db' はエイリアスなし (元々ないため)
    ```

#### 3.2. 新規モジュール: `tools/discover.py`

プロジェクトコンポーネントを命名規則に基づいて自動検出する、再利用可能なモジュールを新設する。

  * **ファイルパス**: `tools/discover.py`

  * **実装コード**:

    ```python
    # tools/discover.py
    import os
    from pathlib import Path

    def discover_components(script_dir: str = "scripts") -> dict:
        """
        指定されたディレクトリをスキャンし、'create_*.py'という命名規則の
        コンポーネントスクリプトを検出する。

        Returns:
            dict: { "component_name": "path/to/script.py", ... } の形式の辞書
        """
        components = {}
        if not os.path.isdir(script_dir):
            return components

        for entry in os.scandir(script_dir):
            if entry.is_file() and entry.name.startswith("create_") and entry.name.endswith(".py"):
                # "create_" と ".py" を除いた部分をコンポーネント名とする
                component_name = entry.name[7:-3]
                components[component_name] = str(Path(entry.path))
        
        return components

    ```

#### 3.3. コマンドラインエントリーポイント: `main.py` の再設計

`main.py`を、設定ファイルと検出モジュールを利用して動的に動作するよう全面的に書き換える。

  * **ファイルパス**: `main.py`

  * **最終的な実装コード**:

    ```python
    # main.py (New Architecture)
    import sys
    import subprocess
    import argparse
    import yaml
    import os
    from tools.discover import discover_components

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

    def load_config(path="config.yml") -> dict:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"{Clr.FAIL}致命的エラー: 設定ファイルが見つかりません: {path}{Clr.ENDC}")
            sys.exit(1)
        return {}

    def execute_command(command_args: list) -> bool:
        try:
            subprocess.run(command_args, check=True, text=True, encoding='utf-8')
            return True
        except KeyboardInterrupt:
            print(f"{Clr.WARNING}ユーザーにより中断されました。{Clr.ENDC}")
            return False
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"{Clr.FAIL}エラー: コマンド実行に失敗しました。詳細: {e}{Clr.ENDC}")
            return False

    def setup_parser(config: dict, components: dict) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="プロジェクト統合管理ツール (新アーキテクチャ)")
        subparsers = parser.add_subparsers(dest="command", help="実行コマンド", required=True)
        
        component_choices = list(components.keys()) + ['all']
        runnable_choices = list(config.get('runnable_modules', {}).keys())

        # generate
        p_gen = subparsers.add_parser("generate", aliases=['g'], help="コンポーネントを生成")
        p_gen.add_argument("component", choices=component_choices, help="生成対象")

        # run
        p_run = subparsers.add_parser("run", aliases=['r'], help="モジュールを実行")
        p_run.add_argument("component", choices=runnable_choices, help="実行対象")
        p_run.add_argument('extra_args', nargs=argparse.REMAINDER)

        # tool
        p_tool = subparsers.add_parser("tool", aliases=['t'], help="各種ツールを実行")
        tool_subparsers = p_tool.add_subparsers(dest="tool_command", required=True)
        p_merge = tool_subparsers.add_parser("merge", help="ジェネレータースクリプトに変更をマージ")
        p_merge.add_argument("component", choices=component_choices, help="マージ対象")

        return parser

    def main():
        config = load_config()
        all_components = discover_components()
        
        # エイリアスを解決するための逆引きマップを作成
        aliases = config.get('aliases', {})
        alias_map = {v: k for k, v in aliases.items()} # e.g. {'generate': 'g', 'core': 'c'}

        # コマンドライン引数をパース
        parser = setup_parser(config, all_components)
        args = parser.parse_args()

        # 実行
        python_exec = sys.executable

        if args.command in [alias_map.get("generate"), "generate"]:
            components_to_process = config.get('component_order', []) if args.component == 'all' else [args.component]
            print_header(f"コンポーネント生成: {args.component}")
            
            success_list, failure_list = [], []
            for i, name in enumerate(components_to_process):
                if name in all_components:
                    print_progress(f"[{i+1}/{len(components_to_process)}] '{name}' を生成中...")
                    if execute_command([python_exec, all_components[name]]):
                        success_list.append(name)
                    else:
                        failure_list.append(name); break
                else:
                    print(f"{Clr.FAIL}エラー: コンポーネント '{name}' の生成スクリプトが見つかりません。{Clr.ENDC}")
                    failure_list.append(name); break
            
            if args.component == 'all':
                print_header("生成処理サマリー", Clr.WARNING)
                print(f"{Clr.OKGREEN}成功 ({len(success_list)}件): {success_list}{Clr.ENDC}")
                if failure_list:
                    print(f"{Clr.FAIL}失敗 ({len(failure_list)}件): {failure_list}{Clr.ENDC}")

        elif args.command in [alias_map.get("run"), "run"]:
            module_name = config['runnable_modules'][args.component]
            execute_command([python_exec, "-m", module_name] + args.extra_args)

        elif args.command in [alias_map.get("tool"), "tool"]:
            if args.tool_command == "merge":
                components_to_process = config.get('component_order', []) if args.component == 'all' else [args.component]
                print_header(f"変更マージ: {args.component}")

                for i, name in enumerate(components_to_process):
                    if name in all_components:
                        print_progress(f"[{i+1}/{len(components_to_process)}] '{name}' の変更をマージ中...")
                        merge_script = "tools/merge/merge_changes.py"
                        target_script = all_components[name]
                        if not execute_command([python_exec, merge_script, target_script]):
                            print(f"{Clr.FAIL}エラー: '{name}' のマージに失敗しました。{Clr.ENDC}")
                            break
                    else:
                        print(f"{Clr.FAIL}エラー: コンポーネント '{name}' が見つかりません。{Clr.ENDC}")
                        break

    if __name__ == "__main__":
        main()

    ```

### 4\. 移行手順

1.  **ファイル作成**:
    1.  `config.yml` をプロジェクトのルートに作成し、上記3.1の内容を記述します。
    2.  `tools/discover.py` を作成し、上記3.2の内容を記述します。
2.  **ファイル置換**:
    1.  `main.py` の内容を、上記3.3のコードで完全に置き換えます。
3.  **ファイル削除**:
    1.  古い設定ファイル `config/cli_config.yml` を削除します。
    2.  古いマージ実行スクリプト `tools/merge/run_merge.py` を削除します。
4.  **動作確認**:
      * `python main.py g all` (generate all) が正常に動作することを確認します。
      * `python main.py t merge c` (tool merge core) が `merge_changes.py` を正しく呼び出すことを確認します。
      * `python main.py r backtest` (run backtest) がバックテストモジュールを起動することを確認します。

以上で、新アーキテクチャへの移行が完了します。
これにより、新しいコンポーネント `new_feature` を追加したい場合、開発者は `scripts/create_new_feature.py` を作成するだけで、`generate` と `merge` の両方のコマンドが自動的に `new_feature` をサポートするようになります。