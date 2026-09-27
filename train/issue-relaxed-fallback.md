**Title:** Relaxed-LP fallback: mutual exclusion, time-limited incumbents, and how to report "Optimal (Relaxed)"

**Describe the bug**
Three related questions about the relaxed-LP fallback in
`perform_optimization`. Each is a design choice, not an obvious bug, so I am
asking before opening PRs. I have working implementations for all three,
running daily on a live install.

1. **`mutual_exclusion` is dropped in the fallback.**
   `_add_deferrable_group_constraints(..., relaxed=True)` keeps
   `max_combined_power` but skips mutual exclusion, because the relaxed LP has
   no binaries. The fallback then schedules both members of a group in the
   same timestep. For a group that models one physical device (one heat pump
   serving DHW or space heating) that plan cannot be executed. Reported by
   @Micr0mega in #539: a shared-tank heat source in a `mutual_exclusion` group
   ran both loads at once after the fallback.
   *Proposal:* keep mutual exclusion in the fallback with its own binaries
   (one per member), so the fallback becomes a small MILP instead of a pure
   LP. If one-source-per-slot genuinely cannot meet demand, the run is then
   reported infeasible instead of publishing a plan that violates the group.

2. **A time-limited solve discards its incumbent.** `"user_limit"` is in
   `fail_statuses`, so a MILP that hits `lp_solver_timeout` goes to the
   relaxed LP even when HiGHS already holds a feasible, binary-respecting
   incumbent. For long horizons with several semi-continuous loads that
   incumbent is usually a better plan than the relaxed LP, which may run a
   semi-continuous load below its nominal power.
   *Proposal:* when the status is `user_limit` and the solver reports a
   feasible solution (HiGHS: `primal_solution_status == 2`; a value alone is not
   enough, since a time-out before any solution also returns value 0.0), keep
   the incumbent and publish it as a distinct status (e.g.
   `"Optimal (Incumbent)"`); fall back to the relaxed LP only for
   infeasible/unbounded/no-value.

3. **How should `"Optimal (Relaxed)"` be reported?** Its plan is published to
   the sensors, but `/api/v1/last-run` reports the run as `error` and
   `/api/v1/plan` keeps serving the previous plan. That is defensible (the
   plan drops binary constraints) but it means the sensors and `/api/v1/plan`
   disagree after a fallback.
   *Options:* (a) keep it as is and document it (I documented the current
   behaviour in <link to PR 1b>); (b) report it as `ok` on both endpoints;
   (c) add a distinct last-run status such as `degraded`. That would be an
   additive schema change to `last-run.schema.json`.

**To Reproduce**
1. Two continuous deferrable loads in a `deferrable_load_groups` entry with
   `"mutual_exclusion": true`.
2. Force the fallback, e.g. with a very short `lp_solver_timeout` on a 288-step
   horizon, or with a semi-continuous member whose nominal power cannot fit the
   thermal band.
3. The published plan has both members above zero in the same timestep, with
   `optim_status` `"Optimal (Relaxed)"`.

**Expected behavior**
Mutual exclusion holds in every published plan, and a time-limited solve keeps
its feasible incumbent. For question 3, whichever option you prefer.

**Screenshots**
n/a

**Home Assistant installation type**
 - Home Assistant OS

**Your hardware**
- OS: HA OS
- Architecture: aarch64 (Raspberry Pi)

**EMHASS installation type**
 - Add-on

**Additional context**
Only the unambiguous part is in <link to PR 1b>: `Optimal_Inaccurate` runs,
whose plan is already published, are now reported as `ok` and served on
`/api/v1/plan`. None of the three items above is changed there.
