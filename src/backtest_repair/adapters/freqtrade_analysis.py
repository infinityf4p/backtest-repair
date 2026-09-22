"""Unmodified native lookahead-analysis with public offline OHLCV files."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from .common import entry
from .freqtrade import offline_environment


class QuietProgress:
    def add_task(self, *args, **kwargs):
        return 0

    def update(self, *args, **kwargs):
        pass


def run(spec, bars, rec):
    from freqtrade.optimize.analysis.lookahead import LookaheadAnalysis

    cls = entry(spec)
    config, exchange = offline_environment(spec, cls)
    pair = spec["clock"]["instrument"]
    first = datetime.fromisoformat(bars[0]["date"]).replace(tzinfo=timezone.utc)
    last = datetime.fromisoformat(bars[-1]["date"]).replace(
        tzinfo=timezone.utc
    ) + timedelta(days=1)
    config.update(
        pairs=[pair],
        minimum_trade_amount=1,
        targeted_trade_amount=20,
        timerange=first.strftime("%Y%m%d") + "-" + last.strftime("%Y%m%d"),
        backtest_cache="none",
        enable_protections=False,
    )
    rows = [
        [
            int(
                datetime.fromisoformat(b["date"])
                .replace(tzinfo=timezone.utc)
                .timestamp()
                * 1000
            ),
            *[b[k] for k in ("open", "high", "low", "close", "volume")],
        ]
        for b in bars
    ]
    (Path("fixtures") / (pair.replace("/", "_") + "-1d.json")).write_text(
        json.dumps(rows), encoding="utf-8"
    )
    analysis = LookaheadAnalysis(config, {"name": cls.__name__})
    analysis.exchange = exchange
    try:
        analysis.start(QuietProgress())
        result = vars(analysis.current_analysis).copy()
        result.update(
            failed_bias_check=analysis.failed_bias_check,
            status="inconclusive"
            if analysis.failed_bias_check
            else "bias_found"
            if result["has_bias"]
            else "no_bias_found",
            native_backtests=1 + 2 * result["total_signals"],
            source="freqtrade.optimize.analysis.lookahead.LookaheadAnalysis.start",
            limitation="Native analysis truncates the framework dataframe; it does not rewrite external candidate CSV reads.",
        )
        return result
    finally:
        exchange.close()
