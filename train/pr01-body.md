## fix: thermal and heat_topology bugfixes on existing code

Small, independent fixes to code that is already on master: thermal loads,
shared thermal tanks, heat_topology, and two general robustness fixes that
also protect setups without any thermal load. No new features, no new
parameters, no schema or `param_definitions.json` changes, no changes to
`opt_res_latest.csv` columns.

Each fix is its own commit with a regression test that **fails on current
master and passes with the fix**. They were found by running the stack daily
on a live install and by a 20-day rolling-MPC replay against measured data
(thanks @Thimpey, #539).

### Fixes

| Commit | What was wrong | Visible effect before the fix |
|---|---|---|
| building_demand gains | a shared tank using the building physics model ignored `window_area` / `shgc` / `internal_gains_factor` (the compiler folds them onto the tank, the physics call never passed them) | planned heating 1.8-2.2x measured in the #539 replay |
| def_current_power pin | shared-tank members (`thermal_source`) were not treated as thermal loads by the step-0 power pin | a continuous heat pump on a shared tank had its t=0 power hard-pinned; the run could go Infeasible |
| predicted temperature publish | `_publish_thermal_loads` skipped `thermal_source` loads | `custom_predicted_temperature_id` published nothing for heat_topology configs |
| publish ids | the default per-load entity lists were built from the configured load count, before a heat_topology compile or a runtime `def_load_config` raises it; a caller's list shorter than the load count was not padded either | publish-data raised `IndexError`: for a topology with more flows than configured loads, or for any short `custom_*_id` list. Now missing entries get the default names, with a warning when the list came from the caller |
| open-meteo fail-soft | on a cold start, a failed open-meteo request returned `None` and crashed with a `TypeError` the #997 fail-soft guard does not catch | an offline `list`-method setup with a thermal load crashed instead of planning without solar gains |
| open-meteo weather for heat_topology | `_list_method_needs_weather` only recognised `thermal_config` / `thermal_battery` | `list`-method setups with heat_topology computed every curve COP against the constant 15 C fallback |
| null `min_temperatures` entry | `np.maximum` propagates the NaN of a null static entry | the weather-compensated curve floor was dropped for exactly the slots marked curve-only |
| `def_minimum_on/off_time` normalisation | not routed through `check_def_loads` like the sibling per-load arrays | a `null` entry (e.g. `[3, null]` from a partial set-config) stopped the run with `Invalid def_minimum_on_time value at index 1: None` |
| config diagnostics | `min_power > nominal_power` not rejected by the topology compiler; `thermal_battery` without a demand model raised a bare `KeyError`; `thermal_inertia` missing from the #943 unknown-key allow-list | the source silently never ran (or the run was Infeasible when its heat was needed); such a topology now stops with a field-naming error. Unhelpful stack trace; a false "unknown key is ignored" warning |
| thermal_inertia at the horizon | the per-load lag had no upper bound | `thermal_inertia` at or past the horizon crashed the build with `ValueError: Invalid dimensions (0,)` |
| solcast test isolation | three solcast mock tests used the machine-global daily quota counter | they fail after 8 solcast fetches on the same machine and day (repeated local runs, reused runners) |
| shared-tank two-source test | the test built an infeasible MILP and passed against the relaxed-LP fallback | the test guarded nothing |

### Documentation

One docs commit covers what these fixes make reliable, so users can rely on it
when onboarding:

- `heat_topology.md`: `min_power` <= `nominal_power` (and the validator says
  so); `building_demand` honours `window_area` / `shgc` /
  `internal_gains_factor`; a new **Publishing results** section (flow order =
  load index, `predicted_temp_heater{k}` / `heating_demand_heater{k}`, the
  `custom_*_id` runtime parameters, matched by position, with default names
  for loads without an entry); where the outdoor temperature comes from
  per weather method, that the 15 C fallback is silent, and what to pass when
  it is unavailable.
- `thermal_battery.md`: at least one demand model is required; for shared
  tanks and heat_topology storage, a `null` `min_temperatures` entry defers to
  `min_temperature_curve` (a standalone `thermal_battery` does not read the
  curve).
- `thermal_model.md`: `thermal_inertia` is applied in whole timesteps
  (rounded down) and capped at the horizon.
- `config.md`: `def_minimum_on_time` / `def_minimum_off_time` padding and
  `null` handling.

The Sphinx build shows no warnings for the changed pages.

### Users without temperature management

Nothing here changes a plan for a setup without thermal loads. Verified A/B
against current master with six non-thermal configurations (defaults,
battery, semi-continuous loads with min on/off time, three loads with short
per-load arrays, `def_current_power`, single-constant loads): the result
DataFrames are **byte-identical**. The changes such users can notice are
all on error paths: a `null` in `def_minimum_on_time` / `def_minimum_off_time`
now means 0 instead of stopping the run, and an Open-Meteo cold-start failure
now fails with a readable `ValueError` instead of a `TypeError`, and a
`custom_*_id` list shorter than the load count publishes the missing loads
under their default names with a warning, instead of raising `IndexError`.

Smaller side effects of the fixes, for completeness:

- `def_minimum_on_time` / `def_minimum_off_time` now go through the same runtime
  normalisation as the other per-load arrays: a runtime scalar is broadcast to
  every load, and a short runtime list logs the #1040 warning.
- A negative `thermal_inertia` is clamped to 0 (before, it built a malformed
  model).
- The building_demand gains are part of the problem when it is built. With the
  warm-start cache a reused problem keeps the first run's gains, the same way
  it already keeps the outdoor temperature; <link to PR 2> bypasses the cache for
  shared tanks.

### Not in this PR (on purpose)

- **Lag rounding.** The per-load path truncates `thermal_inertia / time_step`
  while the shared-tank path rounds. Aligning them changes the plan for ratios
  with a fractional part >= 0.5, so that goes to an issue first. The clamp here
  keeps truncation and only removes the crash.
- **Relaxed-LP fallback and solver-status handling.** A separate PR, because it
  changes published statuses.

### Verification

- Every regression test: red on master, green with its fix.
- Full suite on this branch: 1246 passed, 1 skipped, 32 xfailed. Two tests that fetch live open-meteo data failed in a sandbox without network; they fail identically on master there and are untouched by this PR.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
