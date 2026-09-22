# Backtest Repair

面向结构化量化策略的诊断、反例实验与最小修复 workflow。策略继续由原生框架执行；LLM 提出假设、选择实验和修改代码，验收由宿主检查器决定。

支持 Backtrader、backtesting.py、vn.py CTA、RQAlpha 回调模块和 Freqtrade。这里的支持范围是明确的单标的回测 profile，不是这些框架全部功能的通用替代品。

## 工作流

1. 固定策略源码、规格、行情、原生依赖和运行镜像，计算内容身份。
2. 原生回放，检查真实订单/成交、费用与账户账本、公开交易约束及覆盖率。
3. 仅扰动截点之后的行情，对比截至截点的指标、信号、订单与成交；也可请求历史前缀实验。
4. Agent 在明确预算内提出假设、运行实验、提交最小补丁。
5. 校验提交的准确源码版本、参数/条件/无关方法保护，以及相对于原始运行的受保护指标。
6. 冻结提交，再运行严格晚于可见区间的数据。独立验证结果不反馈给该 agent。

CLI、单策略修复和批量评测使用同一个核心。结果按内容保存；原生执行有缓存；模型响应和补丁有事务记录。请求已发出但响应丢失时记录用量未知，禁止静默重新付费。

## 使用

```bash
python -m pip install -e '.[remote,dev]'
python -m pytest -q -p no:cacheprovider
btr detect cases/bt_signal_sma
btr inspect cases/vnpy_stale_orders
```

复制 `runtime.example.json` 为 `runtime.remote.local.json`，填入已有 Linux Docker 主机及已验证的 known_hosts 路径。SSH 密码通过隐藏输入读取。构建使用锁定依赖；构建后记录镜像 SHA，运行配置使用 SHA 固定实际镜像。

```bash
python run_defects.py build --runtime runtime.remote.local.json
btr run cases/bt_stop --runtime runtime.pinned.local.json --mode ssh_docker --output results/audit
btr repair cases/vnpy_stale_orders --runtime runtime.pinned.local.json --mode ssh_docker --output results/single
btr suite . --runtime runtime.pinned.local.json --mode ssh_docker --output results/twenty --jobs 2
btr report results/twenty
```

模型使用 Responses 流式协议，从 `BTR_API_BASE` / `BTR_API_KEY` 或本机明确配置的 API-key provider 读取认证。密钥留在宿主内存，不能进入候选代码容器、模型消息或仓库。默认预算和模型配置见 [protocol.json](protocol.json)。单策略可以通过 `--model`、`--effort`、`--limits` 覆盖；本次评测使用预先冻结的协议。

对同一输出目录重复执行会复用已完成结果，或恢复已有响应及工具动作。已发出且缺少响应的模型调用会停止并保留未知用量。修改源码、规格、数据、检查器或镜像会产生新执行身份；旧结果不覆盖。

## 20 个网上真实策略

[策略清单](docs/TWENTY_STRATEGIES.md)包含 Backtrader 3 个、backtesting.py 3 个、vn.py 5 个、RQAlpha 3 个、Freqtrade 6 个。每个策略保留原始公开版本、文件哈希、许可证、适配说明及独立后续行情。三例为有上游修复记录的历史缺陷，WTC 为上游公开的已知前视偏差示例，其余为公开策略示例。没有向策略注入人工错误，每例只进行一次 agent 流程。

必要的原生预检、修复复测、诊断实验和独立验证分别计数。没有成交、关键退出条件未触发、适配失败和模型调用失败不会混成通过。历史已知缺陷的修复不等于发现当前版本的新漏洞，也不能用于估算所有策略的错误率。

## 实测结果

20 个策略各进行一次 agent 流程：**4 个修复通过、12 个未发现违规、3 个因覆盖不足保留结论、1 个模型请求超时**。独立后续行情为 17 个通过、3 个覆盖不足。正式的 106 次原生执行均成功；预检和必要的修复复测单独记录，没有随机种子重复。

完整本地测试 40 项通过；追加探针的验收门槛补强后，使用已保存记录复核了全部 20 例，接受判定一致。模型请求共 45 次，其中一次最终用量未知，没有自动付费重试。

[逐例结果与限制](evaluation/REPORT.md) · [可视报告](evaluation/report.html) · [机器可读汇总](evaluation/summary.json) · [完整证据下载](https://github.com/infinityf4p/backtest-repair/releases/tag/v0.4.0)

## 约束与证据

- 支持明确的框架版本、单标的行情、费用和执行规则；多资产、tick、实盘、强平/资金费、公司行动等不在本次支持范围。
- 普通示例的检查主要验证原生执行一致性、账本与因果性；明确的订单寿命/信号条件/滚动窗口另有规格检查。没有公开业务规格时，不会凭回测利润猜测正确交易逻辑。
- 参数、继承、无关方法和比较条件默认不可修改；缺陷指标只在公开允许范围内更改。
- 隔离保护宿主，但原生观测器与策略共用 Python 进程；不宣称可以证明恶意代码没有篡改观测器。
- 有限历史测试不是普遍正确性、实盘安全性或盈利能力证明。

架构与边界：[ARCHITECTURE.md](docs/ARCHITECTURE.md)。问题修复记录：[FIXES.md](docs/FIXES.md)。数据和许可证：[SOURCES.md](docs/SOURCES.md)。冻结输入：[evaluation/inputs.json](evaluation/inputs.json)。

初始公开起点为 `73fcd86`；保留它用于对照修复前行为。MIT 许可证只适用于本仓库原创 harness；第三方策略和框架保持各自上游许可证。
