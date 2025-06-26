import backtrader as bt
import abc

class RealtimeDataFeed(bt.feeds.PandasData):
    """
    リアルタイムデータをbacktraderに供給するためのカスタムデータフィード。
    PandasDataを継承し、新しいデータを動的に追加する機能を持つ。
    """
    def push_data(self, data_dict):
        """
        新しいローソク足データをフィードに追加します。
        :param data_dict: {'datetime': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}
        """
        # このメソッドは、backtraderの内部構造にアクセスするため、
        # 慎重な実装が必要です。
        # 簡単な例として、新しい行を追加する処理を想定しますが、
        # 実際にはより複雑なハンドリングが必要になる場合があります。
        pass

class DataFetcher(metaclass=abc.ABCMeta):
    """
    証券会社APIから価格データを取得するためのインターフェース（抽象基底クラス）。
    このクラスを継承して、各証券会社専用のデータ取得クラスを実装します。
    """
    def __init__(self, symbols, config):
        """
        :param symbols: 取得対象の銘柄コードのリスト
        :param config: 設定オブジェクト
        """
        self.symbols = symbols
        self.config = config
        self.data_feeds = {s: None for s in symbols} # 銘柄ごとのデータフィードを保持

    @abc.abstractmethod
    def start(self):
        """
        データ取得を開始します。
        (例: WebSocketへの接続、ポーリングスレッドの開始など)
        """
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self):
        """データ取得を安全に停止します。"""
        raise NotImplementedError

    @abc.abstractmethod
    def get_data_feed(self, symbol):
        """
        指定された銘柄のデータフィードオブジェクトを返します。
        まだ生成されていない場合は、ここで生成します。
        :param symbol: 銘柄コード
        :return: RealtimeDataFeed のインスタンス
        """
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_historical_data(self, symbol, timeframe, compression, period):
        """
        戦略のインジケーター計算に必要な過去のデータを取得します。
        :param symbol: 銘柄コード
        :param timeframe: 'days', 'minutes'など
        :param compression: 1, 5, 60など
        :param period: 取得する期間の長さ (例: 100本)
        :return: pandas.DataFrame
        """
        raise NotImplementedError