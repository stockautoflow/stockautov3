はい、承知いたしました。
`main.py`のリファクタリングに関する詳細設計書を作成します。

-----

## **`main.py` リファクタリング詳細設計書**

### **1. 概要**

本設計書は、プロジェクト統合管理スクリプト `main.py` のリファクタリングに関する詳細な設計を定義する。目的は、保守性・可読性・拡張性の向上であり、既存の全機能は変更しない。

### **2. 変更対象**

  * **修正対象ファイル**: `main.py`
  * **新規作成ファイル**: `config/cli_config.yml`

### **3. 設計詳細**

#### **3.1. 設定ファイルの導入**

設定情報を `main.py` から分離し、一元管理するため、以下の構造を持つ `config/cli_config.yml` を新規に作成する。

  * **ファイルパス**: `config/cli_config.yml`

  * **ファイル構造**:

    ```yaml
    # 各コンポーネント生成スクリプトのパス
    generation_scripts:
      initialize: "create_initialize.py"
      core: "create_core.py"
      backtest: "create_backtest.py"
      evaluation: "create_evaluation.py"
      rakuten: "create_rakuten.py"
      realtrade: "create_realtrade.py"
      dashboard: "create_dashboard.py"
      db: "create_db.py"

    # 'python -m' で実行するモジュール
    runnable_modules:
      backtest: "src.backtest.run_backtest"
      evaluation: "src.evaluation.run_evaluation"
      realtrade: "src.realtrade.run_realtrade"
      dashboard: "src.dashboard.app"

    # ツールスクリプトのパス
    tool_scripts:
      merge: "tools/merge/run_merge.py"
      db_view: "tools/db/view_db.py"
      db_gen: "tools/db/generate_sample_db.py"

    # 短縮コマンドの定義
    aliases:
      # generate
      gall:  { command: "generate", args: ["all"] }
      gi:    { command: "generate", args: ["initialize"] }
      gc:    { command: "generate", args: ["core"] }
      gb:    { command: "generate", args: ["backtest"] }
      ge:    { command: "generate", args: ["evaluation"] }
      grk:   { command: "generate", args: ["rakuten"] }
      gr:    { command: "generate", args: ["realtrade"] }
      gd:    { command: "generate", args: ["dashboard"] }
      gdb:   { command: "generate", args: ["db"] }
      # run
      rb:    { command: "run", args: ["backtest"] }
      re:    { command: "run", args: ["evaluation"] }
      rr:    { command: "run", args: ["realtrade"] }
      rd:    { command: "run", args: ["dashboard"] }
      # tool
      tm:    { command: "tool", sub_command: "merge" }
      tdv:   { command: "tool", sub_command: "db_view" }
      tdg:   { command: "tool", sub_command: "db_gen" }
    ```

#### **3.2. コマンド実行ロジックの共通化**

`execute_script`, `execute_module`, `execute_tool` を廃止し、以下の共通関数に統合する。

  * **新設関数**: `execute_command(command_args: list)`

  * **実装例**:

    ```python
    import subprocess
    import sys
    import logging

    logger = logging.getLogger(__name__)

    def execute_command(command_args: list, **kwargs) -> bool:
        """指定されたコマンドをサブプロセスとして実行する"""
        logger.info(f"コマンド実行: {' '.join(command_args)}")
        try:
            # text=True は universal_newlines=True と同じで、エンコーディングを指定
            subprocess.run(
                command_args,
                check=True,
                text=True,
                encoding='utf-8',
                **kwargs
            )
            logger.info("コマンド正常終了")
            return True
        except KeyboardInterrupt:
            logger.warning("ユーザーによりコマンド実行が中断されました。")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"コマンド実行エラー (コード: {e.returncode})")
            if e.stdout:
                logger.error(f"--- STDOUT ---\n{e.stdout}")
            if e.stderr:
                logger.error(f"--- STDERR ---\n{e.stderr}")
            return False
        except FileNotFoundError:
            logger.error(f"実行ファイルが見つかりません: {command_args[0]}")
            return False
    ```

#### **3.3. メインロジックの再構築**

