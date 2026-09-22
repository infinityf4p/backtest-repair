# Status of reviewed issues

The original public baseline is commit `73fcd86`. The following corrections apply to the current workflow:

| Reviewed issue | Current behavior |
|---|---|
| Unchanged code accepted as repaired / financial checks bypassed | Exact source identity and all mandatory checks enforced by the host |
| Final two bars omitted from prefix comparison | Compare through the cutoff; exclude only explicitly identified forced terminal trades |
| Exit configuration and intent insufficiently protected | Actual exit settings checked; AST protection plus original-run indicator comparison |
| Directory-only cache reuse | Hash public inputs, runtime, policy and complete checker code |
| Intraday capability reported as daily | Shared clock and declared frequency |
| Two inconsistent agent loops | One package workflow, thin compatibility facades |
| Interrupted episodes and uncertain model usage | Atomic receipts, action journal, process lock; no automatic paid retry after uncertain dispatch |
| Incomplete branch coverage treated as success | Explicit minimum coverage and public predicate coverage; inconclusive is not accepted |

Remaining boundaries are material: strategy and recorder share an interpreter; only selected observations are checked; profiles do not implement every native-framework feature; finite probes cannot prove absence of all lookahead; generic examples have no complete independent trading-intent oracle. See [architecture](ARCHITECTURE.md). These limits are not silently converted to passes.
