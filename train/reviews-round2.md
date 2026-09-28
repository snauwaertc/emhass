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

## Status after fixes

Every finding above was fixed on its branch, with a test that fails on the old
tip and passes on the new one where the finding is about behaviour. The
cascade was rebased (1 → 2 → … → 7 → 9, and 10 on 7); 1b and 8 stay on master.

| PR | What was done |
|---|---|
| 1 | Padding a short user-passed publish-id list is logged as a warning; `shgc` 0 is honoured; `plan_output_schema.md` updated. |
| 1b | Publishing from a folder with only temp files falls back instead of crashing; "CPLEX" only (Gurobi's time limit is `user_limit`). |
| 2 | Overshoot gate: continuous sources gate on T[t+1], semi-continuous on T[t]; heating from a start above the threshold works again. Id 0 is a valid id. |
| 3 | Same gate rule for shared tanks; nested malformed topology entries give a 400, not a 500; the uncapped heat-pump warning no longer fires for cooling or already-capped storages; runtime `shared_thermal_tanks` docs completed. |
| 4 | Save-time validation of storage capacity and transfer limits restored; a zone with `thermal_inertia` on its floor gets soft floors over the dead zone; a transfer is bounded at the end of the step too, so it cannot overshoot the temperature difference; lag on a transfer-only storage is ignored with a warning. |
| 5 | Per-step re-solve ceiling at the DP trajectory + 1 C (and the curve supply when the DP is infeasible); a receiver without `loss_coefficient` keeps its demand; the rejection test compares with the static plan. **New in this round:** the per-step ceiling exposed that the DP did not see the tank's `desired_temperatures`, so a tank starting below its target was left cold with an Optimal status; the DP now prices the comfort shortfall like the solve (test red/green). |
| 6 | Test for the DP re-derivation of the ON level (red without it); the `min_power` warning names the deferrable load and is not repeated by the relaxed rescue; ON-level wording in the docs; clearer message for an infinite cap. |
| 7 | "Already on master" wording (test and commit message); `prior_heat` without a lag is logged; docs on what it sums, alignment, counter recipe and validation; body counts (9 of 10 tests red on the base). |
| 8 | Day-ahead with N>1 documented as not representing the open interval; cookbook version note. |
| 9 | Rebased onto PR 5's skip guard (one combined guard); a real DP re-solve time-out test (red without the incumbent check); the time-out test asserts the actual outcome (`User_Limit`, no plan); MIP gap in the incumbent log; solver report read inside the try; CPLEX/Gurobi wording; output-schema statuses. |
| 10 | Heat pump modelled as two sources (DHW 55 C supply, space-heating curve) in one mutual-exclusion group; one-value maximum-temperature lists (which bound only the first step) replaced by per-step lists; migration guide: concrete vs water defaults, per-load settings, no-equivalent fields; `temp_predicted2` and `Optimal_Inaccurate` rows; `cop_solver` scope; the test executes the page's own Python block. |

Fix-on-fix history (PRs 4, 5, 6, 9) is left as is; each body offers a squash.
