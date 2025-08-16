import os

# ==============================================================================
# ファイル: create_db.py
# 実行方法: python create_db.py
# How to update:(venv) C:\stockautov3>python tools/merge/merge_changes.py scripts/create_db.py
# 説明:
#   このスクリプトは、SQLiteデータベースの内容を表示し、
#   サンプルDBを作成するための一連のユーティリティファイルを生成します。
# ==============================================================================

project_files = {
    "tools/db/generate_sample_db.py": """import sqlite3
import os
import yaml

def create_sample_database(db_file):
    \"\"\"
    指定された内容で新しいSQLiteデータベースを作成します。
    既にファイルが存在する場合は上書きします。
    \"\"\"
    # ファイルのディレクトリが存在しない場合は作成
    dir_name = os.path.dirname(db_file)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"既存のファイル '{db_file}' を削除しました。")

    conn = None
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # 'positions' テーブルを作成
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT,
                size REAL,
                price REAL,
                entry_datetime TEXT
            )
        ''')

        # サンプルデータを挿入
        positions_data = [
            ('1332', 1100.0, 2222.0, '2025-01-01T09:09:09'),
            ('1605', 4400.0, 5555.0, '2025-04-04T14:04:04')
        ]
        cursor.executemany(
            'INSERT INTO positions (symbol, size, price, entry_datetime) VALUES (?, ?, ?, ?)',
            positions_data
        )

        conn.commit()
        print(f"✅ サンプルデータベース '{db_file}' を正常に作成しました。")

    except sqlite3.Error as e:
        print(f"❌ データベース作成エラー: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # --- ▼▼▼ ここから変更 ▼▼▼ ---
    # スクリプト自身の場所を基準にconfig.ymlへの絶対パスを構築
    script_dir = os.path.dirname(os.path.abspath(__file__))
    CONFIG_FILE = os.path.join(script_dir, 'config.yml')
    # --- ▲▲▲ ここまで変更 ▲▲▲ ---
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if not config or 'sample_database_path' not in config:
                print(f"❌ エラー: '{CONFIG_FILE}' に 'sample_database_path' キーが見つかりません。")
            else:
                db_path = config['sample_database_path']
                create_sample_database(db_path)
    except FileNotFoundError:
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' が見つかりません。")
    except yaml.YAMLError as e:
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' の形式が正しくありません。 詳細: {e}")""",

    "tools/db/view_db.py": """import sqlite3
import yaml
import os # <--- 追加

def display_all_tables_data(db_file):
    \"\"\"
    SQLiteデータベース内のすべてのテーブルとそのデータを表示します。
    \"\"\"
    conn = None
    try:
        # 読み取り専用モードで接続
        conn = sqlite3.connect(f'file:{db_file}?mode=ro', uri=True)
        cursor = conn.cursor()
        print(f"✅ データベース: '{db_file}' に接続しました。\\n")

        # テーブル一覧を取得
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("データベースにテーブルが見つかりませんでした。")
            return

        print("--- データベース内のテーブル一覧とデータ ---")
        for table_tuple in tables:
            table_name = table_tuple[0]
            print(f"\\n--- テーブル: '{table_name}' ---")

            try:
                cursor.execute(f"SELECT * FROM {table_name};")
                rows = cursor.fetchall()
                column_names = [description[0] for description in cursor.description]
                print("カラム:", column_names)

                if not rows:
                    print(f"テーブル '{table_name}' は空です。")
                else:
                    for row in rows:
                        print(row)
            except sqlite3.OperationalError as e:
                print(f"❌ エラー: テーブル '{table_name}' のデータを取得できませんでした。詳細: {e}")

    except sqlite3.OperationalError as e:
        print(f"❌ SQLite接続エラー: データベースファイルが見つからないか、読み取り専用で開けませんでした。パスを確認してください。 詳細: {e}")
    except Exception as e:
        print(f"❌ 予期せぬエラーが発生しました: {e}")
    finally:
        if conn:
            conn.close()
            print(f"\\n✅ データベース: '{db_file}' から切断しました。")

if __name__ == "__main__":
    # --- ▼▼▼ ここから変更 ▼▼▼ ---
    # スクリプト自身の場所を基準にconfig.ymlへの絶対パスを構築
    script_dir = os.path.dirname(os.path.abspath(__file__))
    CONFIG_FILE = os.path.join(script_dir, 'config.yml')
    # --- ▲▲▲ ここまで変更 ▲▲▲ ---
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if not config or 'view_database_path' not in config:
                print(f"❌ エラー: '{CONFIG_FILE}' に 'view_database_path' キーが見つかりません。")
            else:
                db_path = config['view_database_path']
                display_all_tables_data(db_path)
    except FileNotFoundError:
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' が見つかりません。")
    except yaml.YAMLError as e:
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' の形式が正しくありません。 詳細: {e}")""",

    "tools/db/config.yml": """# view_db.py が参照するSQLiteデータベースのパス
$view_database_path: 'results/realtrade/realtrade_state.db'
# view_database_path: '../../results/realtrade/realtrade_state.db'
view_database_path: 'C:\\stockautov3\\log\\notification_history.db'


# generate_sample_db.py が生成するサンプルデータベースのパス
sample_database_path: 'results/realtrade/sample_database.db'
# sample_database_path: '../../results/realtrade/sample_database.db'""",

    "tools/db/requirements.txt": """
PyYAML>=6.0
""",

    "tools/db/README.md": """# SQLite データベースビューア

このツールは、SQLiteデータベースの中身を簡単に確認するためのユーティリティセットです。

## 機能一覧

* **`view_db.py`**: 設定ファイル (`config.yml`) に基づき、指定されたデータベースの内容をコンソールに表示します。
* **`generate_sample_db.py`**: 動作確認に使用できる、サンプルデータ入りのデータベースを作成します。

## 動作環境

* Python 3.6 以上

## 🛠️ インストール方法

1.  まず、これらのファイルを同じディレクトリにダウンロードまたは配置します。

2.  ターミナル（コマンドプロンプト）を開き、そのディレクトリに移動して、以下のコマンドを実行して必要なライブラリをインストールします。

    ```bash
    pip install -r requirements.txt
    ```

## 🚀 使用方法

### 1. 表示/生成対象データベースの設定

`config.yml` ファイルをテキストエディタで開き、各パスを必要に応じて編集します。

* `view_database_path`: `view_db.py`で中身を閲覧したいデータベースのパスを指定します。
* `sample_database_path`: `generate_sample_db.py`で作成するサンプルデータベースのファイルパスを指定します。

```yaml
# 例:
view_database_path: '../../results/realtrade/realtrade_state.db'
sample_database_path: '../../results/realtrade/sample_database.db'
```

### 2. (任意) サンプルデータベースの作成

設定ファイルを確認した後、以下のコマンドでサンプルデータベースを作成できます。

```bash
python generate_sample_db.py
```config.yml`の`sample_database_path`で指定した場所にファイルが作成されます。

### 3. データベース内容の表示

`config.yml`の`view_database_path`に閲覧したいDBのパスが設定されていることを確認し、以下のコマンドを実行します。

```bash
python view_db.py
```
ターミナルに、指定したデータベースのテーブル情報やデータが表示されます。

## ⚠️ 注意点

* 各スクリプト実行時に「設定ファイルが見つかりません」というエラーが出た場合は、`config.yml`が同じディレクトリにあるか確認してください。
* `view_db.py`実行時に「データベースファイルが見つかりません」というエラーが出た場合は、`config.yml`に記述した`view_database_path`が正しいか確認してください。"""
}




def create_files(files_dict):
    """
    辞書からファイル名と内容を読み取り、ファイルを作成する。
    ディレクトリが存在しない場合は作成する。
    """
    for filename, content in files_dict.items():
        # ディレクトリ部分があれば、その存在を確認してなければ作成
        if os.path.dirname(filename):
            os.makedirs(os.path.dirname(filename), exist_ok=True)

        # contentの両端の空白を削除してから書き込む
        content = content.strip()
        try:
            # newline='\n' を指定して、WindowsでのCRLF問題を回避
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"  - ファイル作成: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- SQLite Utils プロジェクトの生成を開始します ---")
    create_files(project_files)
    print("\nプロジェクトの生成が完了しました。")
    print("\n次のステップ:")
    print("1. (ターミナルで) pip install -r requirements.txt")
    print("2. (ターミナルで) python generate_sample_db.py")
    print("3. (ターミナルで) python view_db.py")
