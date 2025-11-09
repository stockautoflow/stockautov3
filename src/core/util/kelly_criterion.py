# src/core/util/kelly_criterion.py (新規追加)
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def calculate_raw_kelly(win_rate_percent, rr_ratio):
    """
    勝率(%)とRR比から生のケリーf値を計算する。
    基本仕様書 v2.1 (1.3.1) に準拠。

    Args:
        win_rate_percent (str or float): "55.20%" や 55.20 など
        rr_ratio (str or float): "2.15", "inf", np.inf など

    Returns:
        float: 計算されたケリーf値 (期待値がマイナスなら負の値を返す)
                無効な入力の場合は np.nan を返す。
    """
    try:
        # 1. 勝率(p)のクリーニング (例: "55.20%" -> 0.5520)
        p_str = str(win_rate_percent).replace('%', '')
        p = pd.to_numeric(p_str, errors='coerce') / 100.0

        # 2. RR比(R)のクリーニング (例: "inf" -> np.inf)
        r_str = str(rr_ratio).lower().replace('inf', 'inf')
        R = pd.to_numeric(r_str, errors='coerce')
        if r_str == 'inf':
            R = np.inf

        # 3. 入力値のバリデーション (仕様 1.3.1 - 処理2)
        if pd.isna(p) or pd.isna(R) or not (0 <= p <= 1) or R <= 0:
            return np.nan

        # 4. エッジケース処理 (Rが無限大) (仕様 1.3.1 - 処理3)
        if R == np.inf:
            return p  # f_value = p

        # 5. 通常処理 (仕様 1.3.1 - 処理4)
        # f* = (p*R - (1-p)) / R
        f_value = (p * R - (1 - p)) / R
        return f_value

    except Exception as e:
        logger.error(f"ケリー基準の計算エラー: p={win_rate_percent}, R={rr_ratio}, Error: {e}")
        return np.nan