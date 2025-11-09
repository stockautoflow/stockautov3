import pandas as pd

# 抽出対象のファイルパス
file_path = 'all_recommend_2025-10-16-211418.csv'
# 保存するファイルパス
output_file_path = 'kerry_all_recommend_2025-10-16-211418.csv'

try:
    # --- 1. CSVファイルの読み込み ---
    df = pd.read_csv(file_path)

    # --- 2. データの前処理（クリーニング） ---
    
    # H列「総トレード数」を数値に変換
    df['総トレード数'] = pd.to_numeric(df['総トレード数'], errors='coerce')
    
    # N列「Kerry」（ケリー基準）を数値に変換 (%を除去)
    df['Kerry_numeric'] = pd.to_numeric(df['Kerry'].astype(str).str.replace('%', ''), errors='coerce')
    
    # 処理に必要な列に欠損値(NaN)がある行を削除
    df.dropna(subset=['銘柄', '総トレード数', 'Kerry_numeric'], inplace=True)
    
    # --- 3. 抽出ステップ1：総トレード数でフィルタリング ---
    df_filtered = df[df['総トレード数'] >= 50].copy()

    # --- 4. 抽出ステップ2：各銘柄でケリー基準が最大の行を抽出 ---
    
    if df_filtered.empty:
        print("--- 実行結果 ---")
        print("条件（総トレード数 >= 50）に一致するデータ行は見つかりませんでした。")
        
    else:
        # B列「銘柄」でグループ分けし、「Kerry_numeric」が最大の行のインデックスを取得
        idx_max_kerry = df_filtered.groupby('銘柄')['Kerry_numeric'].idxmax()
        
        # 該当するインデックスの行を抽出
        df_result = df_filtered.loc[idx_max_kerry]
        
        # 結果を「Kerry_numeric」の降順（高い順）で並び替え
        df_result_sorted = df_result.sort_values(by='Kerry_numeric', ascending=False)

        # --- 5. 結果をCSVファイルに保存 ---
        
        # index=False を指定して、pandasのインデックス（行番号）がCSVに保存されないようにする
        # encoding='utf-8-sig' を指定して、Excelで開いた際の文字化けを防ぐ
        df_result_sorted.to_csv(output_file_path, index=False, encoding='utf-8-sig')
        
        print("--- 実行結果 ---")
        print(f"抽出結果を '{output_file_path}' として保存しました。")
        print(f"（{len(df_result_sorted)} 件のデータが抽出されました）")

except FileNotFoundError:
    print(f"エラー: ファイル '{file_path}' が見つかりません。")
except KeyError as e:
    print(f"エラー: {e} という列が見つかりません。CSVの列名（B列='銘柄', H列='総トレード数', N列='Kerry'）が正しいか確認してください。")
except Exception as e:
    print(f"予期せぬエラーが発生しました: {e}")