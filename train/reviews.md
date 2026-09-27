# Independent review of the train (round 1)

Each PR was reviewed by a separate agent that had not written it. Each review
read the diff against its base and checked it against AGENTS.md. Regression
tests were re-run red/green in a clean worktree, and suspicious claims were
probed with small reproducers. The agents did not commit anything.

"Status" is what was done about each finding after the review.

## Summary (findings as reported; see "Status after fixes" below)

| PR | Verdict | Blocking findings |
|---|---|---|
| 1 | needs changes (docs / body only) | a doc claim about `min_temperature_curve` that only holds for shared tanks |
| 1b | ready with nits | the body says a healthy run was flagged, but HiGHS (the default) never returns `optimal_inaccurate` |
| 2 | needs changes | the `draw_off_demand` cache-key commit is a no-op after the #970 bypass, and its comment is wrong; the published `min_temp_heater` ignores `min_temperature_curve` |
| 3 | needs changes | a tank-level `overshoot_temperature` with a semi-continuous source turns Optimal into infeasible (→ relaxed) |
| 4 | needs changes | `P_transfer_*` is all zeros after a relaxed rescue; its regression test is vacuous; the start-below-floor ramp loosens floors that were reachable |
| 5 | needs changes | the DP ignores a tank's flat `thermal_losses` (the default tank type), so it plans too cold and too optimistic a COP |
| 6 | ready with nits | the `min_power` collision warning skips non-semi-continuous capped sources |
| 7 | ready with nits | per-load `prior_heat` docs point to the shared-tank recipe (kWh of heat instead of W of input) |
| 8 | needs changes | no test that the day-ahead solve actually uses the peak; four places still say MPC-only |
| 9 | needs changes (**blocker**) | a time-out with no incumbent is published as `Optimal (Incumbent)` with an all-zero plan |
| 10 | needs changes | the walkthrough's topology is Python, not JSON; the publish example can crash (IndexError); the shower profile moves with MPC |

## Blocker detail: PR 9, time-out without an incumbent

Checked independently with cvxpy 1.7.5 and HiGHS:

- **Time-out with no solution found:** HiGHS returns `status=user_limit` and
  `value=0.0`, with `primal_solution_status=0` and `mip_gap=inf`. The
  constraints are violated by large amounts.
- **Time-out with a solution found:** `primal_solution_status=2`.

"value is not None" therefore does not prove that an incumbent exists. The fork
branches `feature/hp-thermal-cap` and `feature/dp-cop-solver` carry the same
logic.

## Cross-cutting (decision for the author)

- **Authorship and trailers:** done. Every commit is now authored and
  committed by the contributor (one commit keeps its upstream co-contributor),
  and assistant trailers and session links are removed from commit messages
  and PR bodies.
- **AGENTS.md "issue first":** several PRs change `optimization.py` output by
  more than ~3 lines. Reviewers suggest opening an issue first for:
  - PR 2 (overshoot on continuous loads);
  - PR 3 (size; the reviewer proposes a split into 4 PRs);
  - PR 4 (the helper refactor);
  - PR 8 (MPC-only was deliberate on master).
- **Fix-on-fix history:** PR 5 has 34 commits, including a reversal. Squashing
  it into 3-4 logical commits, or squash-merging it, is recommended.

## Findings per PR

### PR 1
1. The `thermal_battery.md` "null defers to the curve" statement: a per-load
   `thermal_battery` never reads `min_temperature_curve`. It is true only for
   shared tanks and heat_topology storage.
2. `heat_topology.md` has two inaccuracies:
   - "logs a warning and uses 15 °C": the fallback in
     `_get_clean_outdoor_temp` is silent;
   - "one entry is enough" holds only when the storage's member is load 0.
3. The PR body should mention the smaller visible changes:
   - `def_minimum_on/off_time` are re-normalised at runtime;
   - a negative `thermal_inertia` is clamped to 0.
4. Nits:
   - "exactly one demand model" should say "at least one";
   - a comment still says "9 arrays" (there are 11);
   - a shared-tank test uses `assertIn("Optimal")` where it should use
     `assertEqual`;
   - a test comment describes `check_def_loads` inaccurately.
5. Shared-tank gains are frozen on a warm-start cache hit. This already
   exists; PR 2's bypass fixes it.

