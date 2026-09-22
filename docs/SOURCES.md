# Sources and licenses

The harness is MIT licensed. Third-party strategy source files under cases/ and provenance/ retain their upstream licenses. Each provenance/<case>/LICENSE is the license retrieved at the historical source version; copying a strategy to cases/<case>/strategy.py does not change that license.

Native frameworks are separately installed from locked dependencies: [Backtrader](https://github.com/mementum/backtrader), [backtesting.py](https://github.com/kernc/backtesting.py), [vn.py CTA](https://github.com/vnpy/vnpy_ctastrategy), [RQAlpha](https://github.com/ricequant/rqalpha) and [Freqtrade](https://github.com/freqtrade/freqtrade). Their licenses are not replaced by the harness license.

Original strategy versions and source hashes are listed in [sources.json](../sources.json). Freqtrade historical strategies come from [freqtrade-strategies](https://github.com/freqtrade/freqtrade-strategies); the legacy ADX API is translated by an explicitly separate bridge that preserves original calculations.

Market fixtures are normalized Binance public OHLCV archives: [format and checksums](https://github.com/binance/binance-public-data). vn.py uses ETHUSDT USD-M one-minute candles on 2024-01-01 and 2024-01-02 with preceding-day warmup. ADX uses ETHUSDT spot hourly candles from 2024 Q1, followed by 2024 Q2. Strategy004 uses BTCUSDT spot five-minute candles for January and February 2024. All times are UTC. Raw archive checksums were verified during acquisition; fixture identities are recorded in the baseline manifest.


The expanded corpus also uses the upstream [GOOG daily dataset](https://github.com/kernc/backtesting.py/blob/ca2e2611621e472542ba90f7243a1fa06a7d7108/backtesting/test/GOOG.csv) and public Sina daily 000001 stock observations. GOOG is split chronologically at row 1,600; the stock data uses 2024 H1/H2 with earlier warmup. WTC's February 30m holdout is aggregated from verified Binance 5m bars. See [the full corpus](TWENTY_STRATEGIES.md) and [market acquisition identities](../evaluation/market-sources.json). The Sina endpoint is a moving history window; the checked-in, hashed fixture is the reproducible input, not a promise that a future request returns identical rows.
