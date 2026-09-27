# Independent review of the train (round 2)

Each PR was re-reviewed at its pushed tip by a fresh agent. Each review read the
diff against its base and checked it against AGENTS.md and the PR body. Tests
were re-run red/green, and reproducers were written where something looked off.
Each review then compared the result with round 1 (`reviews.md`).

## Summary

| PR | Verdict | Round-1 findings | Remaining must-fix |
|---|---|---|---|
| 1 | ready with nits | all resolved | publish-id padding also pads user-passed lists (narrow it or log it, and say so in the body); `plan_output_schema.md` stale |
| 1b | ready with nits | resolved, one new inaccuracy | "CPLEX or Gurobi": in cvxpy a Gurobi time limit maps to `user_limit`, so only CPLEX; empty-publish crash on a temp-only folder not mentioned |
| 2 | needs changes | resolved | the continuous overshoot gate blocks heating at t when T[t] is above the threshold: a run that was Optimal becomes infeasible, and the relaxed rescue fails too (verified fix: `p[:-1] <= P * (1 - is_overshoot[1:])`) |
| 3 | ready with nits | resolved (500 on save only at top level) | `max_startups` / `startup_penalty` barely act on continuous sources; nested malformed entries still give a 500; uncapped heat-pump warning fires for cool and for already-capped storages; runtime `shared_thermal_tanks` docs incomplete |
| 4 | needs changes | resolved | save-time validation regression (a storage with no `volume` / `thermal_mass`, or a negative `max_transfer_power`, is saved and fails the next run); a zone with `thermal_inertia` sitting on its floor is infeasible; a transfer can move more heat in one step than the temperature difference allows |
| 5 | needs changes | mostly resolved | the re-solve ceiling uses `max_supply` (default 70), so it rarely binds and a "refined" plan can still overstate the COP (0.77); the DP sees zero demand from a receiver without `loss_coefficient`; `test_dp_resolve_rejection_preserves_static_plan` is vacuous |
| 6 | ready with nits | one open | no test covers the DP re-derivation of the ON level (shown to be load-bearing) |
| 7 | ready with nits | resolved | "ships upstream" wording in a commit and a test docstring; test counts in the body |
| 8 | ready with nits | resolved | day-ahead with N>1 cannot represent the open interval (doc); cookbook version note |
| 9 | ready with nits | blocker resolved | no real test of the incumbent check on the DP re-solve; Gurobi wording; stale comments; squash the fix-on-fix commits |
| 10 | needs changes (small) | mostly resolved | the walkthrough prices DHW heat-pump heat with the space-heating curve (about 2x too cheap); the migration guide misses the concrete-to-water density / heat-capacity default change |

## Cross-cutting

- **Overshoot gate timing.** PR 2 (continuous `thermal_config`) and PR 3 (shared
  tank) now gate on T[t]. Each timing has a failure mode:
  - gating on T[t] fails when the start is above the threshold and the floor
    needs heat at t+1;
  - gating on T[t+1] fails for a semi-continuous source whose full step
    crosses the threshold.
  
  A consistent rule is to gate continuous sources on T[t+1] (they can
  modulate) and semi-continuous sources on T[t].
- **Gurobi.** In cvxpy 1.7.5 a Gurobi time limit maps to `user_limit` (so
  "Optimal (Incumbent)" with PR 9), not `optimal_inaccurate`. The docs, the
  `last_run.py` comment and the bodies of 1b and 9 should say CPLEX only.
- **History.** PRs 4, 5, 6 and 9 carry fix-on-fix commits whose messages
  describe intermediate states; squash before opening, or squash-merge.
- **Hygiene.** No AI attribution, session links or fork-internal references
  remain, apart from "ships upstream" in PR 7.
- **Users without thermal loads.** Unaffected in every PR; several reviewers
  re-checked with byte-identical A/B runs.
