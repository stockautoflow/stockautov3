import os
import glob
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import yaml
import config_backtrader as config
import logging

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
        logger.warning("取引履歴レポートが見つかりません。")
    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f: strategy_params = yaml.safe_load(f)
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
            if df.index.tz is not None: df.index = df.index.tz_localize(None)
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
    if trade_history_df is None or trade_history_df.empty: return pd.DataFrame()
    return trade_history_df[trade_history_df['銘柄'] == int(symbol)].copy()

def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    ohlc_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    return df.resample(rule).agg(ohlc_dict).dropna()

def add_vwap(df):
    df['date'] = df.index.date
    df['typical_price_volume'] = ((df['high'] + df['low'] + df['close']) / 3) * df['volume']
    df['cumulative_volume'] = df.groupby('date')['volume'].cumsum()
    df['cumulative_tpv'] = df.groupby('date')['typical_price_volume'].cumsum()
    df['vwap'] = df['cumulative_tpv'] / df['cumulative_volume']
    df.drop(['date', 'typical_price_volume', 'cumulative_volume', 'cumulative_tpv'], axis=1, inplace=True)
    return df

def add_atr(df, params):
    p = params.get('atr', {})
    period = p.get('period', 14)
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    return df

def add_adx(df, params):
    p = params.get('adx', {})
    period = p.get('period', 14)
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    up_move = high - high.shift()
    down_move = low.shift() - low
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-9)
    df['adx'] = dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    return df

def add_ichimoku(df, params):
    p = params['ichimoku']
    high, low, close = df['high'], df['low'], df['close']
    tenkan_high = high.rolling(window=p['tenkan_period']).max()
    tenkan_low = low.rolling(window=p['tenkan_period']).min()
    df['tenkan_sen'] = (tenkan_high + tenkan_low) / 2
    kijun_high = high.rolling(window=p['kijun_period']).max()
    kijun_low = low.rolling(window=p['kijun_period']).min()
    df['kijun_sen'] = (kijun_high + kijun_low) / 2
    df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(p['kijun_period'])
    senkou_b_high = high.rolling(window=p['senkou_span_b_period']).max()
    senkou_b_low = low.rolling(window=p['senkou_span_b_period']).min()
    df['senkou_span_b'] = ((senkou_b_high + senkou_b_low) / 2).shift(p['kijun_period'])
    df['chikou_span'] = close.shift(-p['chikou_period'])
    return df

