# 20 个真实策略：评测结果

源码版本：`a118253d9335628169e824b78b6d5ab206507a3c`。20 个不同的网上公开策略，每例一次 agent 流程，没有随机种子重复。

可见验收：{'repaired': 4, 'observed_no_violation': 12, 'inconclusive': 3, 'model_usage_unknown': 1}。独立后续行情：{'pass': 17, 'inconclusive': 3}。

模型请求 45 次，收到完整记录 44 次，已知用量 340,828 tokens；中转未提供金额计费，费用不估算。正式原生运行 106 次，状态 {'ok': 106}。另保留原生预检 52 次，未额外运行 agent。

| 策略 | 框架 | 原始成交数 | Agent 验收 | 后续行情 | 补丁 |
|---|---|---:|---|---|---|
| [vnpy_stale_orders](cases/vnpy_stale_orders/result.json) | vnpy_cta | 151 | 已修复 | 通过 | [查看](cases/vnpy_stale_orders/patch.diff) |
| [adx_missing_exit](cases/adx_missing_exit/result.json) | freqtrade | 48 | 已修复 | 覆盖不足 | [查看](cases/adx_missing_exit/patch.diff) |
| [volume_lookahead](cases/volume_lookahead/result.json) | freqtrade | 14 | 已修复 | 通过 | [查看](cases/volume_lookahead/patch.diff) |
| [bt_stop](cases/bt_stop/result.json) | backtrader | 17 | 未发现违规 | 通过 | 无修改 |
| [bt_macd](cases/bt_macd/result.json) | backtrader | 47 | 未发现违规 | 通过 | 无修改 |
| [bt_signal_sma](cases/bt_signal_sma/result.json) | backtrader | 69 | 未发现违规 | 通过 | 无修改 |
| [btpy_sma](cases/btpy_sma/result.json) | backtesting_py | 139 | 未发现违规 | 通过 | 无修改 |
| [btpy_multitimeframe](cases/btpy_multitimeframe/result.json) | backtesting_py | 8 | 未发现违规 | 覆盖不足 | 无修改 |
| [btpy_trailing](cases/btpy_trailing/result.json) | backtesting_py | 57 | 未发现违规 | 通过 | 无修改 |
| [vnpy_atr_rsi](cases/vnpy_atr_rsi/result.json) | vnpy_cta | 11 | 未发现违规 | 通过 | 无修改 |
| [vnpy_boll](cases/vnpy_boll/result.json) | vnpy_cta | 1 | 覆盖不足 | 通过 | 无修改 |
| [vnpy_dual_thrust](cases/vnpy_dual_thrust/result.json) | vnpy_cta | 0 | 覆盖不足 | 覆盖不足 | 无修改 |
| [vnpy_keltner](cases/vnpy_keltner/result.json) | vnpy_cta | 9 | 未发现违规 | 通过 | 无修改 |
| [rq_golden_cross](cases/rq_golden_cross/result.json) | rqalpha | 1 | 覆盖不足 | 通过 | 无修改 |
| [rq_macd](cases/rq_macd/result.json) | rqalpha | 2 | 未发现违规 | 通过 | 无修改 |
| [rq_buy_hold](cases/rq_buy_hold/result.json) | rqalpha | 1 | 未发现违规 | 通过 | 无修改 |
| [ft_wtc](cases/ft_wtc/result.json) | freqtrade | 8 | 已修复 | 通过 | [查看](cases/ft_wtc/patch.diff) |
| [ft_ema_ha](cases/ft_ema_ha/result.json) | freqtrade | 38 | 未发现违规 | 通过 | 无修改 |
| [ft_fisher_hammer](cases/ft_fisher_hammer/result.json) | freqtrade | 2 | model_usage_unknown | 通过 | 无修改 |
| [ft_bband_rsi](cases/ft_bband_rsi/result.json) | freqtrade | 14 | 未发现违规 | 通过 | 无修改 |

## 解读

- 已修复仅表示该候选通过准确源码版本对应的公开检查；不等同于完整策略正确性证明。
- 三个历史缺陷来自上游 PR；WTC 是公开的已知前视偏差示例，没有向这些策略注入错误。其余为公开框架示例，不代表真实资金部署记录。
- 后续行情严格晚于可见区间，结果没有反馈给 agent。未触发退出条件、未成交或缺少足够观测都会保留为覆盖不足。
- 预检中发现过量价格扰动使正常 trailing stop 无效，以及 RQAlpha 局部指标缺少观测。修正的是探针/观测层，原始策略不变，失败记录保留。
- 账户、费用、参数/方法/指标保护、因果性和公开业务约束分别检查。普通示例没有完整独立交易意图 oracle，不能把未发现违规解读为生产认证。
- [架构和剩余边界](../docs/ARCHITECTURE.md)、[来源清单](../docs/TWENTY_STRATEGIES.md)、[完整汇总 JSON](summary.json)。


## 最终复核

正式执行版本为 `a118253`。结束后补强了“追加探针必须纳入最终验收”的门槛：默认探针通过不能覆盖另一个失败、覆盖不足或旧候选的实验；代码改动后必须重新验证所有已请求的截点。新增 5 项回归测试，完整本地测试共 40 项通过。

用补强后的检查器离线重算了这 20 例的账本、公开规则、因果比较、代码/指标保护和 4 个追加实验，16 个已接受提交的判定全部保持一致。没有重新调用模型或原生引擎。完整结果见 [revalidation.json](revalidation.json)，可对解压后的证据运行 `python evaluation/revalidate.py --runs /path/to/results`。

三例保留结论分别为：vn.py DualThrust 没有成交；vn.py BollChannel 和 RQAlpha GoldenCross 在可见期间各只有一次成交，agent 因未覆盖退出而保守拒绝下完整结论。后两例的最低数值覆盖检查虽通过，最终仍未被接受。后续行情的三例覆盖不足分别为 ADX 无退出条件触发、多周期 RSI 无成交、DualThrust 无成交。

Strategy002/Fisher-Hammer 的原生检查和后续行情检查通过，但第 4 次模型请求超时，没有取得最终提交和完整用量。该例记为 `model_usage_unknown`，不计成功，也没有自动重发请求。总计 45 次请求、44 份完整响应、340,828 个已知 tokens；缺失请求的实际用量和总费用未知。

[下载完整证据包](https://github.com/infinityf4p/backtest-repair/releases/tag/v0.4.0)，文件身份见 [evidence-bundle.json](evidence-bundle.json)。其中保留原始模型请求/响应、补丁、原生结果和确切公开输入；私有运行配置与认证信息不包含在内。
