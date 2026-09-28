## fix: shared thermal tanks - stale plans, missing comfort columns, and validation gaps

Second batch of fixes to code that is already on master: shared thermal tanks
(`shared_thermal_tanks` / `heat_topology`), the per-load thermal model, and the
solve loop. No new features or parameters, no `param_definitions.json` changes.
Stacked on <link to PR 1>; the diff below is only this PR's.

Each fix is its own commit with a regression test that **fails on the base and
passes with the fix**. Three extra tests pass on the base on purpose: two
guards that configurations without shared tanks still use the cache and still
reuse the problem per day in perfect forecast, and
`test_shared_tank_fresh_build_honors_start_temperature`, which pins the
property the #970 bypass relies on.

### Fixes

| Commit | What was wrong | Visible effect before the fix |
|---|---|---|
| warm-start cache (#970) | a shared tank bakes its start temperature, forecast, COP and losses into the problem as constants; the cache-hit refresh only updates `thermal_config` / `thermal_battery` parameters | under rolling MPC every run after the first re-solved against the first run's tank temperature and forecast, still reporting Optimal |
| perfect forecast per day | same root cause inside `perform_perfect_forecast_optim`'s day loop | day 2, 3, ... were solved against day 1's weather |
| entries without `id` | the compiler built its id maps before checking ids | bare `KeyError('id')` instead of the documented field-path `ValueError` |
| comfort columns for tank members | the `target/min/max_temp_heater{k}` lookup only read the load's own `thermal_config` / `thermal_battery` | a tank member never published its comfort band, although the MILP used it; `min_temp_heater{k}` is now the floor the solver enforced, including `min_temperature_curve` |
| overshoot on a continuous `thermal_config` load | the overshoot indicator was tied to `p_def_bin2`, which a continuous load never links to its power | a continuous load heated straight through `overshoot_temperature`; now it heats up to the threshold and stops, with the same next-step timing as the semi-continuous path (so a start above the threshold can still heat when the floor needs it) |
| solver exception | cvxpy keeps the previous status and value when `solve()` raises | on a reused problem, a crash republished the previous run's plan as Optimal |
| incomplete fuel source / profile consumer | `src["efficiency"]` / `c["profile"]` read without a check | bare `KeyError` with no path to the entry (an integer id of 0 stays valid) |

**Plan change for existing users:** the overshoot fix changes schedules for a
continuous `thermal_config` load that sets both `overshoot_temperature` and
`desired_temperatures`: it now stops heating above the overshoot threshold, as
the semi-continuous path already did. If the maintainer prefers, this commit
can move to an issue first.

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
- Full suite: 1259 passed, 1 skipped, 32 xfailed. Two tests that fetch live open-meteo data failed in a sandbox without network; they fail identically on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
