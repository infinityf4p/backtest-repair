# Twenty published strategies

Twenty distinct strategy sources; no injected strategy bug and no random-seed repetitions. The three historical bug versions and the published WTC bias example are identified openly. Other examples are not presumed correct or defective.

| ID | Engine | Published source | Visible bars | Later holdout bars | Adaptation |
|---|---|---|---:|---:|---|
| vnpy_stale_orders | vnpy_cta | [source](https://github.com/vnpy/vnpy_ctastrategy/blob/ac7be8fa955fcecff655ad7bc11c8b9a4789ea32/vnpy_ctastrategy/strategies/double_ma_strategy.py) | 1440 | 1440 | Original source; declared benchmark instrument/costs |
| adx_missing_exit | freqtrade | [source](https://github.com/freqtrade/freqtrade-strategies/blob/d3a76cae2886425865732796dba9860e7e15ffd3/user_data/strategies/berlinguyinca/ADXMomentum.py) | 2184 | 2184 | Original source; declared benchmark instrument/costs |
| volume_lookahead | freqtrade | [source](https://github.com/freqtrade/freqtrade-strategies/blob/424bddd28fcd01478af48ac2b4b21cbae5368b99/user_data/strategies/Strategy004.py) | 8928 | 8352 | Original source; declared benchmark instrument/costs |
| bt_stop | backtrader | [source](https://github.com/mementum/backtrader/blob/b853d7c90b6721476eb5a5ea3135224e33db1f14/samples/stop-trading/stop-loss-approaches.py) | 1600 | 548 | Original source; declared benchmark instrument/costs |
| bt_macd | backtrader | [source](https://github.com/mementum/backtrader/blob/b853d7c90b6721476eb5a5ea3135224e33db1f14/samples/macd-settings/macd-settings.py) | 1600 | 548 | Use upstream FixedPerc sizer at its published 20% default; benchmark market and declared fees differ from sample CLI defaults. |
| bt_signal_sma | backtrader | [source](https://github.com/mementum/backtrader/blob/b853d7c90b6721476eb5a5ea3135224e33db1f14/samples/sigsmacross/sigsmacross.py) | 1600 | 548 | Original source; declared benchmark instrument/costs |
| btpy_sma | backtesting_py | [source](https://github.com/kernc/backtesting.py/blob/ca2e2611621e472542ba90f7243a1fa06a7d7108/doc/examples/Quick%20Start%20User%20Guide.py) | 1600 | 548 | Extract original imports/functions/classes by AST; omit tutorial run/optimization/plot cells; all retained ASTs identical. |
| btpy_multitimeframe | backtesting_py | [source](https://github.com/kernc/backtesting.py/blob/ca2e2611621e472542ba90f7243a1fa06a7d7108/doc/examples/Multiple%20Time%20Frames.py) | 1600 | 548 | Extract original imports/functions/classes by AST; omit tutorial run/optimization/plot cells; all retained ASTs identical. |
| btpy_trailing | backtesting_py | [source](https://github.com/kernc/backtesting.py/blob/ca2e2611621e472542ba90f7243a1fa06a7d7108/doc/examples/Strategies%20Library.py) | 1600 | 548 | Extract original imports/functions/classes by AST; omit tutorial run/optimization/plot cells; all retained ASTs identical. |
| vnpy_atr_rsi | vnpy_cta | [source](https://github.com/vnpy/vnpy_ctastrategy/blob/6ef76981624bf55b2ea978f8587f74d633aafc72/vnpy_ctastrategy/strategies/atr_rsi_strategy.py) | 1440 | 1440 | Original source; declared benchmark instrument/costs |
| vnpy_boll | vnpy_cta | [source](https://github.com/vnpy/vnpy_ctastrategy/blob/6ef76981624bf55b2ea978f8587f74d633aafc72/vnpy_ctastrategy/strategies/boll_channel_strategy.py) | 1440 | 1440 | Original source; declared benchmark instrument/costs |
| vnpy_dual_thrust | vnpy_cta | [source](https://github.com/vnpy/vnpy_ctastrategy/blob/6ef76981624bf55b2ea978f8587f74d633aafc72/vnpy_ctastrategy/strategies/dual_thrust_strategy.py) | 1440 | 1440 | Original source; declared benchmark instrument/costs |
| vnpy_keltner | vnpy_cta | [source](https://github.com/vnpy/vnpy_ctastrategy/blob/6ef76981624bf55b2ea978f8587f74d633aafc72/vnpy_ctastrategy/strategies/king_keltner_strategy.py) | 1440 | 1440 | Original source; declared benchmark instrument/costs |
| rq_golden_cross | rqalpha | [source](https://github.com/ricequant/rqalpha/blob/a5fb4e43879c381e61131399dcc094d495c7080a/rqalpha/examples/golden_cross.py) | 117 | 125 | Original source; declared benchmark instrument/costs |
| rq_macd | rqalpha | [source](https://github.com/ricequant/rqalpha/blob/a5fb4e43879c381e61131399dcc094d495c7080a/rqalpha/examples/macd.py) | 117 | 125 | Original source; declared benchmark instrument/costs |
| rq_buy_hold | rqalpha | [source](https://github.com/ricequant/rqalpha/blob/a5fb4e43879c381e61131399dcc094d495c7080a/rqalpha/examples/buy_and_hold.py) | 117 | 125 | Original source; declared benchmark instrument/costs |
| ft_wtc | freqtrade | [source](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/lookahead_bias/wtc.py) | 1488 | 1392 | Original source; declared benchmark instrument/costs |
| ft_ema_ha | freqtrade | [source](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/Strategy001.py) | 8928 | 8352 | Original source; declared benchmark instrument/costs |
| ft_fisher_hammer | freqtrade | [source](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/Strategy002.py) | 8928 | 8352 | Original source; declared benchmark instrument/costs |
| ft_bband_rsi | freqtrade | [source](https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/berlinguyinca/BbandRsi.py) | 2184 | 2184 | Original source; declared benchmark instrument/costs |

Hashes, upstream commits and licenses are in [sources.json](../sources.json), [input manifest](../evaluation/inputs.json), and each `provenance/<id>/LICENSE`. Fixed reference versions are evaluator-only provenance, never agent input.

## Data

- Backtrader / backtesting.py: the published backtesting.py GOOG dataset, first 1,600 rows visible and remaining 548 rows held out. No tutorial optimization is executed.
- vn.py: Binance ETHUSDT USD-M minute bars, 2024-01-01 visible and 2024-01-02 held out, with preceding-day initialization bars. The Bollinger strategy naturally needs several additional visible bars to finish its 15-minute window warmup.
- RQAlpha: Sina daily 000001.XSHE, 2024 H1 visible and H2 held out, each with 150 earlier warmup observations. These are OHLCV fixtures under the declared simplified exchange metadata.
- Freqtrade 5m: Binance BTCUSDT spot January 2024 visible, February held out.
- Freqtrade 1h: Binance ETHUSDT spot 2024 Q1 visible, Q2 held out.
- WTC: Binance BTCUSDT spot 30m January 2024 visible; holdout February aggregated deterministically from six consecutive 5m bars (first open, maximum high, minimum low, last close, sum volume).

All later intervals were frozen before model calls. Future perturbations preserve the visible prefix and transform only future bars; these are diagnostic data, not new real-market observations.

The selected source paths and interfaces are not evidence that these examples were deployed with real capital. This is a deliberately mixed, nonrandom benchmark; its repair rate is not a population estimate.
