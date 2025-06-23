# 取引戦略ガイド

## はじめに

このドキュメントは、長期(long)、中期(medium)、短期(short)の3つの時間軸をすべて利用し、様々な市場の状況に対応するための30パターンのエントリー戦略アイデア集です。

### 3つの時間軸

- **長期 (long):** 相場の大きな方向性（トレンドの有無、方向）を定義します。
- **中期 (medium):** 長期トレンド内での調整（押し目・戻り）や、レンジ相場での反転ポイントを捉えます。
- **短期 (short):** 具体的なエントリーの引き金（トリガー）となります。

> これらの設定例をベースに、パラメータを最適化してご自身の戦略を構築してください。

---

## カテゴリー1: トレンドフォロー戦略 (Trend Following)

大きなトレンドに乗り、順張りで利益を狙う最も基本的な戦略群です。

### 1. SMA + RSI + EMAクロス (基本形)

**ロジック概要:** 長期SMAで上昇トレンドを確認し、中期RSIで押し目を測り、短期EMAのゴールデンクロスでエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 75}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 50}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 75}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 50}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
### 2. EMA + MACD + Stochastic

**ロジック概要:** 長期EMAでトレンド方向を定義。中期のMACDが0以上（上昇トレンド）で、短期Stochasticが売られすぎ圏からの反発を狙う。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 100}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '>', 'target': {'type': 'values', 'value': 0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 30}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 100}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '<', 'target': {'type': 'values', 'value': 0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 70}}`
### 3. ADX + Bollinger Bands + RSI

**ロジック概要:** 長期ADXでトレンドの強さを確認。中期で価格がボリンジャーバンドのミドルバンド（SMA）より上で推移し、短期RSIの押し目でエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'BollingerBands', 'params': {'period': 20, 'devfactor': 2.0}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 40}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'BollingerBands', 'params': {'period': 20, 'devfactor': 2.0}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 60}}`
### 4. Ichimoku(Proxy) + VWAP + EMAクロス

**ロジック概要:** 長期EMAを雲と見なしトレンドを判断。中期VWAPで当日の勢いを測り、短期EMAクロスでエントリー。日中取引向け。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 200}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '>', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 5}}, 'indicator2': {'name': 'ema', 'params': {'period': 20}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 200}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '<', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 5}}, 'indicator2': {'name': 'ema', 'params': {'period': 20}}}`
### 5. SMAデュアル + MACD + EMA

**ロジック概要:** 2本の長期SMAで強いトレンドを定義。中期MACDでトレンドの継続を確認し、短期で価格がEMAを上抜いたらエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 50}}, 'compare': '<', 'target': {'type': 'indicator', 'indicator': {'name': 'sma', 'params': {'period': 150}}}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '>', 'target': {'type': 'values', 'value': 0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'ema', 'params': {'period': 10}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 50}}, 'compare': '>', 'target': {'type': 'indicator', 'indicator': {'name': 'sma', 'params': {'period': 150}}}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '<', 'target': {'type': 'values', 'value': 0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'ema', 'params': {'period': 10}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
### 6. EMA + ADX + MACD

**ロジック概要:** 長期EMAでトレンド方向を、中期ADXでその強さを確認。短期MACDのゼロライン越えをエントリーシグナルとする。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 100}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '>', 'target': {'type': 'values', 'value': 0}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 100}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '<', 'target': {'type': 'values', 'value': 0}}`
### 7. SMA + Stochastic + EMAクロス

**ロジック概要:** 長期SMAでトレンドを確認後、中期Stochasticで売られすぎの押し目を待ち、短期EMAクロスでトレンドへの再復帰を捉える。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 75}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 20, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 30}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 75}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 20, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 70}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
### 8. ADX + RSI + VWAP

**ロジック概要:** 長期ADXでトレンド相場であることを確認。中期RSIで押し目を測り、短期で価格がVWAPを上抜くことで当日の勢いを確信する。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 50}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '>', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 50}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '<', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
### 9. Ichimoku(Proxy) + Bollinger + EMAクロス

**ロジック概要:** 長期EMAを雲の代わりとして長期トレンドを確認。中期で価格がBBミドルバンドより上にあり、短期EMAクロスでエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 200}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'BollingerBands', 'params': {'period': 20, 'devfactor': 2.0}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 9}}, 'indicator2': {'name': 'ema', 'params': {'period': 26}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 200}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'BollingerBands', 'params': {'period': 20, 'devfactor': 2.0}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 9}}, 'indicator2': {'name': 'ema', 'params': {'period': 26}}}`
### 10. EMA + MACD + RSI

**ロジック概要:** 長期EMAでトレンドを、中期MACDで勢いを判断。短期RSIが売られ過ぎゾーンからの回復を見せた時にエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 100}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '>', 'target': {'type': 'values', 'value': 0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 40}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 100}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '<', 'target': {'type': 'values', 'value': 0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 60}}`
---

