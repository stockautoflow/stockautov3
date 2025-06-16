from flask import Flask, render_template, jsonify, request
import chart_generator
import logging

# Flaskアプリケーションの初期化
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# アプリケーション起動時に一度だけデータをロード
with app.app_context():
    chart_generator.load_data()

@app.route('/')
def index():
    """メインページを表示する。"""
    # 選択可能な銘柄リストをテンプレートに渡す
    symbols = chart_generator.get_all_symbols(chart_generator.config.DATA_DIR)
    return render_template('index.html', symbols=symbols)

@app.route('/get_chart')
def get_chart():
    """選択された銘柄と時間足のチャートデータをJSONで返すAPI。"""
    symbol = request.args.get('symbol', type=str)
    timeframe = request.args.get('timeframe', type=str)
    
    if not symbol or not timeframe:
        return jsonify({"error": "Symbol and timeframe are required"}), 400

    # chart_generatorからチャートのJSONデータを取得
    chart_json = chart_generator.generate_chart_json(symbol, timeframe)
    
    return chart_json

if __name__ == '__main__':
    app.run(debug=True, port=5001)