import unittest
from unittest.mock import Mock, MagicMock, patch

# --- テスト対象のモジュールを動的にインポート ---
with patch.dict('sys.modules', {'xlwings': Mock()}):
    from src.realtrade.bridge.excel_reader import ExcelReader

class TestExcelReader(unittest.TestCase):
    """
    ExcelReaderクラスの単体テスト。
    xlwingsをモック化し、Excelに依存せずにロジックを検証する。
    """

    def setUp(self):
        """各テストの前にモックオブジェクトを準備する"""
        self.mock_sheets = MagicMock()
        self.mock_data_sheet = Mock()
        self.mock_position_sheet = Mock()

        self.mock_sheets.__getitem__.side_effect = lambda key: {
            'リアルタイムデータ': self.mock_data_sheet,
            'position': self.mock_position_sheet
        }[key]

    def test_read_market_data_successfully(self):
        """市場データの読み取りと解析が正常に行われることをテスト"""
        # Arrange: xlwingsが返すダミーデータを定義
        dummy_market_data = [
            [1332.0, 2500.5, 2490.0, 2510.0, 2485.0, 100000.0],
            [1605.0, 3000.0, 3010.0, 3020.0, 2990.0, 250000.0],
            [None, None, None, None, None, None]
        ]
        dummy_cash = 5000000.0
        
        # ▼▼▼ ここからが修正箇所 ▼▼▼
        # 呼び出される引数に応じて異なる値を返すside_effect関数を定義
        def range_side_effect(arg):
            mock_range = Mock()
            if arg == 'A2:F10':
                mock_range.value = dummy_market_data
            elif arg == 'B11':
                mock_range.value = dummy_cash
            else:
                # 想定外の引数で呼び出された場合
                mock_range.value = None
            return mock_range

        # self.mock_data_sheet.range の挙動をside_effectで設定
        self.mock_data_sheet.range.side_effect = range_side_effect
        # ▲▲▲ ここまでが修正箇所 ▲▲▲

        # Act: テスト対象のメソッドを実行
        reader = ExcelReader(self.mock_sheets)
        result = reader.read_market_data()

        # Assert: 結果が期待通りであることを検証
        expected = {
            '1332': {'close': 2500.5, 'open': 2490.0, 'high': 2510.0, 'low': 2485.0, 'volume': 100000.0},
            '1605': {'close': 3000.0, 'open': 3010.0, 'high': 3020.0, 'low': 2990.0, 'volume': 250000.0},
            'account': {'cash': 5000000.0}
        }
        self.assertEqual(result, expected)

    def test_read_positions_successfully(self):
        """建玉情報の読み取りと解析が正常に行われることをテスト"""
        # Arrange
        dummy_position_data = [
            [7203.0, None, None, None, None, None, '買建', 1000.0, None, 2800.0],
            [9984.0, None, None, None, None, None, '売建', 500.0,  None, 8500.0],
            ['--------', None, None, None, None, None, None, None, None, None]
        ]
        self.mock_position_sheet.range.return_value.value = dummy_position_data

        # Act
        reader = ExcelReader(self.mock_sheets)
        result = reader.read_positions()

        # Assert
        expected = {
            '7203': {'size': 1000.0, 'price': 2800.0},
            '9984': {'size': -500.0, 'price': 8500.0}
        }
        self.assertEqual(result, expected)

    def test_read_positions_with_invalid_row(self):
        """建玉情報に不正な行が含まれていても、スキップして処理を継続することをテスト"""
        # Arrange
        dummy_position_data = [
            [7203.0, None, None, None, None, None, '買建', 1000.0, None, 2800.0],
            [9984.0, None, None, None, None, None, '売建', 'INVALID',  None, 8500.0],
            [1570.0, None, None, None, None, None, '買建', 200.0, None, 25000.0]
        ]
        self.mock_position_sheet.range.return_value.value = dummy_position_data

        # Act
        reader = ExcelReader(self.mock_sheets)
        result = reader.read_positions()

        # Assert
        expected = {
            '7203': {'size': 1000.0, 'price': 2800.0},
            '1570': {'size': 200.0, 'price': 25000.0}
        }
        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()