## カテゴリー2: 平均回帰戦略 (Mean Reversion)

相場の「行き過ぎ」からの反転を狙う逆張り戦略です。

### 11. ADX(低) + Bollinger Bands + RSI

**ロジック概要:** 長期ADXでレンジ相場を確認。中期でボリンジャーバンド±2σにタッチし、短期RSIが行き過ぎを示す。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'BollingerBands', 'params': {'period': 20, 'devfactor': 2.0}}, 'compare': '>', 'target': {'type': 'data', 'value': 'low'}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'BollingerBands', 'params': {'period': 20, 'devfactor': 2.0}}, 'compare': '<', 'target': {'type': 'data', 'value': 'high'}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 80}}`
### 12. 長期Bollinger + 中期Stochastic + 短期RSI

**ロジック概要:** 長期ボリンジャーバンドで大きな反転ゾーンを特定。中期Stochastic、短期RSIで二重の行き過ぎを確認。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'BollingerBands', 'params': {'period': 50, 'devfactor': 2.5}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 7}}, 'compare': '<', 'target': {'type': 'values', 'value': 30}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'BollingerBands', 'params': {'period': 50, 'devfactor': 2.5}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 80}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 7}}, 'compare': '>', 'target': {'type': 'values', 'value': 70}}`
### 13. RSI + RSI + RSI

**ロジック概要:** 全時間足でRSIの売られすぎ/買われすぎを確認し、非常に強い反転の可能性を捉える。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 40}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 30}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 60}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 70}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 80}}`
### 14. Stochastic + Stochastic + EMAクロス

**ロジック概要:** 長期・中期Stochasticで相場の過熱感を確認し、短期EMAの逆方向クロスで反転エントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'stochastic', 'params': {'period': 20, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 5}}, 'indicator2': {'name': 'ema', 'params': {'period': 10}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'stochastic', 'params': {'period': 20, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 80}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 80}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 5}}, 'indicator2': {'name': 'ema', 'params': {'period': 10}}}`
### 15. ADX(低) + VWAP + Stochastic

**ロジック概要:** 長期的なレンジ相場の中、当日の価格がVWAPから大きく乖離し、短期Stochasticが行き過ぎを示した時に逆張り。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '<', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '>', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 80}}`
---

## カテゴリー3: ボラティリティブレイクアウト戦略 (Volatility Breakout)

静かな相場から動き出す瞬間を捉える戦略です。

### 16. ATR(低) + ATR(低) + EMAクロス

**ロジック概要:** 長期・中期でボラティリティの低下（ATRの低水準）を確認。短期のクロスで動き出しを捉える。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 10.0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 5.0}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 5}}, 'indicator2': {'name': 'ema', 'params': {'period': 20}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 10.0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 5.0}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 5}}, 'indicator2': {'name': 'ema', 'params': {'period': 20}}}`
### 17. ATR(低) + SMA + Price Break

**ロジック概要:** 中期ATRで相場の収縮を確認。長期SMAでブレイク方向を予測し、短期価格が高速EMAを上抜くことでエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 50}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'atr', 'params': {'period': 20}}, 'compare': '<', 'target': {'type': 'values', 'value': 7.0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'ema', 'params': {'period': 10}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 50}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'atr', 'params': {'period': 20}}, 'compare': '<', 'target': {'type': 'values', 'value': 7.0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'ema', 'params': {'period': 10}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
### 18. ADX(低) + ADX(低) + MACDゼロクロス

**ロジック概要:** 長期・中期でADXが低水準にあり、エネルギーを溜めている状態を確認。短期MACDのゼロクロスをブレイクのサインとする。

!!! warning "注意: この戦略は現在サポートされていません"
    理由: 固定値とのクロスオーバーは未サポートです。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'indicator2': {'name': 'values', 'value': 0}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'indicator2': {'name': 'values', 'value': 0}}`
### 19. ATR(高) + ATR(高) + EMAクロス

**ロジック概要:** 逆に、すでにボラティリティが高い相場での順張り戦略。長期・中期共にATRが高いことを確認し、短期の押し目からの再上昇を狙う。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 20.0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 10.0}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 20.0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 10.0}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
### 20. Ichimoku(Proxy)収縮 + ADX + EMAクロス

**ロジック概要:** 長期ATRの低下を雲の収縮と見なし、中期ADXの上昇でブレイクの予兆を捉え、短期EMAクロスでエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'atr', 'params': {'period': 50}}, 'compare': '<', 'target': {'type': 'values', 'value': 15.0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 9}}, 'indicator2': {'name': 'ema', 'params': {'period': 26}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'atr', 'params': {'period': 50}}, 'compare': '<', 'target': {'type': 'values', 'value': 15.0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 9}}, 'indicator2': {'name': 'ema', 'params': {'period': 26}}}`
---

## カテゴリー4: 複合戦略 (Hybrid Strategies)

異なるタイプのロジックを組み合わせた高度な戦略です。

