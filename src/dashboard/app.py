from flask import Flask, render_template, jsonify, request
from . import chart_generator  # 変更: 相対インポート
import logging
import pandas as pd

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# アプリケーションコンテキスト内でデータをロード
with app.app_context():
    chart_generator.load_data()

@app.route('/')
def index():
    # 変更: パス参照をchart_generator内部に委譲
    symbols = chart_generator.get_all_symbols()
    default_params = chart_generator.strategy_params.get('indicators', {})
    return render_template('index.html', symbols=symbols, params=default_params)

@app.route('/get_chart_data')
def get_chart_data():
    try:
        symbol = request.args.get('symbol', type=str)
        timeframe = request.args.get('timeframe', type=str)
        if not symbol or not timeframe:
            return jsonify({"error": "Symbol and timeframe are required"}), 400

        p = chart_generator.strategy_params.get('indicators', {})
        indicator_params = {
            'long_ema_period': request.args.get('long-ema-period', p.get('long_ema_period'), type=int),
            'medium_rsi_period': request.args.get('medium-rsi-period', p.get('medium_rsi_period'), type=int),
            'short_ema_fast': request.args.get('short-ema-fast', p.get('short_ema_fast'), type=int),
            'short_ema_slow': request.args.get('short-ema-slow', p.get('short_ema_slow'), type=int),
            'atr_period': request.args.get('atr-period', p.get('atr_period'), type=int),
            'adx': {'period': request.args.get('adx-period', p.get('adx', {}).get('period'), type=int)},
            'macd': {'fast_period': request.args.get('macd-fast-period', p.get('macd', {}).get('fast_period'), type=int),
                     'slow_period': request.args.get('macd-slow-period', p.get('macd', {}).get('slow_period'), type=int),
                     'signal_period': request.args.get('macd-signal-period', p.get('macd', {}).get('signal_period'), type=int)},
            'stochastic': {'period': request.args.get('stoch-period', p.get('stochastic', {}).get('period'), type=int),
                           'period_dfast': request.args.get('stoch-period-dfast', p.get('stochastic', {}).get('period_dfast'), type=int),
                           'period_dslow': request.args.get('stoch-period-dslow', p.get('stochastic', {}).get('period_dslow'), type=int)},
            'bollinger': {'period': request.args.get('bollinger-period', p.get('bollinger', {}).get('period'), type=int),
                          'devfactor': request.args.get('bollinger-devfactor', p.get('bollinger', {}).get('devfactor'), type=float)},
            'sma': {'fast_period': request.args.get('sma-fast-period', p.get('sma',{}).get('fast_period'), type=int),
                    'slow_period': request.args.get('sma-slow-period', p.get('sma',{}).get('slow_period'), type=int)},
            'vwap': {'enabled': request.args.get('vwap-enabled') == 'true'},
            'ichimoku': {'tenkan_period': request.args.get('ichimoku-tenkan-period', p.get('ichimoku', {}).get('tenkan_period'), type=int),
                         'kijun_period': request.args.get('ichimoku-kijun-period', p.get('ichimoku', {}).get('kijun_period'), type=int),
                         'senkou_span_b_period': request.args.get('ichimoku-senkou-b-period', p.get('ichimoku', {}).get('senkou_span_b_period'), type=int),
                         'chikou_period': request.args.get('ichimoku-chikou-period', p.get('ichimoku', {}).get('chikou_period'), type=int)}
        }

        chart_json = chart_generator.generate_chart_json(symbol, timeframe, indicator_params)
        trades_df = chart_generator.get_trades_for_symbol(symbol)

        trades_df = trades_df.where(pd.notnull(trades_df), None)
        for col in ['損益', '損益(手数料込)']:
            if col in trades_df.columns: trades_df[col] = trades_df[col].round(2)
        trades_json = trades_df.to_json(orient='records')

        return jsonify(chart=chart_json, trades=trades_json)
    except Exception as e:
        app.logger.error(f"Error in /get_chart_data: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5002)