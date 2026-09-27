## feat: relaxed-LP fallback - keep mutual exclusion, keep time-limited incumbents, report both as ok

> Implements the three proposals in <link to relaxed-fallback issue>. Open it
> once the maintainer has chosen; each proposal is its own commit, so any of
> them can be dropped.

Stacked on <link to PR 7>. It also contains the `Optimal_Inaccurate` commit
from <link to PR 1b> (identical patch), because the status reporting builds
on the shared `OK_OPTIM_STATUSES`; if PR 1b is merged first, that commit
drops out of the diff.

### 1. Mutual exclusion survives the relaxed fallback

`_add_deferrable_group_constraints(..., relaxed=True)` skipped mutual
exclusion, so a fallback scheduled both members of a group in the same
timestep. For a group that models one physical device that plan cannot be
executed (reported by @Micr0mega in #539). The fallback now keeps it with one
binary per member (a small MILP instead of a pure LP). If one active member
per timestep cannot meet the demand, the run is reported **infeasible**
instead of "Optimal (Relaxed)" with both loads running.

### 2. A time-limited solve keeps its feasible incumbent

`user_limit` was in the fail list, so a MILP that hit `lp_solver_timeout` was
discarded for the relaxed LP even when HiGHS held a feasible, binary-respecting
incumbent. That incumbent is now published as **"Optimal (Incumbent)"**; the
relaxed fallback runs only for infeasible, unbounded, no-status or no-value
solves. The DP COP re-solve uses the same shared predicate.

### 3. Every published plan is "ok" on the API

"Optimal (Relaxed)" and "Optimal (Incumbent)" publish their plan to the
sensors, so they are added to `last_run.OK_OPTIM_STATUSES`:
`/api/v1/last-run` reports them as `ok` and `/api/v1/plan` serves them.
No schema change (`ok` / `infeasible` / `error` as before).

### Behaviour changes (all users, only on these error paths)

- A mutex-infeasible problem is now reported Infeasible (no plan) instead of
  an "Optimal (Relaxed)" plan that violates the group.
- A solve that times out after finding a feasible plan now publishes that plan
  ("Optimal (Incumbent)") instead of the relaxed LP's plan.
- `/api/v1/last-run` reports relaxed and incumbent runs as `ok` instead of
  `error`, and `/api/v1/plan` serves them.

A solve that finishes normally is unchanged: A/B against master with six
non-thermal configurations gives byte-identical result DataFrames.

### Documentation

- `publish_data.md`: every `optim_status` value, what it means for the plan,
  and how the API reports it.
- `heat_topology.md`: mutual exclusion also holds in the fallback.
- `advanced_math_model.md`, `config.md`: `lp_solver_timeout` and the
  incumbent.

### Verification

- The mutex test (26 h of mutually exclusive runtime in 24 h) fails on the
  base and passes; the max_supply_temperature gate is still checked in a forced
  relaxed fallback. The incumbent and status tests fail on the base and pass.
- Full suite: 1371 passed, 1 skipped, 32 xfailed. Two tests that fetch live
  open-meteo data failed in a sandbox without network; they fail identically
  on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QGQMaX47ARAZFK2bVCiJwC