### 21. トレンド + ボラティリティフィルター

**ロジック概要:** 基本のトレンドフォロー戦略に、長期ATRフィルターを追加。市場が動いている時のみエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 75}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 15.0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 50}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 75}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 15.0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 50}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
### 22. トレンド内カウンタートレード

**ロジック概要:** 長期トレンド（SMA）を確認し、中期のStochasticで行き過ぎの反動を狙い、短期RSIでエントリー。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 100}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 20, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 50}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 100}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 20, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 80}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 50}}`
### 23. ADX(トレンド) + ADX(レンジ) + EMAクロス

**ロジック概要:** 長期でトレンドがある(高ADX)中で、中期で調整局面(低ADX)に入った後の、短期EMAクロスによる再ブレイクを狙う。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 20}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
### 24. VWAP + SMA + RSI

**ロジック概要:** 長期SMAで大局観を、中期VWAPで当日の勢いを判断。短期RSIで精密な押し目買いのタイミングを計る。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 50}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '<', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 40}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 50}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '>', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 60}}`
### 25. MACD + Stochastic + RSI

**ロジック概要:** 3つのオシレーターを各時間足で役割分担。長期MACDで大きな流れ、中期Stochasticで押し目、短期RSIでエントリー。

!!! warning "注意: この戦略は現在サポートされていません"
    理由: 固定値とのクロスオーバーは未サポートです。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '>', 'target': {'type': 'values', 'value': 0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 30}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'rsi', 'params': {'period': 7}}, 'indicator2': {'name': 'values', 'value': 30}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '<', 'target': {'type': 'values', 'value': 0}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 70}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'rsi', 'params': {'period': 7}}, 'indicator2': {'name': 'values', 'value': 70}}`
### 26. Bollinger + EMA + MACD

**ロジック概要:** 長期BBミドルバンドでトレンド方向を、中期EMAでサポートを確認。短期MACDのゼロクロスでエントリー。

!!! warning "注意: この戦略は現在サポートされていません"
    理由: 固定値とのクロスオーバーは未サポートです。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'bollingerbands', 'params': {'period': 50, 'devfactor': 2.0}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 50}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'indicator2': {'name': 'values', 'value': 0}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'bollingerbands', 'params': {'period': 50, 'devfactor': 2.0}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 50}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'indicator2': {'name': 'values', 'value': 0}}`
### 27. SMA + VWAP + VWAP

**ロジック概要:** 長期SMAで大きなトレンド方向を決定。中期・短期ともに価格がVWAPより上にあることを確認し、強い買い（売り）圧力が継続している局面を狙う。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 100}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '<', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '<', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'sma', 'params': {'period': 100}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '>', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'ema', 'params': {'period': 1}}, 'compare': '>', 'target': {'type': 'indicator', 'indicator': {'name': 'vwap', 'params': {}}}}`
### 28. RSI + ADX + EMAクロス

**ロジック概要:** 長期RSIで過熱感をフィルタリング（買われすぎでない）。中期ADXでトレンドの強さを確認し、短期EMAクロスで順張り。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '<', 'target': {'type': 'values', 'value': 70}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossover', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'rsi', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 30}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 25}}`
    - **Short:** `{'timeframe': 'short', 'type': 'crossunder', 'indicator1': {'name': 'ema', 'params': {'period': 10}}, 'indicator2': {'name': 'ema', 'params': {'period': 25}}}`
### 29. Ichimoku(Proxy) + ATR + Stochastic

**ロジック概要:** 長期EMAを雲と見なしてトレンドを定義。中期ATRでボラティリティがあることを確認し、短期Stochasticで押し目を狙う。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 200}}, 'compare': '<', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 10.0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 30}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'ema', 'params': {'period': 200}}, 'compare': '>', 'target': {'type': 'data', 'value': 'close'}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'atr', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 10.0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 70}}`
### 30. ADX + MACD + Stochastic

**ロジック概要:** 長期ADXでトレンドの有無を確認。中期MACDでその方向性を判断。短期Stochasticで押し目/戻りのタイミングを計る。

=== "ロングエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '>', 'target': {'type': 'values', 'value': 0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '<', 'target': {'type': 'values', 'value': 40}}`
=== "ショートエントリー条件"

    - **Long:** `{'timeframe': 'long', 'indicator': {'name': 'adx', 'params': {'period': 14}}, 'compare': '>', 'target': {'type': 'values', 'value': 20}}`
    - **Medium:** `{'timeframe': 'medium', 'indicator': {'name': 'macd', 'params': {'period_me1': 12, 'period_me2': 26, 'period_signal': 9}}, 'compare': '<', 'target': {'type': 'values', 'value': 0}}`
    - **Short:** `{'timeframe': 'short', 'indicator': {'name': 'stochastic', 'params': {'period': 14, 'period_dfast': 3, 'period_dslow': 3}}, 'compare': '>', 'target': {'type': 'values', 'value': 60}}`
---

