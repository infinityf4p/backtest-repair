# Backtest Repair

A native-engine harness for diagnosing and repairing structured trading strategies. It accepts Backtrader, backtesting.py, vn.py CTA, RQAlpha callback modules and Freqtrade strategies, preserving each framework's execution model.

**This initial public commit preserves the current implementation before the fixes described in [KNOWN_ISSUES](docs/KNOWN_ISSUES.md).** It is a research workflow, with explicit runtime and strategy-profile limits.

The repository contains the harness, dependency locks, isolated Linux Docker workers, and three published historical-defect cases. Each case preserves the original source, fixed commit provenance and its original license. They are historical bugs supported by merged upstream PRs, not claims about current upstream releases. Market fixtures are real Binance historical candles. Cases are not profitability recommendations.

## Install and inspect

```bash
python -m pip install -e '.[remote,dev]'
btr detect cases/vnpy_stale_orders
python -m pytest -q -p no:cacheprovider
```

For remote native replay, copy `runtime.example.json` to `runtime.remote.local.json` and provide your Linux Docker SSH configuration and verified known_hosts file. The password is read without echo; do not commit credentials. Model credentials are read locally from BTR_API_BASE/BTR_API_KEY or an explicit local Codex API-key provider.

```bash
python run_defects.py build --runtime runtime.remote.local.json
python run_defects.py baseline --runtime runtime.pinned.local.json
python run_defects.py agents --runtime runtime.pinned.local.json
python run_defects.py holdout --runtime runtime.pinned.local.json
```

The current external evaluator runs one bounded agent episode per strategy. It exposes only public strategy inputs and native evidence. Source and comments are treated as untrusted data. Upstream patches and held-out periods are not supplied to the agent. The initial submission checks have known omissions documented below; a test pass is not a general correctness claim.

## Historical cases

| Case | Framework | Source of historical fix |
|---|---|---|
| DoubleMaStrategy missing order cancellation | vn.py CTA | [PR 44](https://github.com/vnpy/vnpy_ctastrategy/pull/44) |
| ADXMomentum missing exit signal | Freqtrade | [PR 31](https://github.com/freqtrade/freqtrade-strategies/pull/31) |
| Strategy004 full-sample volume mean | Freqtrade | [PR 285](https://github.com/freqtrade/freqtrade-strategies/pull/285) |

See [sources.json](sources.json), [protocol.json](protocol.json), [licenses and data sources](docs/SOURCES.md), and [known issues](docs/KNOWN_ISSUES.md). Private runtime configurations, user paths, model credentials and previous machine-specific run artifacts are excluded from this repository.
