from flask import Flask, render_template, jsonify, request
import chart_generator
import logging
import pandas as pd

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

@app.route('/get_chart_data')
def get_chart_data():
    """チャートと取引履歴のデータをまとめてJSONで返す。"""
    symbol = request.args.get('symbol', type=str)
    timeframe = request.args.get('timeframe', type=str)
    
    if not symbol or not timeframe:
        return jsonify({"error": "Symbol and timeframe are required"}), 400

    default_params = chart_generator.strategy_params['indicators']
    macd_defaults = default_params.get('macd', {})
    
    indicator_params = {
        'long_ema_period': request.args.get('long_ema_period', default=default_params['long_ema_period'], type=int),
        'medium_rsi_period': request.args.get('medium_rsi_period', default=default_params['medium_rsi_period'], type=int),
        'short_ema_fast': request.args.get('short_ema_fast', default=default_params['short_ema_fast'], type=int),
        'short_ema_slow': request.args.get('short_ema_slow', default=default_params['short_ema_slow'], type=int),
        'macd': {
            'fast_period': request.args.get('macd_fast_period', default=macd_defaults.get('fast_period'), type=int),
            'slow_period': request.args.get('macd_slow_period', default=macd_defaults.get('slow_period'), type=int),
            'signal_period': request.args.get('macd_signal_period', default=macd_defaults.get('signal_period'), type=int),
        }
    }

    chart_json = chart_generator.generate_chart_json(symbol, timeframe, indicator_params)
    trades_df = chart_generator.get_trades_for_symbol(symbol)
    
    # NaN値をNoneに変換 (JSONシリアライズのため)
    trades_df = trades_df.where(pd.notnull(trades_df), None)

    # 損益を小数点以下2桁に丸める
    trades_df['損益'] = trades_df['損益'].round(2)
    trades_df['損益(手数料込)'] = trades_df['損益(手数料込)'].round(2)

    trades_json = trades_df.to_json(orient='records')
    
    return jsonify(chart=chart_json, trades=trades_json)

if __name__ == '__main__':
    app.run(debug=True, port=5001)