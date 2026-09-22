# Acceptance fixes after the public baseline

The public baseline is commit `73fcd86e1724965d104f01afbba4b46d70cb3529`. Its source manifest remains an historical record, not a current-tree integrity manifest.

The following checks now have executable regressions:

- Repaired submissions require a real source change, evidence for that exact source, successful native execution and passing financial, contract, causality and preservation checks.
- Unchanged no-violation submissions require the same measured checks. Missing specifications and infrastructure blocks are not successful repairs.
- Prefix indicators and signals are compared through the cutoff candle. Only explicitly recorded forced terminal fills and their orders receive terminal-event handling.
- Required native account fields and actual Freqtrade exit configuration are checked against the public contract.
- Class/module parameters, inheritance, imports, trading comparisons and methods outside declared repair scopes are protected by AST comparison.
- Completed results are reused only when source, fixtures, specification, runtime, policy and checker identities match. Modified submitted files invalidate cached evidence.
- Intraday capability descriptions and release-availability timestamps use the actual configured bar clock.

Run `python -m pytest -q -p no:cacheprovider`. These checks are local harness regressions; they are separate from the upcoming 20 real-strategy native executions and are not counted as additional strategy or model episodes.

Remaining architecture work unifies orchestration, makes content-addressed executions automatic, adds transactional resume and controlled experiment selection, and strengthens coverage and evidence validation.
