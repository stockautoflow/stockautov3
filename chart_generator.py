import os
import glob
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import yaml
import config_backtrader as config
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

price_data_cache = {}
trade_history_df = None
strategy_params = None

def load_data():
    global trade_history_df, strategy_params
    
    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    if trade_history_path:
        trade_history_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
        logger.info(f"取引履歴ファイルを読み込みました: {trade_history_path}")
    else:
        trade_history_df = pd.DataFrame()
        logger.warning("取引履歴レポートが見つかりません。チャートに取引は表示されません。")

    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f:
            strategy_params = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("strategy.yml が見つかりません。")
        strategy_params = {}

    all_symbols = get_all_symbols(config.DATA_DIR)
    for symbol in all_symbols:
        csv_pattern = os.path.join(config.DATA_DIR, f"{symbol}*.csv")
        data_files = glob.glob(csv_pattern)
        if data_files:
            df = pd.read_csv(data_files[0], index_col='datetime', parse_dates=True)
            df.columns = [x.lower() for x in df.columns]
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            price_data_cache[symbol] = df
    logger.info(f"{len(price_data_cache)} 件の銘柄データをキャッシュしました。")

def find_latest_report(report_dir, prefix):
    search_pattern = os.path.join(report_dir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def get_all_symbols(data_dir):
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    files = glob.glob(file_pattern)
    return sorted(list(set(os.path.basename(f).split('_')[0] for f in files)))

def get_trades_for_symbol(symbol):
    if trade_history_df is None or trade_history_df.empty:
        return pd.DataFrame()
    return trade_history_df[trade_history_df['銘柄'] == int(symbol)].copy()

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
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    up_move = high - high.shift()
    down_move = low.shift() - low
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-9)
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-9)
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
    if symbol not in price_data_cache: return {}
    base_df = price_data_cache[symbol]
    symbol_trades = get_trades_for_symbol(symbol)
    
    p_ind_ui = indicator_params
    p_tf_def = strategy_params['timeframes']
    p_filter_def = strategy_params.get('filters', {})

    df, title = None, ""
    sub_plots = defaultdict(lambda: False)

    if timeframe_name == 'short':
        df = base_df.copy()
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
        df = add_ichimoku(df, p_ind_ui['ichimoku']); sub_plots['ichimoku'] = True
        if p_ind_ui.get('vwap', {}).get('enabled', False): df = add_vwap(df); sub_plots['vwap'] = True
        title = f"{symbol} Short-Term ({p_tf_def['short']['compression']}min)"
    elif timeframe_name == 'medium':
        df = resample_ohlc(base_df, f"{p_tf_def['medium']['compression']}min")
        p = p_ind_ui['medium_rsi_period']
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=p).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
        rs = gain / loss.replace(0, 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs)); sub_plots['rsi'] = True
        if p_ind_ui.get('vwap', {}).get('enabled', False): df = add_vwap(df); sub_plots['vwap'] = True
        title = f"{symbol} Medium-Term ({p_tf_def['medium']['compression']}min)"
    elif timeframe_name == 'long':
        df = resample_ohlc(base_df, 'D')
        title = f'{symbol} Long-Term (Daily)'

    if df is None or df.empty: return {}
    
    df = add_adx(df, p_ind_ui['adx']['period']); sub_plots['adx'] = True
    df = add_atr(df, p_ind_ui['atr_period']); sub_plots['atr'] = True
    p = p_ind_ui['sma']
    df['sma_fast'] = df['close'].rolling(window=p['fast_period']).mean()
    df['sma_slow'] = df['close'].rolling(window=p['slow_period']).mean()
    p = p_ind_ui['bollinger']
    df['bb_middle'] = df['close'].rolling(window=p['period']).mean()
    df['bb_std'] = df['close'].rolling(window=p['period']).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * p['devfactor'])
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * p['devfactor'])
    df['ema_fast'] = df['close'].ewm(span=p_ind_ui['short_ema_fast'], adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=p_ind_ui['short_ema_slow'], adjust=False).mean()
    df['ema_long'] = df['close'].ewm(span=p_ind_ui['long_ema_period'], adjust=False).mean()

    active_subplots = [k for k, v in sub_plots.items() if v and k in ['atr', 'adx', 'rsi', 'macd', 'stoch']]
    rows = 1 + len(active_subplots)
    specs = [[{"secondary_y": True}]] + [[{'secondary_y': False}] for _ in active_subplots]
    main_height = max(0.4, 1.0 - (0.15 * len(active_subplots)))
    sub_height = (1 - main_height) / len(active_subplots) if active_subplots else 0
    row_heights = [main_height] + [sub_height] * len(active_subplots) if active_subplots else [1]
    
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, specs=specs, row_heights=row_heights)
    
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='OHLC', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
    volume_colors = ['red' if row.close > row.open else 'green' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker=dict(color=volume_colors, opacity=0.3)), secondary_y=True, row=1, col=1)

    p = p_ind_ui['bollinger']; fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, fillcolor='rgba(128,128,128,0.1)', fill='tonexty', hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_middle'], mode='lines', name=f"BB({p['period']},{p['devfactor']})", line=dict(color='gray', width=0.7, dash='dash'), connectgaps=True), row=1, col=1)
    p = p_ind_ui['sma']; fig.add_trace(go.Scatter(x=df.index, y=df['sma_fast'], mode='lines', name=f"SMA({p['fast_period']})", line=dict(color='cyan', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['sma_slow'], mode='lines', name=f"SMA({p['slow_period']})", line=dict(color='magenta', width=1), connectgaps=True), row=1, col=1)
    if sub_plots['vwap']: fig.add_trace(go.Scatter(x=df.index, y=df['vwap'], mode='lines', name='VWAP', line=dict(color='purple', width=1, dash='dot'), connectgaps=False), row=1, col=1)
    if sub_plots['ichimoku']:
        fig.add_trace(go.Scatter(x=df.index, y=df['tenkan_sen'], mode='lines', name='Tenkan', line=dict(color='blue', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['kijun_sen'], mode='lines', name='Kijun', line=dict(color='red', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['chikou_span'], mode='lines', name='Chikou', line=dict(color='#8c564b', width=1.5, dash='dash'), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_a'], mode='lines', name='Senkou A', line=dict(color='rgba(0, 200, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_b'], mode='lines', name='Senkou B', line=dict(color='rgba(200, 0, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)

    current_row = 2
    if sub_plots['atr']:
        fig.add_trace(go.Scatter(x=df.index, y=df['atr'], mode='lines', name='ATR', line=dict(color='#ff7f0e', width=1), connectgaps=True), row=current_row, col=1); fig.update_yaxes(title_text="ATR", row=current_row, col=1); current_row += 1
    if sub_plots['adx']:
        fig.add_trace(go.Scatter(x=df.index, y=df['adx'], mode='lines', name='ADX', line=dict(color='black', width=1.5), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['plus_di'], mode='lines', name='+DI', line=dict(color='green', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['minus_di'], mode='lines', name='-DI', line=dict(color='red', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="ADX", row=current_row, col=1, range=[0, 100]); current_row += 1
    if sub_plots['rsi']:
        rsi_upper = p_filter_def.get('medium_rsi_upper', 70)
        rsi_lower = p_filter_def.get('medium_rsi_lower', 30)
        fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], mode='lines', name='RSI', line=dict(color='#1f77b4', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_hline(y=rsi_upper, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=rsi_lower, line_dash="dash", line_color="green", row=current_row, col=1)
        fig.update_yaxes(title_text="RSI", row=current_row, col=1, range=[0,100]); current_row += 1
    if sub_plots['macd']:
        colors = ['red' if val > 0 else 'green' for val in df['macd_hist']]
        fig.add_trace(go.Bar(x=df.index, y=df['macd_hist'], name='MACD Hist', marker_color=colors), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['macd'], mode='lines', name='MACD', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], mode='lines', name='Signal', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="MACD", row=current_row, col=1); current_row += 1
    if sub_plots['stoch']:
        fig.add_trace(go.Scatter(x=df.index, y=df['stoch_k'], mode='lines', name='%K', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['stoch_d'], mode='lines', name='%D', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)
        fig.update_yaxes(title_text="Stoch", row=current_row, col=1, range=[0,100]); current_row += 1

    if not symbol_trades.empty:
        buy_trades = symbol_trades[symbol_trades['方向'] == 'BUY']
        sell_trades = symbol_trades[symbol_trades['方向'] == 'SELL']
        fig.add_trace(go.Scatter(x=buy_trades['エントリー日時'], y=buy_trades['エントリー価格'],mode='markers', name='Buy',marker=dict(symbol='triangle-up', color='red', size=10)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_trades['エントリー日時'], y=sell_trades['エントリー価格'],mode='markers', name='Sell', marker=dict(symbol='triangle-down', color='green', size=10)), row=1, col=1)
        
        # NOTE: Trailing stop line cannot be easily drawn as it moves. 
        # We draw the initial SL/TP lines for reference.
        for _, trade in symbol_trades.iterrows():
            if trade['テイクプロフィット価格'] > 0:
                fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['テイクプロフィット価格'],x1=trade['決済日時'], y1=trade['テイクプロフィット価格'],line=dict(color="rgba(255, 0, 0, 0.5)", width=2, dash="dash"),row=1, col=1)
            if trade['ストップロス価格'] > 0:
                fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['ストップロス価格'],x1=trade['決済日時'], y1=trade['ストップロス価格'],line=dict(color="rgba(0, 128, 0, 0.5)", width=2, dash="dash"),row=1, col=1)


    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Price", legend_title="Indicators", xaxis_rangeslider_visible=False, hovermode='x unified', autosize=True)
    fig.update_yaxes(title_text="Volume", secondary_y=True, row=1, col=1)
    if timeframe_name != 'long': fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(bounds=[15, 9], pattern="hour"), dict(bounds=[11.5, 12.5], pattern="hour")])
    else: fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    
    return pio.to_json(fig)