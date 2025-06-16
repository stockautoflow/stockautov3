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

# --- グローバル変数 ---
# データとパラメータをキャッシュして、リクエストごとに読み込まないようにする
price_data_cache = {}
trade_history_df = None
strategy_params = None

def load_data():
    """アプリケーション起動時に価格データと取引履歴を読み込む"""
    global trade_history_df, strategy_params

    # 最新の取引履歴を読み込む
    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    if trade_history_path:
        trade_history_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
        logger.info(f"取引履歴ファイルを読み込みました: {trade_history_path}")
    else:
        trade_history_df = pd.DataFrame()
        logger.warning("取引履歴レポートが見つかりません。")

    # 戦略パラメータを読み込む
    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f:
            strategy_params = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("strategy.yml が見つかりません。")
        strategy_params = {}

    # 全ての価格データをキャッシュに読み込む
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
    """指定されたプレフィックスを持つ最新のレポートファイルを見つける"""
    search_pattern = os.path.join(report_dir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def get_all_symbols(data_dir):
    """dataディレクトリから分析対象の全銘柄リストを取得する"""
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    files = glob.glob(file_pattern)
    symbols = [os.path.basename(f).split('_')[0] for f in files]
    return sorted(list(set(symbols)))

def resample_ohlc(df, rule):
    """価格データを指定の時間足にリサンプリングする"""
    df.index = pd.to_datetime(df.index)
    ohlc_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    return df.resample(rule).agg(ohlc_dict).dropna()

def generate_chart_json(symbol, timeframe_name):
    """指定された銘柄と時間足のチャートを生成し、JSON形式で返す"""
    if symbol not in price_data_cache:
        return {}

    base_df = price_data_cache[symbol]
    symbol_trades = trade_history_df[trade_history_df['銘柄'] == int(symbol)].copy() if not trade_history_df.empty else pd.DataFrame()

    p_ind = strategy_params['indicators']
    p_tf = strategy_params['timeframes']
    
    df = None
    title = ""
    
    if timeframe_name == 'short':
        df = base_df.copy()
        df['ema_fast'] = df['close'].ewm(span=p_ind['short_ema_fast'], adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=p_ind['short_ema_slow'], adjust=False).mean()
        title = f"{symbol} Short-Term ({p_tf['short']['compression']}min) Interactive"
    elif timeframe_name == 'medium':
        df = resample_ohlc(base_df, f"{p_tf['medium']['compression']}min")
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        title = f"{symbol} Medium-Term ({p_tf['medium']['compression']}min) Interactive"
    elif timeframe_name == 'long':
        df = resample_ohlc(base_df, 'D')
        df['ema_long'] = df['close'].ewm(span=p_ind['long_ema_period'], adjust=False).mean()
        title = f'{symbol} Long-Term (Daily) Interactive'

    if df is None or df.empty:
        return {}

    # --- チャートの作成 ---
    has_rsi = 'rsi' in df.columns
    specs = [[{"secondary_y": True}]]
    rows = 1
    row_heights = [1]
    if has_rsi:
        specs.extend([[{'secondary_y': False}]])
        rows = 2
        row_heights = [0.7, 0.3]
        
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05, specs=specs, row_heights=row_heights)

    # ローソク足と出来高
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='OHLC', increasing_line_color='red', decreasing_line_color='green'), secondary_y=False, row=1, col=1)
    volume_colors = ['red' if row.close > row.open else 'green' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker_color=volume_colors), secondary_y=True, row=1, col=1)

    # インジケーター
    if 'ema_fast' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_fast'], mode='lines', name=f"EMA({p_ind['short_ema_fast']})", line=dict(color='blue', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    if 'ema_slow' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_slow'], mode='lines', name=f"EMA({p_ind['short_ema_slow']})", line=dict(color='orange', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    if 'ema_long' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_long'], mode='lines', name=f"EMA({p_ind['long_ema_period']})", line=dict(color='purple', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    if has_rsi:
        p_filter = strategy_params['filters']
        fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], mode='lines', name='RSI', line=dict(color='blue', width=1), connectgaps=True), row=2, col=1)
        fig.add_hline(y=p_filter['medium_rsi_upper'], line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=p_filter['medium_rsi_lower'], line_dash="dash", line_color="green", row=2, col=1)

    # 売買マーカーとSL/TPライン
    if not symbol_trades.empty:
        # (略... 前回のコードと同じ)
        buy_trades = symbol_trades[symbol_trades['方向'] == 'BUY']
        sell_trades = symbol_trades[symbol_trades['方向'] == 'SELL']
        fig.add_trace(go.Scatter(x=buy_trades['エントリー日時'], y=buy_trades['エントリー価格'],mode='markers', name='Buy Entry',marker=dict(symbol='triangle-up', color='red', size=10)), secondary_y=False, row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_trades['エントリー日時'], y=sell_trades['エントリー価格'],mode='markers', name='Sell Entry', marker=dict(symbol='triangle-down', color='green', size=10)), secondary_y=False, row=1, col=1)
        for _, trade in symbol_trades.iterrows():
            fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['テイクプロフィット価格'],x1=trade['決済日時'], y1=trade['テイクプロフィット価格'],line=dict(color="red", width=2, dash="dash"),row=1, col=1, secondary_y=False)
            fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['ストップロス価格'],x1=trade['決済日時'], y1=trade['ストップロス価格'],line=dict(color="green", width=2, dash="dash"),row=1, col=1, secondary_y=False)


    # レイアウト設定
    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Price", legend_title="Indicators", xaxis_rangeslider_visible=False, hovermode="x unified", autosize=True)
    fig.update_yaxes(title_text="Volume", secondary_y=True, row=1, col=1)
    if has_rsi:
        fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0,100])

    if timeframe_name != 'long':
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(bounds=[15, 9], pattern="hour"), dict(bounds=[11.5, 12.5], pattern="hour")])
    else:
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        
    return pio.to_json(fig)