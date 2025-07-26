# SQLite データベースビューア

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
* `view_db.py`実行時に「データベースファイルが見つかりません」というエラーが出た場合は、`config.yml`に記述した`view_database_path`が正しいか確認してください。