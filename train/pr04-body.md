## feat: one thermal model in heat_topology - building zones, tank-to-tank transfers, window solar (#539)

Makes the heat_topology storage a superset of the two single-load thermal
models, so a hybrid system can combine them: a heat pump and a gas boiler
charging a buffer that feeds the house through its emitters, with the house
modelled as a thermal mass that can be pre-heated. Everything is opt-in; a
storage without the new fields is the same water tank as before.
Stacked on <link to PR 3>; the diff below is only this PR's.

### What it adds

| Feature | Field(s) | Notes |
|---|---|---|
| Building-zone storage | storage `thermal_mass` (kWh/K), `loss_coefficient` (kW/K) | state-dependent loss `UA*(T - outdoor)`: a warmer zone loses more, so pre-heating on cheap power and coasting through a price peak shows up in the plan |
| Heat-input lag on storage | storage `thermal_inertia` (h) | same whole-step convention as the per-load model (truncate), capped at the horizon; see <link to lag issue> |
| Window solar for zones | storage `window_area`, `shgc` | gain `window_area * shgc * GHI` from the forecast already fetched for PV; applies to a zone with `loss_coefficient` and needs GHI in the weather data |
| Tank-to-tank transfers | storage-to-storage `flows` with `transfer_coefficient` (kW/K), `max_transfer_power` (W) | hot-to-cold only, at most `k * (T_from - T_to)`; zero when the receiver is as warm or warmer |
| Pump schedule | result columns `P_transfer_{from}_{to}` (W) | additive columns in the result CSV and `/api/v1/plan`; not published as HA sensors |
| Start below the floor | - | a storage that starts below a minimum it must meet soon (including a setback floor that rises a few steps later) gets a soft floor over a recovery window instead of an infeasible problem |

**Refactor note.** The per-step bound, overshoot indicator and comfort penalty
were implemented three times (thermal_config, thermal_battery, shared tank).
They are extracted into `_add_temp_bound`, `_overshoot_indicator` and
`_comfort_penalty`. The shared-tank and thermal_config paths use all three;
thermal_battery uses the overshoot and penalty helpers and keeps its hard
bounds inline. This is behaviour-preserving:
no existing test is changed, and plans without thermal loads are
byte-identical. I know `optimization.py` restructurings normally need an issue
first; the extraction is limited to these three helpers, which the new storage
features need anyway. I can split it into its own PR if you prefer.

**Recovery window.** When a storage starts below a near-term floor (one of the
first 6 steps; a floor that steps up later stays hard), the hard
floor is ramped up from the start temperature (at most 0.5 C per step, over at
least 6 steps), and every degree below the configured floor inside that window
is priced with a weight that dominates energy prices. A storage that can
recover in one step therefore still does (the plan is the same as before); one
that cannot follows the ramp instead of making the problem infeasible. The
three values are module-level constants (`SHARED_TANK_START_RECOVERY_STEPS`,
`SHARED_TANK_START_RECOVERY_RATE`, `SHARED_TANK_START_RECOVERY_PENALTY`) and
are design choices. The penalty weight is per degree per step in the
objective's currency, so with very high electricity prices it may no longer
dominate.

**Thermal-inertia dead zone.** Over the first `L` steps of a storage with
`thermal_inertia`, no source heat arrives, so a hard floor there made a zone
that sits on its floor infeasible on the next run. Those floors are priced
instead. On a storage fed only by transfers the lag has no effect (transfers
are not lagged), so it is ignored with a warning.

**Validation at save time.** With `volume` now optional, the compiler checks
that each storage has a positive `volume` or `thermal_mass`, and that transfer
fields are positive, so an unusable topology is refused when it is saved.

### Fixes to the new code in this PR

- A transfer into a receiver that is hotter than the feeder made the whole
  problem infeasible; the transfer is now gated on/off.
- A transfer naming a storage with no temperature state is forced to zero with
  a warning, instead of being bounded by `max_transfer_power` alone (which
  would allow heat to flow uphill).
- An ID shared by a source and a storage turned a transfer into a source flow;
  it is now rejected.
- `tank_transfers` from a previous compile were kept or duplicated on re-merge;
  they are now replaced.
- A transfer is also limited by the temperatures at the end of the step, so a
  step can no longer leave the receiver hotter than its feeder.
- After a relaxed rescue, `P_transfer_*` is read from the problem that was
  solved (it was published as zeros), and the transfer variables are restored
  afterwards, so a reused problem does not publish a frozen pump schedule.
- A lag at the end of the horizon no longer crashes the build.
- A `null` in `min_temperatures` means "no bound at this step" instead of
  becoming `nan`.

Known limits, left as they are: the relaxed fallback keeps the transfer on/off
binaries (it is still a MILP, not a pure LP), and window solar duplicates the
formula of the existing `solar_absorption_area` path rather than reusing its
helper.

### Commits

1. The compiler: zone fields, storage-to-storage flows, validation.
2. The optimizer: zones, transfers, window solar, lag, start below the floor.
3. Docs.

### Documentation

- `heat_topology.md`: building-zone storage (fields, example, equivalence to
  `thermal_battery` / `thermal_config`); tank-to-tank transfers; the recovery
  ramp; where a transfer-only storage's temperature and the `P_transfer_*`
  columns appear; the shared-ID rule.
- `plan_output_schema.md`: the `P_transfer_{from}_{to}` columns and the
  transfer-only storage column.

### Users without temperature management

Unchanged. A/B against master with six non-thermal configurations (defaults,
battery, semi-continuous loads with min on/off time, three loads with short
per-load arrays, `def_current_power`, single-constant loads): the result
DataFrames are byte-identical.

### Verification

- Every regression test fails without its fix and passes with it (checked
  before the review-round fixes were squashed); every commit passes the full
  suite.
- Full suite: 1325 passed, 1 skipped, 32 xfailed. Two tests that fetch live open-meteo data failed in a sandbox without network; they fail identically on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