### PR 1b
1. The body overstates the reach: only CPLEX and Gurobi return
   `optimal_inaccurate`.
2. The docs row should read "a feasible solution the solver could not prove
   optimal (e.g. a CPLEX time limit); not produced by HiGHS".
3. Nits:
   - the branch name;
   - add an assert against `cp.OPTIMAL_INACCURATE.title()`;
   - `/api/v1/plan` keeps the last good plan.

### PR 2
1. `draw_off_demand` cache-key commit (119623a7):
   - it is a no-op because shared tanks bypass the cache;
   - its comment wrongly says the tank `start_temperature` is updated at
     runtime;
   - its test locks that claim in.
2. The published `min_temp_heater{k}` for tank members copies the static list,
   while the solver uses `resolve_min_temperatures` (list and curve).
3. Overshoot on continuous loads changes plans. Issue first, or flag it in the
   body.
4. Comments cite a web-UI caller of `compile_heat_topology` that does not exist
   at this point.
5. Check that upstream #970 is this bug.
6. One test passes on the base. Reword the claim "every regression test fails
   on the base".

### PR 3
1. **The semi-continuous overshoot gate** `is_overshoot[1:] + bin2[:-1] <= 1`
   can make a previously feasible run infeasible.
2. The capped heat pump in the doc example never runs with the default
   semi-continuous sources. Document `treat_as_semi_cont: false` or warn.
3. Combi tank: with no `indoor_target_temperature`, the building demand is
   computed against the DHW minimum.
4. Save-time validation can still return a 500 (`AttributeError` for
   `"flows": "x"`).
5. Smaller issues:
   - the string `"false"` enables extend mode;
   - `pad_defaults` misses `def_minimum_on/off_time`;
   - misleading warning text in extend mode.
6. Fork-internal wording in commit messages.

### PR 4
1. **After a relaxed rescue, `P_transfer_*` is read from the restored (failed)
   problem, so it is all zeros.**
2. `test_relaxed_rescue_restores_transfer_vars` patches a hook that does not
   exist yet, so it passes without the fix.
3. The start-below-floor ramp triggers whenever any floor is above the start,
   even when a single step could recover. Reachable floors get loosened for 6
   steps, and it logs at INFO on every run.
4. The building-zone docs example bounds only step 0 with `max_temperatures`.
5. Smaller issues:
   - `plan_output_schema.md` is stale;
   - window solar duplicates `calculate_surface_solar_gain`;
   - the "Bug A" docstring label.

### PR 5
1. **The DP ignores the flat `thermal_losses`, and the coupled store's own
   demand.**
2. `test_dp_cop_refinement_noop_when_consistent` does engage the DP.
3. The re-solve is not warm-started (new `cp.Problem`). Only HiGHS gets half the
   budget.
4. The DP ignores `desired_temperatures` and per-step bounds.
5. The DP runtime is unbounded by the time-out: 27 s at the state cap on x86.
6. A cooling source with only `heating_curve` breaks even under `static`.
7. Smaller issues:
   - `static` creates a Parameter (not byte-identical, differences ≤ 1e-11);
   - `cop_solver` is not validated;
   - several docs inaccuracies.

### PR 6
1. The `min_power` collision warning only runs for semi-continuous sources. The
   reviewer reproduced a silent abandonment with a continuous source.
2. The DP ON-level re-derivation test never changes the COP.
3. Smaller issues:
   - the warning is logged twice per tick;
   - `minimum_power_of_deferrable_loads[k]` is read unguarded;
   - NaN / inf / `True` pass validation.

### PR 7
1. Per-load `prior_heat` is W of electric input, but the docs link to the
   shared-tank kWh recipe.
2. The update recipe assumes one MPC run per step.
3. Per-load `prior_heat` in the cache key means a warm-start miss on every
   tick. The body should say so.
4. Smaller issues:
   - a misaligned length is truncated silently;
   - failure behaviour differs between the two paths;
   - the known-key test uses a scalar;
   - test gaps;
   - storage-level `prior_heat` is undocumented.

### PR 8
1. The claimed regression test only checks `passed_data`. It needs an
   end-to-end day-ahead test on `peak_import`.
2. Places that still say MPC-only:
   - `passing_data.md:185` and `:342`;
   - `runtime_params.json:40`;
   - the cookbook comment.