`main`関数を責務分割し、`argparse`のセットアップとコマンドの処理を動的に行う。

  * **ヘルパー関数の設計**:

      * `load_config(path: str) -> dict`:
        指定されたパスからYAMLファイルを読み込み、辞書として返す。

        ```python
        import yaml
        def load_config(path="config/cli_config.yml"):
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        ```

      * `setup_parser(config: dict) -> argparse.ArgumentParser`:
        設定情報に基づき、`argparse`のパーサーを動的に構築する。

        ```python
        import argparse
        def setup_parser(config: dict):
            parser = argparse.ArgumentParser(description="プロジェクト統合管理ツール")
            subparsers = parser.add_subparsers(dest="command", help="実行コマンド", required=True)

            # generate コマンド
            p_gen = subparsers.add_parser("generate", aliases=['g'], help="コンポーネントを生成")
            p_gen.add_argument("component", choices=list(config['generation_scripts'].keys()) + ['all'], help="生成対象")

            # run コマンド
            p_run = subparsers.add_parser("run", aliases=['r'], help="モジュールを実行")
            p_run.add_argument("component", choices=config['runnable_modules'].keys(), help="実行対象")
            p_run.add_argument('extra_args', nargs=argparse.REMAINDER)

            # tool コマンド
            p_tool = subparsers.add_parser("tool", aliases=['t'], help="各種ツールを実行")
            tool_subparsers = p_tool.add_subparsers(dest="tool_command", required=True)
            tool_subparsers.add_parser("db_view", aliases=['tdv'])
            tool_subparsers.add_parser("db_gen", aliases=['tdg'])
            p_merge = tool_subparsers.add_parser("merge", aliases=['tm'])
            p_merge.add_argument("component", help="マージ対象")

            return parser
        ```

      * `handle_command(args: argparse.Namespace, config: dict)`:
        パースされた引数に基づき、適切なコマンドを構築して `execute_command` を呼び出す。

        ```python
        def handle_command(args: argparse.Namespace, config: dict):
            python_exec = sys.executable
            
            if args.command in ["generate", "g"]:
                components_to_gen = config['generation_scripts'].keys() if args.component == 'all' else [args.component]
                for comp in components_to_gen:
                    script_path = config['generation_scripts'][comp]
                    if not execute_command([python_exec, script_path]):
                        logger.error(f"{comp} の生成に失敗しました。処理を中断します。")
                        break
            
            elif args.command in ["run", "r"]:
                module_name = config['runnable_modules'][args.component]
                execute_command([python_exec, "-m", module_name] + args.extra_args)

            elif args.command in ["tool", "t"]:
                script_path = config['tool_scripts'][args.tool_command]
                tool_args = [args.component] if hasattr(args, 'component') else []
                execute_command([python_exec, script_path] + tool_args)
        ```

  * **`main`関数の再実装**:
    上記のヘルパー関数を呼び出すシンプルな構成にする。エイリアス処理も統合する。

    ```python
    def main():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        config = load_config()
        
        # エイリアスを通常の引数リストに変換
        args_list = sys.argv[1:]
        if args_list and args_list[0] in config['aliases']:
            alias_conf = config['aliases'][args_list[0]]
            # ツールコマンドの特殊処理
            if alias_conf['command'] == 'tool' and alias_conf.get('sub_command'):
                 args_list = [alias_conf['command'], alias_conf['sub_command']]
            else:
                 args_list = [alias_conf['command']] + alias_conf['args']

        parser = setup_parser(config)
        args = parser.parse_args(args_list)
        handle_command(args, config)
    ```

### **4. 実装後のコード例（`main.py`全体像）**

