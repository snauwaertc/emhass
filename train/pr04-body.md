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
| Window solar for zones | storage `window_area`, `shgc` | gain `window_area * shgc * GHI` from the forecast already fetched for PV |
| Tank-to-tank transfers | storage-to-storage `flows` with `transfer_coefficient` (kW/K), `max_transfer_power` (W) | hot-to-cold only, at most `k * (T_from - T_to)`; zero when the receiver is as warm or warmer |
| Pump schedule | result columns `P_transfer_{from}_{to}` (W) | additive columns in the result CSV and `/api/v1/plan`; not published as HA sensors |
| Start below the floor | - | a storage that starts below a minimum it must meet soon (including a setback floor that rises a few steps later) gets a recovery ramp (at most 0.5 C per step, over at least 6 steps) instead of an infeasible problem |

**Refactor note.** The per-step bound, overshoot indicator and comfort penalty
were implemented three times (thermal_config, thermal_battery, shared tank).
They are extracted into `_add_temp_bound`, `_overshoot_indicator` and
`_comfort_penalty` and used by all three paths. This is behaviour-preserving:
no existing test is changed, and plans without thermal loads are
byte-identical. I know `optimization.py` restructurings normally need an issue
first; the extraction is limited to these three helpers, which the new storage
features need anyway. I can split it into its own PR if you prefer.

**Recovery ramp.** The two constants (6 steps minimum, 0.5 C per step) are
design choices. Before this change such a run was infeasible and published
nothing, so no working configuration changes. They are module-level constants
(`SHARED_TANK_START_RECOVERY_STEPS`, `SHARED_TANK_START_RECOVERY_RATE`).

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
- The relaxed fallback now restores the transfer variables, so a reused
  problem does not publish a frozen pump schedule after one rescue.
- A lag at the end of the horizon no longer crashes the build.
- A `null` in `min_temperatures` means "no bound at this step" instead of
  becoming `nan`.

### Documentation

- `heat_topology.md`: building-zone storage (fields, example, equivalence to
  `thermal_battery` / `thermal_config`); tank-to-tank transfers; the recovery
  ramp; where a transfer-only storage's temperature and the `P_transfer_*`
  columns appear; the shared-ID rule.
- `plan_output_schema.md`: the `P_transfer_{from}_{to}` columns.

### Users without temperature management

Unchanged. A/B against master with six non-thermal configurations (defaults,
battery, semi-continuous loads with min on/off time, three loads with short
per-load arrays, `def_current_power`, single-constant loads): the result
DataFrames are byte-identical.

### Verification

- Every commit with tests: red on the base, green with the change.
- Full suite: 1309 passed, 1 skipped, 32 xfailed. Two tests that fetch live open-meteo data failed in a sandbox without network; they fail identically on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QGQMaX47ARAZFK2bVCiJwC
