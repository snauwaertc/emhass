## fix: seed the thermal_inertia dead zone with prior_heat under rolling MPC (#1136)

> Open this after the maintainer has answered #1136; it implements the fix
> proposed there.

With `thermal_inertia`, heat produced at step `t` only reaches the store at
`t + 1 + L`, so the first `L` steps of a solve carry no source term. That is
right for a one-shot day-ahead plan, where nothing precedes the horizon. A
rolling MPC re-solve starts mid-flight: heat committed by the previous runs is
still on its way, and the model has no state for it. Over that window the
predicted temperature does not depend on anything the optimizer can choose, so
it cannot see the effect of its own past actions and keeps re-injecting heat,
returning an Optimal plan that over-provisions heating.

Reported by @Thimpey on #539 with a 96-run rolling-MPC repro on a real install:
36.58 kWh planned without an initial condition, 10.83 kWh with it, 11.0 kWh
measured.
Stacked on <link to PR 6>; the diff below is only this PR's.

### Change

- `prior_heat` as the missing initial condition on both lagged paths:
  - per-load `thermal_config` (already on master): `prior_heat` in **input
    watts** per step, the unit that model already uses;
  - shared-tank storage (from <link to PR 4>): thermal **kWh** per step,
    passed per run with the runtime parameter `shared_tank_prior_heat`, keyed by
    storage id, like `shared_tank_start_temperatures`.
- Values are validated (finite, non-negative, numeric): this is runtime state
  from a plan or sensor feed, and a bad value would otherwise skew the
  trajectory into a plausible-but-wrong Optimal plan. A malformed
  `shared_tank_prior_heat` entry warns and is ignored (cold start for that
  storage); a malformed per-load `prior_heat` in `def_load_config` raises a
  `ValueError`, like the other `thermal_config` fields. A shorter list is
  right-aligned, a longer one keeps its most recent values, and either
  alignment is logged.
- Absent or empty gives zeros, which reproduces the current behaviour exactly.
- `prior_heat` stays structural in the optimization cache key, because it is
  baked into the constraint as a raw array; this is noted at the exclusion list
  so it is not later "optimized" into a stale-state bug. **Trade-off:** a
  `thermal_config` load whose `prior_heat` changes every run misses the
  warm-start cache every run. (Shared tanks already rebuild every run.) Making it
  a `cp.Parameter` refreshed on a cache hit would restore warm starts; I kept
  that out of this PR.
- `prior_heat` is added to the #943 known-key list for `thermal_config`, so
  using it no longer triggers an "unknown key is ignored" warning.
- `runtime_params.json`: `shared_tank_prior_heat` (additive).

### Documentation

- `heat_topology.md`: why a lagged storage needs an initial condition under
  rolling MPC, `shared_tank_prior_heat`, and how to keep it current from
  **delivered** heat, not from the new plan's own first steps.
- `thermal_model.md`: `prior_heat` on a `thermal_config` load, in input W,
  with its own update recipe.
- Both recipes shift the window once per completed time step, and resend the
  same list when MPC runs more often than that.
- `passing_data.md`: `shared_tank_prior_heat`.

### Users without temperature management

Unchanged. A/B against master with six non-thermal configurations:
byte-identical result DataFrames. Without `prior_heat`, thermal configurations
are unchanged too.

### Verification

- Regression tests (per-load and shared-tank initial condition, validation,
  runtime parameter parsing, known-key list): 7 of 8 fail on the base, all pass
  with the change.
- Full suite: 1360 passed, 1 skipped, 32 xfailed. Two tests that fetch live
  open-meteo data failed in a sandbox without network; they fail identically
  on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
