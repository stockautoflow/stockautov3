# create_dashboard.py

import os

dashboard_files = {
    "src/dashboard/__init__.py": """
# Dashboard Package
""",

    "src/dashboard/app.py": """
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
""",

    "src/dashboard/chart_generator.py": """
import os
import glob
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import yaml
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# --- 定数定義 (新しいディレクトリ構造に対応) ---
EVALUATION_RESULTS_DIR = 'results/evaluation'
DATA_DIR = 'data'
STRATEGY_BASE_YML = 'config/strategy_base.yml'


# --- グローバル変数 ---
price_data_cache = {}
trade_history_df = None
strategy_params = None

def find_latest_report(report_dir, prefix):
    subdirs = [d for d in glob.glob(os.path.join(report_dir, '*')) if os.path.isdir(d)]
    if not subdirs:
        return None
    latest_subdir = max(subdirs, key=os.path.getctime)
    logger.info(f"最新の評価結果ディレクトリを検出: {latest_subdir}")
    search_pattern = os.path.join(latest_subdir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def load_data():
    global trade_history_df, strategy_params, price_data_cache
    
    # 戦略設定を読み込み
    try:
        with open(STRATEGY_BASE_YML, 'r', encoding='utf-8') as f:
            strategy_params = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"{STRATEGY_BASE_YML} が見つかりません。")
        strategy_params = {}

    # 全戦略評価(evaluation)の最新の取引履歴を読み込み
    trade_history_path = find_latest_report(EVALUATION_RESULTS_DIR, "all_trade_history")
    if trade_history_path:
        trade_history_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
        logger.info(f"取引履歴ファイルを読み込みました: {trade_history_path}")
    else:
        trade_history_df = pd.DataFrame()
        logger.warning(f"ディレクトリ '{EVALUATION_RESULTS_DIR}' 内の最新サブディレクトリで、'{'all_trade_history'}_*.csv' パターンのレポートが見つかりませんでした。")
        
    # 価格データキャッシュ処理
    price_data_cache = defaultdict(lambda: {'short': None, 'medium': None, 'long': None})
    timeframes_config = strategy_params.get('timeframes', {})
    all_symbols = get_all_symbols()

    for symbol in all_symbols:
        for tf_name, tf_config in timeframes_config.items():
            source_type = tf_config.get('source_type', 'resample')
            
            if tf_name == 'short' or source_type == 'direct':
                if tf_name == 'short':
                    pattern = f"{symbol}_{tf_config.get('compression', 5)}m_*.csv"
                else: 
                    pattern = tf_config.get('file_pattern', '').format(symbol=symbol)

                if not pattern:
                    continue
                
                search_pattern = os.path.join(DATA_DIR, pattern)
                data_files = glob.glob(search_pattern)

                if data_files:
                    try:
                        df = pd.read_csv(data_files[0], index_col='datetime', parse_dates=True)
                        df.columns = [x.lower() for x in df.columns]
                        if df.index.tz is not None: df.index = df.index.tz_localize(None)
                        price_data_cache[symbol][tf_name] = df
                    except Exception as e:
                        logger.error(f"[{symbol}] {tf_name}のデータ読み込みに失敗: {data_files[0]} - {e}")
                else:
                    logger.warning(f"データファイルが見つかりません: {search_pattern}")

def get_all_symbols():
    file_pattern = os.path.join(DATA_DIR, f"*_*.csv")
    files = glob.glob(file_pattern)
    return sorted(list(set(os.path.basename(f).split('_')[0] for f in files if '_' in os.path.basename(f))))

def get_trades_for_symbol(symbol):
    if trade_history_df is None or trade_history_df.empty:
        return pd.DataFrame()
    # 銘柄コードが文字列の場合と数値の場合の両方に対応
    symbol_str = str(symbol)
    symbol_int = int(symbol) if symbol.isdigit() else None
    
    trades = trade_history_df[
        (trade_history_df['銘柄'].astype(str) == symbol_str) |
        (trade_history_df['銘柄'] == symbol_int)
    ].copy()
    return trades

def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    ohlc_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    return df.resample(rule, label='right', closed='right').agg(ohlc_dict).dropna()

def add_vwap(df):
    df['date'] = df.index.date
    df['typical_price_volume'] = ((df['high'] + df['low'] + df['close']) / 3) * df['volume']
    df['cumulative_volume'] = df.groupby('date')['volume'].cumsum()
    df['cumulative_tpv'] = df.groupby('date')['typical_price_volume'].cumsum()
    df['vwap'] = df['cumulative_tpv'] / df['cumulative_volume']
    df.drop(['date', 'typical_price_volume', 'cumulative_volume', 'cumulative_tpv'], axis=1, inplace=True)
    return df

def add_atr(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.ewm(alpha=1/period, adjust=False).mean()
    return df

def add_adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean().replace(0, 1e-9)
    up_move = high - high.shift()
    down_move = low.shift() - low
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-9)
    df['adx'] = dx.ewm(alpha=1/period, adjust=False).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    return df

def add_ichimoku(df, p):
    high, low, close = df['high'], df['low'], df['close']
    df['tenkan_sen'] = (high.rolling(window=p['tenkan_period']).max() + low.rolling(window=p['tenkan_period']).min()) / 2
    df['kijun_sen'] = (high.rolling(window=p['kijun_period']).max() + low.rolling(window=p['kijun_period']).min()) / 2
    df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(p['kijun_period'])
    df['senkou_span_b'] = ((high.rolling(window=p['senkou_span_b_period']).max() + low.rolling(window=p['senkou_span_b_period']).min()) / 2).shift(p['kijun_period'])
    df['chikou_span'] = close.shift(-p['chikou_period'])
    return df

def generate_chart_json(symbol, timeframe_name, indicator_params):
    p_ind_ui = indicator_params
    p_tf_def = strategy_params.get('timeframes', {})
    tf_config = p_tf_def.get(timeframe_name, {})
    source_type = tf_config.get('source_type', 'resample')
    df = None
    title = f"{symbol} - {timeframe_name}"

    if timeframe_name == 'short' or source_type == 'direct':
        df = price_data_cache.get(symbol, {}).get(timeframe_name)
        if df is not None: title = f"{symbol} {timeframe_name.capitalize()}-Term (Direct)"
    elif source_type == 'resample':
        base_df = price_data_cache.get(symbol, {}).get('short')
        if base_df is not None:
            timeframe, compression = tf_config.get('timeframe', 'Minutes'), tf_config.get('compression', 60)
            rule_map = {'Minutes': 'T', 'Days': 'D', 'Weeks': 'W', 'Months': 'M'}
            rule = f"{compression}{rule_map.get(timeframe, 'T')}"
            df = resample_ohlc(base_df, rule)
            title = f"{symbol} {timeframe_name.capitalize()}-Term (Resampled from Short)"
        
    if df is None or df.empty:
        return pio.to_json(go.Figure(layout_title_text=f"No data available for {symbol} - {timeframe_name}"))

    sub_plots = defaultdict(bool)
    
    df = add_adx(df, p_ind_ui['adx']['period']); sub_plots['adx'] = True
    df = add_atr(df, p_ind_ui['atr_period']); sub_plots['atr'] = True
    p = p_ind_ui['sma']; df['sma_fast'] = df['close'].rolling(p['fast_period']).mean(); df['sma_slow'] = df['close'].rolling(p['slow_period']).mean()
    p = p_ind_ui['bollinger']; df['bb_middle'] = df['close'].rolling(p['period']).mean(); df['bb_std'] = df['close'].rolling(p['period']).std(); df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * p['devfactor']); df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * p['devfactor'])
    
    p = p_ind_ui['macd']
    exp1 = df['close'].ewm(span=p['fast_period'], adjust=False).mean()
    exp2 = df['close'].ewm(span=p['slow_period'], adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=p['signal_period'], adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']; sub_plots['macd'] = True
    
    p = p_ind_ui['stochastic']
    low_min = df['low'].rolling(window=p['period']).min()
    high_max = df['high'].rolling(window=p['period']).max()
    k_fast = 100 * (df['close'] - low_min) / (high_max - low_min).replace(0, 1e-9)
    df['stoch_k'] = k_fast.rolling(window=p['period_dfast']).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=p['period_dslow']).mean(); sub_plots['stoch'] = True
    
    p = p_ind_ui['medium_rsi_period']
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=p).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
    rs = gain / loss.replace(0, 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs)); sub_plots['rsi'] = True
    
    if p_ind_ui.get('vwap', {}).get('enabled', False): df = add_vwap(df);
    df = add_ichimoku(df, p_ind_ui['ichimoku'])

    active_subplots = [k for k, v in sub_plots.items() if v]
    rows = 1 + len(active_subplots)
    specs = [[{"secondary_y": True}]] + [[{}] for _ in active_subplots]
    main_height = max(0.4, 1.0 - (0.15 * len(active_subplots)))
    row_heights = [main_height] + [(1 - main_height) / len(active_subplots) if active_subplots else 0] * len(active_subplots)

    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, specs=specs, row_heights=row_heights)

    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='OHLC', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
    volume_colors = ['red' if row.close > row.open else 'green' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker=dict(color=volume_colors, opacity=0.3)), secondary_y=True, row=1, col=1)

    p = p_ind_ui['bollinger']; fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, fillcolor='rgba(128,128,128,0.1)', fill='tonexty', hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_middle'], mode='lines', name=f"BB({p['period']},{p['devfactor']})", line=dict(color='gray', width=0.7, dash='dash'), connectgaps=True), row=1, col=1)
    p = p_ind_ui['sma']; fig.add_trace(go.Scatter(x=df.index, y=df['sma_fast'], mode='lines', name=f"SMA({p['fast_period']})", line=dict(color='cyan', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['sma_slow'], mode='lines', name=f"SMA({p['slow_period']})", line=dict(color='magenta', width=1), connectgaps=True), row=1, col=1)
    if p_ind_ui.get('vwap', {}).get('enabled', False) and 'vwap' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['vwap'], mode='lines', name='VWAP', line=dict(color='purple', width=1, dash='dot'), connectgaps=False), row=1, col=1)
    
    # --- 一目均衡表の描画 ---
    fig.add_trace(go.Scatter(x=df.index, y=df['tenkan_sen'], mode='lines', name='Tenkan', line=dict(color='blue', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['kijun_sen'], mode='lines', name='Kijun', line=dict(color='red', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['chikou_span'], mode='lines', name='Chikou', line=dict(color='#8c564b', width=1.5, dash='dash'), connectgaps=True), row=1, col=1)

    # 雲の描画（改訂版）
    # スパンAとBのNaNでない共通のインデックスを取得
    idx = df[['senkou_span_a', 'senkou_span_b']].dropna().index
    a = df.loc[idx, 'senkou_span_a']
    b = df.loc[idx, 'senkou_span_b']

    # 雲の区間を特定
    group = (a > b).ne((a > b).shift()).cumsum()
    
    # 各区間ごとにループして雲を描画
    for _, g_df in df.groupby(group):
        is_positive = g_df['senkou_span_a'].iloc[0] > g_df['senkou_span_b'].iloc[0]
        fill_color = 'rgba(0, 200, 0, 0.1)' if is_positive else 'rgba(200, 0, 0, 0.1)'
        
        x = list(g_df.index) + list(g_df.index[::-1])
        y = list(g_df['senkou_span_a']) + list(g_df['senkou_span_b'][::-1])

        fig.add_trace(go.Scatter(
            x=x, y=y,
            fill='toself',
            fillcolor=fill_color,
            line_color='rgba(0,0,0,0)',
            showlegend=False,
            hoverinfo='none'
        ), row=1, col=1)

    # 凡例のために先行スパンの線も描画しておく
    fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_a'], mode='lines', name='Senkou A', line=dict(color='rgba(0, 200, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_b'], mode='lines', name='Senkou B', line=dict(color='rgba(200, 0, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)


    current_row = 2
    for ind_name in active_subplots:
        if ind_name == 'atr':
            fig.add_trace(go.Scatter(x=df.index, y=df['atr'], mode='lines', name='ATR', line=dict(color='#ff7f0e', width=1), connectgaps=True), row=current_row, col=1)
            fig.update_yaxes(title_text="ATR", row=current_row, col=1)
        elif ind_name == 'adx':
            fig.add_trace(go.Scatter(x=df.index, y=df['adx'], mode='lines', name='ADX', line=dict(color='black', width=1.5), connectgaps=True), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['plus_di'], mode='lines', name='+DI', line=dict(color='green', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['minus_di'], mode='lines', name='-DI', line=dict(color='red', width=1), connectgaps=True), row=current_row, col=1)
            fig.update_yaxes(title_text="ADX", row=current_row, col=1, range=[0, 100])
        elif ind_name == 'rsi':
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], mode='lines', name='RSI', line=dict(color='#1f77b4', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1); fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)
            fig.update_yaxes(title_text="RSI", row=current_row, col=1, range=[0,100])
        elif ind_name == 'macd':
            colors = ['red' if val > 0 else 'green' for val in df['macd_hist']]
            fig.add_trace(go.Bar(x=df.index, y=df['macd_hist'], name='MACD Hist', marker_color=colors), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd'], mode='lines', name='MACD', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], mode='lines', name='Signal', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
            fig.update_yaxes(title_text="MACD", row=current_row, col=1)
        elif ind_name == 'stoch':
            fig.add_trace(go.Scatter(x=df.index, y=df['stoch_k'], mode='lines', name='%K', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['stoch_d'], mode='lines', name='%D', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1); fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)
            fig.update_yaxes(title_text="Stoch", row=current_row, col=1, range=[0,100])
        current_row += 1

    symbol_trades = get_trades_for_symbol(symbol)
    if not symbol_trades.empty:
        buy = symbol_trades[symbol_trades['方向'] == 'BUY']; sell = symbol_trades[symbol_trades['方向'] == 'SELL']
        fig.add_trace(go.Scatter(x=buy['エントリー日時'], y=buy['エントリー価格'],mode='markers', name='Buy',marker=dict(symbol='triangle-up', color='red', size=10)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell['エントリー日時'], y=sell['エントリー価格'],mode='markers', name='Sell', marker=dict(symbol='triangle-down', color='green', size=10)), row=1, col=1)

    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Price", legend_title="Indicators", xaxis_rangeslider_visible=False, hovermode='x unified', autosize=True)
    fig.update_yaxes(title_text="Volume", secondary_y=True, row=1, col=1, showticklabels=False)
    if timeframe_name != 'long': fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(bounds=[15, 9], pattern="hour"), dict(bounds=[11.5, 12.5], pattern="hour")])
    else: fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    
    return pio.to_json(fig)
""",

    "src/dashboard/templates/index.html": """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Stock Chart</title>
    <style>
        html, body { height: 100%; margin: 0; padding: 0; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f4f4f4; }
        .container { display: flex; flex-direction: column; height: 100%; padding: 15px; box-sizing: border-box; }
        .controls { margin-bottom: 15px; display: flex; flex-wrap: wrap; gap: 10px 15px; align-items: flex-end; flex-shrink: 0; background-color: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .control-group { display: flex; flex-direction: column; }
        .control-group legend { font-weight: bold; font-size: 0.9em; margin-bottom: 5px; color: #333; padding: 0 3px; border-bottom: 2px solid #3498db;}
        .control-group fieldset { border: 1px solid #ccc; border-radius: 4px; padding: 8px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;}
        .input-item { display: flex; flex-direction: column; }
        label { font-weight: bold; font-size: 0.8em; margin-bottom: 4px; color: #555;}
        select, input[type="number"] { padding: 8px; border-radius: 4px; border: 1px solid #ddd; width: 80px; box-sizing: border-box; }
        input[type="checkbox"] { margin-left: 5px; }
        #chart-container { flex-grow: 1; position: relative; min-height: 300px; }
        #chart { width: 100%; height: 100%; }
        .loader { border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 60px; height: 60px; animation: spin 1.5s linear infinite; position: absolute; top: 50%; left: 50%; margin-top: -30px; margin-left: -30px; display: none; z-index: 10; }
        #table-container { flex-shrink: 0; max-height: 30%; overflow: auto; margin-top: 15px; }
        table { border-collapse: collapse; width: 100%; font-size: 0.8em; white-space: nowrap; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #e9ecef; position: sticky; top: 0; z-index: 1; font-weight: 600; }
        tbody tr:hover { background-color: #f5f5f5; cursor: pointer; }
        tbody tr.highlighted { background-color: #fff8dc; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
    <div class="container">
        <h1>Interactive Chart Viewer (v2)</h1>
        <div class="controls">
            <div class="control-group">
                <legend>General</legend>
                <fieldset>
                    <div class="input-item"><label for="symbol-select">銘柄</label><select id="symbol-select">{% for symbol in symbols %}<option value="{{ symbol }}">{{ symbol }}</option>{% endfor %}</select></div>
                    <div class="input-item"><label for="timeframe-select">時間足</label><select id="timeframe-select"><option value="short" selected>短期</option><option value="medium">中期</option><option value="long">長期</option></select></div>
                    <div class="input-item"><label for="vwap-enabled">VWAP</label><input type="checkbox" id="vwap-enabled" {% if params.vwap.enabled %}checked{% endif %}></div>
                </fieldset>
            </div>
            <div class="control-group">
                <legend>MA / BB</legend>
                 <fieldset>
                    <div class="input-item"><label for="sma-fast-period">SMA(速)</label><input type="number" id="sma-fast-period" value="{{ params.sma.fast_period }}"></div>
                    <div class="input-item"><label for="sma-slow-period">SMA(遅)</label><input type="number" id="sma-slow-period" value="{{ params.sma.slow_period }}"></div>
                    <div class="input-item"><label for="short-ema-fast">EMA(速)</label><input type="number" id="short-ema-fast" value="{{ params.short_ema_fast }}"></div>
                    <div class="input-item"><label for="short-ema-slow">EMA(遅)</label><input type="number" id="short-ema-slow" value="{{ params.short_ema_slow }}"></div>
                    <div class="input-item"><label for="long-ema-period">EMA(長)</label><input type="number" id="long-ema-period" value="{{ params.long_ema_period }}"></div>
                    <div class="input-item"><label for="bollinger-period">BB Period</label><input type="number" id="bollinger-period" value="{{ params.bollinger.period }}"></div>
                    <div class="input-item"><label for="bollinger-devfactor">BB StdDev</label><input type="number" id="bollinger-devfactor" step="0.1" value="{{ params.bollinger.devfactor }}"></div>
                 </fieldset>
            </div>
            <div class="control-group">
                <legend>Oscillators / Volatility</legend>
                 <fieldset>
                    <div class="input-item"><label for="medium-rsi-period">RSI</label><input type="number" id="medium-rsi-period" value="{{ params.medium_rsi_period }}"></div>
                    <div class="input-item"><label for="macd-fast-period">MACD(速)</label><input type="number" id="macd-fast-period" value="{{ params.macd.fast_period }}"></div>
                    <div class="input-item"><label for="macd-slow-period">MACD(遅)</label><input type="number" id="macd-slow-period" value="{{ params.macd.slow_period }}"></div>
                    <div class="input-item"><label for="macd-signal-period">MACD(Sig)</label><input type="number" id="macd-signal-period" value="{{ params.macd.signal_period }}"></div>
                    <div class="input-item"><label for="stoch-period">Stoch %K</label><input type="number" id="stoch-period" value="{{ params.stochastic.period }}"></div>
                    <div class="input-item"><label for="atr-period">ATR</label><input type="number" id="atr-period" value="{{ params.atr_period }}"></div>
                    <div class="input-item"><label for="adx-period">ADX</label><input type="number" id="adx-period" value="{{ params.adx.period }}"></div>
                 </fieldset>
            </div>
            <div class="control-group">
                <legend>Ichimoku (Short Only)</legend>
                 <fieldset>
                    <div class="input-item"><label for="ichimoku-tenkan-period">Tenkan</label><input type="number" id="ichimoku-tenkan-period" value="{{ params.ichimoku.tenkan_period }}"></div>
                    <div class="input-item"><label for="ichimoku-kijun-period">Kijun</label><input type="number" id="ichimoku-kijun-period" value="{{ params.ichimoku.kijun_period }}"></div>
                    <div class="input-item"><label for="ichimoku-senkou-b-period">Senkou B</label><input type="number" id="ichimoku-senkou-b-period" value="{{ params.ichimoku.senkou_span_b_period }}"></div>
                    <div class="input-item"><label for="ichimoku-chikou-period">Chikou</label><input type="number" id="ichimoku-chikou_period" value="{{ params.ichimoku.chikou_period }}"></div>
                 </fieldset>
            </div>
        </div>
        <div id="chart-container"><div id="loader" class="loader"></div><div id="chart"></div></div>
        <div id="table-container">
             <table id="trades-table">
                <thead><tr>
                    <th>方向</th><th>数量</th><th>エントリー価格</th><th>日時</th><th>根拠</th>
                    <th>決済価格</th><th>日時</th><th>根拠</th><th>損益</th><th>損益(込)</th>
                    <th>SL</th><th>TP</th>
                </tr></thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <script>
        const controls = document.querySelectorAll('.controls select, .controls input');
        const chartDiv = document.getElementById('chart');
        const loader = document.getElementById('loader');
        const tableBody = document.querySelector("#trades-table tbody");

        function formatDateTime(ts) { return ts ? new Date(ts).toLocaleString('ja-JP', { year: '2-digit', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''; }
        function formatNumber(num, digits = 2) { return (num === null || typeof num === 'undefined' || isNaN(num)) ? '' : num.toFixed(digits); }

        function updateChart() {
            loader.style.display = 'block';
            chartDiv.style.opacity = '0.3';

            const params = new URLSearchParams();
            params.append('symbol', document.getElementById('symbol-select').value);
            params.append('timeframe', document.getElementById('timeframe-select').value);
            document.querySelectorAll('.controls input').forEach(input => {
                const key = input.id;
                const value = input.type === 'checkbox' ? input.checked : input.value;
                params.append(key, value);
            });

            fetch(`/get_chart_data?${params.toString()}`)
                .then(response => response.json())
                .then(data => {
                    if(data.error) {
                        console.error('API Error:', data.error);
                        loader.style.display = 'none';
                        chartDiv.style.opacity = '1';
                        return;
                    }
                    const chartJson = data.chart ? JSON.parse(data.chart) : { data: [], layout: {} };
                    const trades = data.trades ? JSON.parse(data.trades) : [];
                    
                    Plotly.newPlot('chart', chartJson.data, chartJson.layout, {responsive: true, scrollZoom: true});
                    buildTradeTable(trades);
                })
                .catch(error => console.error('Error fetching data:', error))
                .finally(() => {
                    loader.style.display = 'none';
                    chartDiv.style.opacity = '1';
                    window.dispatchEvent(new Event('resize'));
                });
        }

        function buildTradeTable(trades) {
            tableBody.innerHTML = '';
            trades.forEach(trade => {
                const row = tableBody.insertRow();
                row.innerHTML = `
                    <td style="color:${trade['方向'] === 'BUY' ? 'red' : 'green'}">${trade['方向']}</td><td>${formatNumber(trade['数量'], 2)}</td>
                    <td>${formatNumber(trade['エントリー価格'])}</td><td>${formatDateTime(trade['エントリー日時'])}</td><td>${trade['エントリー根拠'] || ''}</td>
                    <td>${formatNumber(trade['決済価格'])}</td><td>${formatDateTime(trade['決済日時'])}</td><td>${trade['決済根拠'] || ''}</td>
                    <td style="color:${(trade['損益']||0) >= 0 ? 'blue' : 'red'}">${formatNumber(trade['損益'])}</td>
                    <td style="color:${(trade['損益(手数料込)']||0) >= 0 ? 'blue' : 'red'}">${formatNumber(trade['損益(手数料込)'])}</td>
                    <td>${formatNumber(trade['ストップロス価格'])}</td><td>${formatNumber(trade['テイクプロフィット価格'])}</td>
                `;
                row.addEventListener('click', (event) => {
                    document.querySelectorAll('#trades-table tbody tr').forEach(tr => tr.classList.remove('highlighted'));
                    event.currentTarget.classList.add('highlighted');
                    highlightTradeOnChart(trade);
                });
            });
        }

        function highlightTradeOnChart(trade) {
            const entryTime = trade['エントリー日時'];
            const exitTime = trade['決済日時'];
            if (!entryTime || !exitTime) return;

            const currentLayout = chartDiv.layout;
            const newShapes = (currentLayout.shapes || []).filter(s => s.name !== 'highlight-shape');
            newShapes.push({
                name: 'highlight-shape', type: 'rect', xref: 'x', yref: 'paper',
                x0: entryTime, y0: 0, x1: exitTime, y1: 1,
                fillcolor: 'rgba(255, 255, 0, 0.2)', line: { width: 0 }, layer: 'below'
            });
            Plotly.relayout('chart', { shapes: newShapes });
        }

        window.addEventListener('resize', () => { if(chartDiv.childElementCount > 0) Plotly.Plots.resize(chartDiv); });
        controls.forEach(control => control.addEventListener('change', updateChart));
        document.addEventListener('DOMContentLoaded', updateChart);
    </script>
</body>
</html>
"""
}

def create_files(files_dict):
    """
    指定された辞書に基づいてプロジェクトファイルとディレクトリを生成します。
    """
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        content = content.strip()
        
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"ファイルを作成/更新しました: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("Dashboardコンポーネントのファイルを生成します...")
    create_files(dashboard_files)
    print("\\nDashboardコンポーネントのファイル生成が完了しました。")
    print("次に、'python -m src.dashboard.app' を実行してWeb UIを起動してください。")