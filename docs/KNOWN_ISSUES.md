# Known issues in the initial public baseline

These are confirmed limitations of the initial snapshot. The next commits will correct the acceptance gates before expanding the shared workflow and real-strategy evaluation.

1. Submission checks can accept an unchanged `repaired` diagnosis despite failing visible invariants. Unchanged `observed_no_violation` submissions omit financial validation.
2. The external prefix comparison drops the final two bars for every observation type, hiding one- or two-bar lookahead. Only explicitly identified terminal trade events should receive end-of-run handling.
3. Declared exit configuration and protected strategy semantics are not fully checked; signal predicates use candidate-supplied indicator values.
4. Existing results are reused by directory existence, without validating source, data, specification, runtime and checker identities.
5. The capability descriptor reports daily frequency even for supported intraday cases.
6. The external case driver duplicates a smaller orchestration loop instead of using one shared probe/repair/acceptance workflow.
7. Incomplete episodes have no transactional resume, and interrupted model calls can have unknown usage.
8. Isolation protects host resources; audit objects share a Python process with strategy code, so deliberately adversarial evidence tampering remains outside the demonstrated guarantees.

The prior three historical repairs have native replay and upstream-patch evidence. These known issues constrain generalization to arbitrary new strategies; they are not a claim that those particular patches were fabricated or invalid.
