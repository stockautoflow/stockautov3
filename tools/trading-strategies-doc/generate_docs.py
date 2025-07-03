import yaml
import os

def generate_strategy_docs(data_file='strategies.yml', output_file='docs/index.md'):
    """
    構造化されたYAMLデータファイルから戦略を読み込み、
    MkDocs用のMarkdownファイルを生成する。
    """
    print(f"Loading data from {data_file}...")
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Data file '{data_file}' not found.")
        return
    
    print(f"Generating Markdown to {output_file}...")
    
    # docsフォルダがなければ作成
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        # -------------------------------------------------
        # ページのメインタイトル (H1)
        # -------------------------------------------------
        # 目次が正しく生成されるよう、ページ全体のタイトルとしてH1を1つだけ使用します。
        f.write("# 取引戦略ガイド\n\n")

        # -------------------------------------------------
        # 「はじめに」セクションの書き出し (H2)
        # -------------------------------------------------
        intro_data = data.get('introduction', {})
        if intro_data:
            # H1からH2に見出しレベルを変更
            f.write(f"## {intro_data.get('title', 'はじめに')}\n\n")
            f.write(f"{intro_data.get('summary', '')}\n\n")
            
            # 時間軸の説明 (H3)
            timeframes = intro_data.get('timeframes', [])
            if timeframes:
                f.write("### 3つの時間軸\n\n")
                for tf in timeframes:
                    f.write(f"- **{tf.get('name', '')}:** {tf.get('description', '')}\n")
                f.write("\n")

            # 注意書き
            note = intro_data.get('note', '')
            if note:
                 f.write(f"> {note}\n\n")
        
        f.write("---\n\n") # 水平線

        # -------------------------------------------------
        # 各戦略カテゴリーの書き出し (H2)
        # -------------------------------------------------
        categories = data.get('strategy_categories', [])
        for category in categories:
            # H1からH2に見出しレベルを変更
            f.write(f"## {category.get('category_name', '無名のカテゴリー')}\n\n")
            f.write(f"{category.get('category_description', '')}\n\n")

            # 各戦略をループ処理
            strategies = category.get('strategies', [])
            for strategy in strategies:
                name = strategy.get('name', '無名の戦略')
                logic = strategy.get('logic', 'ロジックの説明はありません。')
                
                # H2からH3に見出しレベルを変更
                f.write(f"### {name}\n\n")
                f.write(f"**ロジック概要:** {logic}\n\n")

                # サポートされていない戦略の表示
                if strategy.get('unsupported'):
                    reason = strategy.get('reason', '不明')
                    f.write(f"!!! warning \"注意: この戦略は現在サポートされていません\"\n")
                    f.write(f"    理由: {reason}\n\n")
                
                # エントリー条件の表示
                entry_conditions = strategy.get('entry_conditions')
                if entry_conditions:
                    # ロング条件
                    if 'long' in entry_conditions:
                        # Material for MkDocs のタブ機能を利用
                        f.write("=== \"ロングエントリー条件\"\n\n")
                        
                        for cond in entry_conditions['long']:
                            timeframe = cond.get('timeframe', 'N/A')
                            # タブ内のコンテンツとして4スペースのインデントを付けます
                            f.write(f"    - **{timeframe.capitalize()}:** `{cond}`\n")
                        # f.write("\n") #【修正】タブブロックを壊す可能性のある不要な改行を削除
                    
                    # ショート条件
                    if 'short' in entry_conditions:
                        f.write("=== \"ショートエントリー条件\"\n\n")
                        
                        for cond in entry_conditions['short']:
                            timeframe = cond.get('timeframe', 'N/A')
                            # タブ内のコンテンツとして4スペースのインデントを付けます
                            f.write(f"    - **{timeframe.capitalize()}:** `{cond}`\n")
                        # f.write("\n") #【修正】タブブロックを壊す可能性のある不要な改行を削除

            f.write("---\n\n")

    print("Documentation generation complete.")

if __name__ == '__main__':
    generate_strategy_docs()
