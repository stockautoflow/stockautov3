from flask import Flask, render_template, jsonify, request
import chart_generator
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

with app.app_context():
    chart_generator.load_data()

@app.route('/')
def index():
    """メインページを表示する。"""
    symbols = chart_generator.get_all_symbols(chart_generator.config.DATA_DIR)
    default_params = chart_generator.strategy_params['indicators']
    return render_template('index.html', symbols=symbols, params=default_params)

@app.route('/get_chart')
def get_chart():
    """選択された銘柄、時間足、およびパラメータに基づいてチャートデータをJSONで返す。"""
    symbol = request.args.get('symbol', type=str)
    timeframe = request.args.get('timeframe', type=str)
    
    if not symbol or not timeframe:
        return jsonify({"error": "Symbol and timeframe are required"}), 400

    default_params = chart_generator.strategy_params['indicators']
    
    # ブラウザから送信されたパラメータを取得（なければデフォルト値を使用）
    indicator_params = {
        'long_ema_period': request.args.get('long_ema_period', default=default_params['long_ema_period'], type=int),
        'medium_rsi_period': request.args.get('medium_rsi_period', default=default_params['medium_rsi_period'], type=int),
        'short_ema_fast': request.args.get('short_ema_fast', default=default_params['short_ema_fast'], type=int),
        'short_ema_slow': request.args.get('short_ema_slow', default=default_params['short_ema_slow'], type=int),
    }

    chart_json = chart_generator.generate_chart_json(symbol, timeframe, indicator_params)
    
    return chart_json

if __name__ == '__main__':
    app.run(debug=True, port=5001)