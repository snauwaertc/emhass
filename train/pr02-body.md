## fix: shared thermal tanks - stale plans, missing comfort columns, and validation gaps

Second batch of fixes to code that is already on master: shared thermal tanks
(`shared_thermal_tanks` / `heat_topology`), the per-load thermal model, and the
solve loop. No new features or parameters, no `param_definitions.json` changes.
Stacked on <link to PR 1>; the diff below is only this PR's.

Each fix is its own commit with a regression test that **fails on the base and
passes with the fix**.

### Fixes

| Commit | What was wrong | Visible effect before the fix |
|---|---|---|
| warm-start cache (#970) | a shared tank bakes its start temperature, forecast, COP and losses into the problem as constants; the cache-hit refresh only updates `thermal_config` / `thermal_battery` parameters | under rolling MPC every run after the first re-solved against the first run's tank temperature and forecast, still reporting Optimal |
| perfect forecast per day | same root cause inside `perform_perfect_forecast_optim`'s day loop | day 2, 3, ... were solved against day 1's weather |
| `draw_off_demand` in the cache key | excluded from the shared-tank hash on the assumption it is a parameter; for a shared tank it is baked in | a changed draw-off profile was ignored until an unrelated structural change |
| entries without `id` | the compiler built its id maps before checking ids | bare `KeyError('id')` instead of the documented field-path `ValueError` |
| comfort columns for tank members | the `target/min/max_temp_heater{k}` lookup only read the load's own `thermal_config` / `thermal_battery` | a tank member never published its comfort band, although the MILP used it |
| overshoot on a continuous `thermal_config` load | the overshoot indicator was tied to `p_def_bin2`, which a continuous load never links to its power | a continuous load heated straight through `overshoot_temperature` |
| solver exception | cvxpy keeps the previous status and value when `solve()` raises | on a reused problem, a crash republished the previous run's plan as Optimal |
| incomplete fuel source / profile consumer | `src["efficiency"]` / `c["profile"]` read without a check | bare `KeyError` with no path to the entry |

**Trade-off in the #970 fix:** configurations with shared tanks no longer
warm-start; each run builds the problem fresh (a few seconds for the MILP).
Configurations without shared tanks still use the cache, and a regression test
guards that. Parameterising the tank state like `thermal_battery` would restore
warm-starting later.

### Documentation

- `heat_topology.md`: the comfort columns each topology load carries; a
  **Rolling MPC** note (rebuilt every run, how to pass the measured
  temperature); the new validation messages.
- `thermal_model.md`: `overshoot_temperature` switches the load off whether it
  is semi-continuous or continuous.

### Users without temperature management

Unchanged. A/B against master with six non-thermal configurations (defaults,
battery, semi-continuous loads with min on/off time, three loads with short
per-load arrays, `def_current_power`, single-constant loads): the result
DataFrames are byte-identical. The only fix on a path such users can reach is
the solver-exception one, and it only changes what happens after a crash.

### Verification

- Every regression test: red on the base, green with its fix.
- Full suite: 1255 passed, 1 skipped, 32 xfailed. Two tests that fetch live open-meteo data failed in a sandbox without network; they fail identically on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QGQMaX47ARAZFK2bVCiJwC