3. Billing-period rollover: day-ahead has no `capacity_charge_window`. Document
   resetting the peak.
4. Plans change for anyone who already sends `current_period_peak` to
   day-ahead with a capacity cost.
5. Code comments:
   - "applies to dayahead/perfect too" is wrong;
   - the type hint should match MPC.

### PR 9
1. **Blocker above.** Apply the same check to the DP re-solve, and to the
   relaxed solve (which is now a MILP and can itself time out).
2. The relaxed solve's `user_limit` is treated as failure. Log messages still
   say "LP".
3. The healthy DP path changes: a time-limited DP re-solve is now accepted.
   Say so.
4. The tests do not discriminate:
   - the shared-tank mutex test passes on the base;
   - add a forced-fallback test with a mutex group.
5. `publish_data.md` needs rewording: "respects all constraints", and the
   status order.

### PR 10
1. The walkthrough's topology is Python (`False`, `[0.0] * 14`). The config box
   only accepts JSON.
2. Publishing with the default ids crashes. Those ids are built from
   `number_of_deferrable_loads` before the topology compiles, so
   `custom_deferrable_forecast_id` has 2 entries for 3 loads. The docs must pass
   3 ids and say what each sensor drives.
3. The consumer profile is indexed from the horizon start, not the time of day.
   Under MPC it moves with every run.
4. `section_thermal.md` changes:
   - `efficiency` must map to `electric` (or to gas with a `cost_track`);
   - list the missing fields;
   - renumber the per-load arrays after removing a `thermal_battery`.
5. Smaller issues:
   - extend-mode index shift;
   - exact error text;
   - `cop_solver` is a config setting;
   - link to the MPC page;
   - units.

## Status after fixes

Every blocking and medium finding was fixed on its branch, with a regression
test that fails without the fix where the finding was a code defect. The stack
was then rebased, and each branch's full suite was re-run.

| PR | Fixed | Left as is, stated in the PR body |
|---|---|---|
| 1 | doc scope of `min_temperature_curve`; silent 15 C fallback; publish ids matched by position; "at least one" demand model; test nits; **new: default publish ids padded when a topology adds loads (was IndexError)** | the smaller side effects are now listed in the body |
| 1b | docs/comment say which solvers return `Optimal_Inaccurate`; test tied to `cp.OPTIMAL_INACCURATE` | branch name; empty-publish crash (predates the PR) |
| 2 | no-op cache-key commit dropped; published `min_temp_heater` is the enforced floor; caller references; stale docstring | overshoot plan change on continuous loads (flagged; can move to an issue) |
| 3 | overshoot gate no longer makes semi-continuous sources infeasible; capped semi-continuous sources documented; combi-tank indoor default 20 C; type validation (no 500, no `"false"` extend); min on/off times do not leak in extend mode; exact error text | heat-pump warning logger; cap gate on cooling tanks; split suggestion offered in the body |
| 4 | `P_transfer_*` published from the solved problem after a rescue, with a real test; recovery floor is soft and priced (no longer loosens reachable floors); zone example bounds the horizon; schema doc | window-solar duplication; relaxed fallback keeps transfer binaries |
| 5 | DP includes the flat standing loss; no-op test really checks no DP; cooling source with `heating_curve`; `cop_solver` validated; half time limit for Gurobi/CPLEX too; `static` builds exactly the old problem; docs corrected | DP ignores `desired_temperatures` / per-step bounds, DP runtime, coupled-store demand, absolute consistency check (all stated) |
| 6 | `min_power` collision warns for continuous sources too, once per change; `max_thermal_power` validation | none |
| 7 | per-load `prior_heat` unit (W) and recipe; cadence per time step; alignment logged; cache trade-off stated; storage-level field documented | making `prior_heat` a Parameter (follow-up) |
| 8 | end-to-end day-ahead test; all MPC-only wording; rollover caveat; comments and type hint | design question for the maintainer (stated) |
| 9 | **time-limited solves kept only with a proven feasible incumbent** (HiGHS `primal_solution_status`, else constraint check), also for the DP and the relaxed solve; real time-out test; discriminating mutex test; docs | none |
| 10 | walkthrough JSON conversion, default sensors and what they drive, profile alignment, `costfun` for the gas track, migration guide fields and per-load arrays, several wording fixes | none |