```python
# main.py (Refactored)
import sys
import subprocess
import argparse
import yaml
import logging

# --- Logger Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

# --- Core Functions ---

def load_config(path="config/cli_config.yml") -> dict:
    """設定ファイルを読み込む"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.critical(f"設定ファイルが見つかりません: {path}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"設定ファイルの読み込みエラー: {e}")
        sys.exit(1)

def execute_command(command_args: list, **kwargs) -> bool:
    """指定されたコマンドをサブプロセスとして実行する"""
    logger.info(f"コマンド実行: {' '.join(command_args)}")
    try:
        subprocess.run(
            command_args, check=True, text=True, encoding='utf-8', **kwargs
        )
        logger.info("コマンド正常終了")
        return True
    except KeyboardInterrupt:
        logger.warning("ユーザーによりコマンド実行が中断されました。")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"コマンド実行エラー (コード: {e.returncode})")
        return False
    except FileNotFoundError:
        logger.error(f"実行ファイルが見つかりません: {command_args[0]}")
        return False

def setup_parser(config: dict) -> argparse.ArgumentParser:
    """設定に基づきArgumentParserを構築する"""
    parser = argparse.ArgumentParser(description="プロジェクト統合管理ツール")
    subparsers = parser.add_subparsers(dest="command", help="実行コマンド", required=True)
    
    # generate
    p_gen = subparsers.add_parser("generate", aliases=['g'], help="コンポーネントを生成")
    p_gen.add_argument("component", choices=list(config['generation_scripts'].keys()) + ['all'], help="生成対象")

    # run
    p_run = subparsers.add_parser("run", aliases=['r'], help="モジュールを実行")
    p_run.add_argument("component", choices=config['runnable_modules'].keys(), help="実行対象")
    p_run.add_argument('extra_args', nargs=argparse.REMAINDER, help="モジュールへの追加引数")

    # tool
    p_tool = subparsers.add_parser("tool", aliases=['t'], help="各種ツールを実行")
    tool_subparsers = p_tool.add_subparsers(dest="tool_command", required=True)
    tool_subparsers.add_parser("db_view", aliases=['tdv'], help="DB閲覧ツール")
    tool_subparsers.add_parser("db_gen", aliases=['tdg'], help="サンプルDB生成ツール")
    p_merge = tool_subparsers.add_parser("merge", aliases=['tm'], help="マージツール")
    p_merge.add_argument("component", help="マージ対象のコンポーネント")

    return parser

def handle_command(args: argparse.Namespace, config: dict):
    """パースされた引数に基づき処理を実行する"""
    python_exec = sys.executable

    if args.command in ["generate", "g"]:
        component_order = ["initialize", "core", "backtest", "evaluation", "rakuten", "realtrade", "dashboard", "db"]
        components_to_gen = component_order if args.component == 'all' else [args.component]
        for comp in components_to_gen:
            script_path = config['generation_scripts'][comp]
            if not execute_command([python_exec, script_path]):
                logger.error(f"{comp} の生成に失敗。処理を中断します。")
                break
    
    elif args.command in ["run", "r"]:
        module_name = config['runnable_modules'][args.component]
        execute_command([python_exec, "-m", module_name] + args.extra_args)

    elif args.command in ["tool", "t"]:
        script_key = args.tool_command
        if script_key in ["db_view", "tdv"]:
            script_key = "db_view"
        elif script_key in ["db_gen", "tdg"]:
            script_key = "db_gen"
        elif script_key in ["merge", "tm"]:
            script_key = "merge"
        
        script_path = config['tool_scripts'][script_key]
        tool_args = [args.component] if hasattr(args, 'component') and args.component else []
        execute_command([python_exec, script_path] + tool_args)

def main():
    """メイン処理"""
    config = load_config()
    
    args_list = sys.argv[1:]
    if args_list and args_list[0] in config['aliases']:
        alias_conf = config['aliases'][args_list[0]]
        args_list = [alias_conf['command']]
        if 'sub_command' in alias_conf:
             args_list.append(alias_conf['sub_command'])
        if 'args' in alias_conf:
            args_list.extend(alias_conf['args'])
    
    parser = setup_parser(config)
    args = parser.parse_args(args_list or None) # 引数がない場合はヘルプを表示
    handle_command(args, config)


if __name__ == "__main__":
    main()
```

### **5. 結論**

本設計に基づきリファクタリングを実施することで、`main.py`は責務が明確に分離され、設定主導で動作する柔軟な構造となる。これにより、将来的な機能追加や変更が容易になり、プロジェクト全体の開発効率と品質が向上する。