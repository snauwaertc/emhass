## feat: relaxed fallback - keep mutual exclusion, keep time-limited incumbents, report both as ok

> Implements the three proposals in <link to relaxed-fallback issue>. Open it
> once the maintainer has chosen; each proposal is its own commit, so any of
> them can be dropped.

Stacked on <link to PR 7>. It also contains the `Optimal_Inaccurate` commit
from <link to PR 1b> (identical patch), because the status reporting builds
on the shared `OK_OPTIM_STATUSES`. If PR 1b is merged first, I rebase this PR
onto it: that commit drops out, and the status list and the `optim_status`
row in `publish_data.md` get a small merge (PR 1b's later commits touch the
same lines).

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
incumbent. That incumbent is now published as **"Optimal (Incumbent)"**.

A value is not proof of an incumbent: with cvxpy 1.7.5 and HiGHS, a time-out
before any solution is found also returns `user_limit` with value 0.0, every
variable at 0 and the constraints violated. So the incumbent is kept only when
HiGHS reports a feasible primal solution (`primal_solution_status == 2`); for
other solvers the constraint violations are checked directly. Without that
proof the run goes to the relaxed fallback, exactly as before. The DP COP
re-solve uses the same shared predicate, and the relaxed problem (a MILP too,
since it keeps the mutex binaries) may also use a feasible incumbent. The log
line of an accepted incumbent names the remaining MIP gap.

cvxpy maps a Gurobi time limit to `user_limit` as well, so Gurobi gets the same
treatment (its constraints are checked directly); only a CPLEX time limit comes
back as `optimal_inaccurate`.

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
- With `cop_solver` `auto` or `dp`, a DP re-solve that times out with a feasible
  incumbent is now accepted; before, the static plan was kept.
- `/api/v1/last-run` reports relaxed and incumbent runs as `ok` instead of
  `error`, and `/api/v1/plan` serves them.

A solve that finishes normally is unchanged: A/B against master with six
non-thermal configurations gives byte-identical result DataFrames.

### Commits

One per proposal, so any of them can be dropped, plus the PR 1b commit and
the docs:

1. Mutual exclusion in the relaxed fallback.
2. Time-limited incumbents.
3. `Optimal_Inaccurate` as ok (identical to PR 1b's commit).
4. Relaxed and incumbent plans as ok on the API.
5. Docs.

### Documentation

- `publish_data.md`: every `optim_status` value, what it means for the plan,
  and how the API reports it.
- `heat_topology.md`: mutual exclusion also holds in the fallback.
- `advanced_math_model.md`, `config.md`: `lp_solver_timeout` and the
  incumbent.
- `plan_output_schema.md`: which `optim_status` values come with a plan.

### Verification

- The mutex test (26 h of mutually exclusive runtime in 24 h) fails on the
  base and passes. A forced fallback with a mutual-exclusion group of two
  semi-continuous loads never runs both (8 overlapping steps on the base). The
  max_supply_temperature gate is still checked in a forced relaxed fallback.
- A real time-out without incumbent (`lp_solver_timeout` 1e-6, no mocks): the
  relaxed LP times out too, the status is `User_Limit` and no plan is
  published. A DP re-solve that times out before finding a solution (a real
  HiGHS run with a 1e-6 s limit on the re-solve only) is rejected and the
  static plan is published; that test fails without the re-solve's incumbent
  check. The check itself is unit-tested on HiGHS reports and on a direct
  constraint check.
- Full suite: 1407 passed, 1 skipped, 32 xfailed. Two tests that fetch live
  open-meteo data failed in a sandbox without network; they fail identically
  on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