def generate_chart_json(symbol, timeframe_name, indicator_params):
    if symbol not in price_data_cache: return {}
    base_df = price_data_cache[symbol]
    symbol_trades = get_trades_for_symbol(symbol)
    p_ind = indicator_params
    p_tf = strategy_params['timeframes']
    p_filter = strategy_params['filters']
    df, title = None, ""
    has_ichimoku, has_macd, has_stoch, has_rsi, has_atr, has_vwap = False, False, False, False, False, False

    if timeframe_name == 'short':
        df = base_df.copy()
        df = add_ichimoku(df, p_ind); has_ichimoku = True
        exp1 = df['close'].ewm(span=p_ind['macd']['fast_period'], adjust=False).mean()
        exp2 = df['close'].ewm(span=p_ind['macd']['slow_period'], adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=p_ind['macd']['signal_period'], adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']; has_macd = True
        low_min = df['low'].rolling(window=p_ind['stochastic']['period']).min()
        high_max = df['high'].rolling(window=p_ind['stochastic']['period']).max()
        k_fast = 100 * (df['close'] - low_min) / (high_max - low_min)
        df['stoch_k'] = k_fast.rolling(window=p_ind['stochastic']['period_dfast']).mean()
        df['stoch_d'] = df['stoch_k'].rolling(window=p_ind['stochastic']['period_dslow']).mean(); has_stoch = True
        if p_ind.get('vwap', {}).get('enabled', False): df = add_vwap(df); has_vwap = True
        title = f"{symbol} Short-Term ({p_tf['short']['compression']}min) Interactive"
    elif timeframe_name == 'medium':
        df = resample_ohlc(base_df, f"{p_tf['medium']['compression']}min")
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs)); has_rsi = True
        if p_ind.get('vwap', {}).get('enabled', False): df = add_vwap(df); has_vwap = True
        title = f"{symbol} Medium-Term ({p_tf['medium']['compression']}min) Interactive"
    elif timeframe_name == 'long':
        df = resample_ohlc(base_df, 'D')
        title = f'{symbol} Long-Term (Daily) Interactive'

    if df is None or df.empty: return {}
    
    # --- Add all indicators to the dataframe ---
    p_sma = p_ind.get('sma', {})
    df['sma_fast'] = df['close'].rolling(window=p_sma.get('fast_period')).mean()
    df['sma_slow'] = df['close'].rolling(window=p_sma.get('slow_period')).mean()
    
    df['ema_fast'] = df['close'].ewm(span=p_ind['short_ema_fast'], adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=p_ind['short_ema_slow'], adjust=False).mean()
    df['ema_long'] = df['close'].ewm(span=p_ind['long_ema_period'], adjust=False).mean()

    df = add_adx(df, p_ind); has_adx = True
    df = add_atr(df, p_ind); has_atr = True
    
    p_bb = p_ind.get('bollinger', {})
    bb_period, bb_dev = p_bb.get('period', 20), p_bb.get('devfactor', 2.0)
    df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
    df['bb_std'] = df['close'].rolling(window=bb_period).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * bb_dev)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * bb_dev)

    sub_indicators = [has_atr, has_adx, has_rsi, has_macd, has_stoch]
    rows = 1 + sum(sub_indicators)
    specs = [[{"secondary_y": True}]] + [[{'secondary_y': False}] for _ in range(sum(sub_indicators))]
    main_height = 1.0 - (0.15 * sum(sub_indicators))
    sub_height = (1 - main_height) / sum(sub_indicators) if sum(sub_indicators) > 0 else 0
    row_heights = [main_height] + [sub_height] * sum(sub_indicators) if sum(sub_indicators) > 0 else [1]
    
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, specs=specs, row_heights=row_heights)
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='OHLC', increasing_line_color='red', decreasing_line_color='green'), secondary_y=False, row=1, col=1)
    volume_colors = ['red' if row.close > row.open else 'green' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker=dict(color=volume_colors, opacity=0.3)), secondary_y=True, row=1, col=1)
    
    # Add lines
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, hoverinfo='skip'), secondary_y=False, row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, fillcolor='rgba(128,128,128,0.1)', fill='tonexty', hoverinfo='skip'), secondary_y=False, row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_middle'], mode='lines', name=f"BB({bb_period}, {bb_dev})", line=dict(color='gray', width=0.7, dash='dash'), connectgaps=True), secondary_y=False, row=1, col=1)
    
    if has_vwap:
        fig.add_trace(go.Scatter(x=df.index, y=df['vwap'], mode='lines', name='VWAP', line=dict(color='purple', width=1, dash='dot'), connectgaps=False), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['sma_fast'], mode='lines', name=f"SMA({p_sma.get('fast_period')})", line=dict(color='cyan', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['sma_slow'], mode='lines', name=f"SMA({p_sma.get('slow_period')})", line=dict(color='magenta', width=1), connectgaps=True), row=1, col=1)
    
    if timeframe_name == 'short':
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_fast'], mode='lines', name=f"EMA({p_ind['short_ema_fast']})", line=dict(color='#007bff', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_slow'], mode='lines', name=f"EMA({p_ind['short_ema_slow']})", line=dict(color='#ff7f0e', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    if timeframe_name == 'long':
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_long'], mode='lines', name=f"EMA({p_ind['long_ema_period']})", line=dict(color='#9467bd', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    
    if has_ichimoku:
        fig.add_trace(go.Scatter(x=df.index, y=df['tenkan_sen'], mode='lines', name='転換線', line=dict(color='blue', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['kijun_sen'], mode='lines', name='基準線', line=dict(color='red', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['chikou_span'], mode='lines', name='遅行スパン', line=dict(color='#8c564b', width=1.5, dash='dash'), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_a'], mode='lines', name='先行A', line=dict(color='rgba(0, 200, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_b'], mode='lines', name='先行B', line=dict(color='rgba(200, 0, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)

    current_row = 2
    if has_atr:
        fig.add_trace(go.Scatter(x=df.index, y=df['atr'], mode='lines', name='ATR', line=dict(color='#ff7f0e', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="ATR", row=current_row, col=1)
        current_row += 1
    if has_adx:
        fig.add_trace(go.Scatter(x=df.index, y=df['adx'], mode='lines', name='ADX', line=dict(color='black', width=1.5), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['plus_di'], mode='lines', name='+DI', line=dict(color='green', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['minus_di'], mode='lines', name='-DI', line=dict(color='red', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="ADX", row=current_row, col=1, range=[0, 100])
        current_row += 1
    if has_rsi:
        fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], mode='lines', name='RSI', line=dict(color='#1f77b4', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_hline(y=p_filter['medium_rsi_upper'], line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=p_filter['medium_rsi_lower'], line_dash="dash", line_color="green", row=current_row, col=1)
        fig.update_yaxes(title_text="RSI", row=current_row, col=1, range=[0,100])
        current_row += 1
    if has_macd:
        macd_hist_colors = ['red' if val > 0 else 'green' for val in df['macd_hist']]
        fig.add_trace(go.Bar(x=df.index, y=df['macd_hist'], name='MACD Hist', marker_color=macd_hist_colors), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['macd'], mode='lines', name='MACD', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], mode='lines', name='Signal', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="MACD", row=current_row, col=1)
        current_row += 1
    if has_stoch:
        fig.add_trace(go.Scatter(x=df.index, y=df['stoch_k'], mode='lines', name='%K', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['stoch_d'], mode='lines', name='%D', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)
        fig.update_yaxes(title_text="Stoch", row=current_row, col=1, range=[0,100])

    if not symbol_trades.empty:
        buy_trades = symbol_trades[symbol_trades['方向'] == 'BUY']; sell_trades = symbol_trades[symbol_trades['方向'] == 'SELL']
        fig.add_trace(go.Scatter(x=buy_trades['エントリー日時'], y=buy_trades['エントリー価格'],mode='markers', name='Buy',marker=dict(symbol='triangle-up', color='red', size=10)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_trades['エントリー日時'], y=sell_trades['エントリー価格'],mode='markers', name='Sell', marker=dict(symbol='triangle-down', color='green', size=10)), row=1, col=1)
        for _, trade in symbol_trades.iterrows():
            fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['テイクプロフィット価格'],x1=trade['決済日時'], y1=trade['テイクプロフィット価格'],line=dict(color="red", width=2, dash="dash"),row=1, col=1)
            fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['ストップロス価格'],x1=trade['決済日時'], y1=trade['ストップロス価格'],line=dict(color="green", width=2, dash="dash"),row=1, col=1)

    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Price", legend_title="Indicators", xaxis_rangeslider_visible=False, hovermode='x unified', autosize=True)
    fig.update_yaxes(title_text="Volume", secondary_y=True, row=1, col=1)
    if timeframe_name != 'long': fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(bounds=[15, 9], pattern="hour"), dict(bounds=[11.5, 12.5], pattern="hour")])
    else: fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return pio.to_json(fig)