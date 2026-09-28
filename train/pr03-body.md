## feat: shared-tank extensions for hybrid heating (#539)

Opt-in extensions to shared thermal tanks and `heat_topology`, driven by real
hybrid installs in #539 (heat pump + booster, heat pump + gas boiler, combi
tanks). Every new field is optional and defaults to the current behaviour.
Stacked on <link to PR 2>; the diff below is only this PR's.

### What it adds

| Feature | Field(s) | Why |
|---|---|---|
| Per-source temperature ceiling | source `max_supply_temperature` (number or per-step list) | a heat pump cannot heat a DHW tank past its condenser limit; without a ceiling the optimizer let the cheap heat pump cover the band a booster must deliver. Hard limit, kept in the relaxed fallback. |
| Warning for an uncapped fixed-supply heat pump | - | `supply_temperature` drives the COP only; the compiler now warns when nothing stops the plan from heating past it |
| Per-source overshoot | source `overshoot_temperature` | the tank-level `overshoot_temperature` switched every source off at once; a source can now have its own threshold (it inherits the storage value otherwise), e.g. heat pump stops at 55 C, element continues to 75 C, as a soft preference |
| Additive demand | - | a storage with a `profile` and a `building_demand` consumer (a combi tank) used only the draw-off profile; the two now add up, with the standing loss counted once |
| Per-source anti-short-cycling | source `startup_penalty`, `max_startups` | the compiler always overwrote these per-load arrays with zeros, so topology users could not set them |
| Ordinary loads next to a topology | topology `extend_deferrable_loads` | the compiler replaced the whole deferrable-load set; with the flag, configured loads keep indices `0..N-1` and topology loads are appended |
| Runtime tanks | runtime `shared_thermal_tanks`, `shared_tank_start_temperatures` | the manual flat alternative to `heat_topology` at runtime, and a per-run start-temperature override keyed by storage id for MPC loops |
| Config page | - | `heat_topology` is edited in a multi-line text box instead of a one-line input, and validated with the compiler on save: an invalid topology is not saved and the alert names the field |

`param_definitions.json`, `config_defaults.json` and `associations.csv` are not
changed. `runtime_params.json` gains the two runtime parameters (additive).
Existing shared-tank behaviour that changes:

- **Tank-level `overshoot_temperature`:** each source now gets its own
  indicator (so it can take a per-source threshold), and big-M is sized from
  the tank's bounds instead of a fixed 100. A semi-continuous source is still
  switched off while the tank is above the threshold at the start of a step, as
  before. A continuous source is blocked only in a step that would end above it,
  so it can heat up to the threshold and can heat from a start above it when the
  floor needs it. The upstream soft-comfort tests pass unchanged.
- **Combi tanks:** without `indoor_target_temperature`, the building demand of a
  tank that also has a draw-off profile is computed against 20 C, not the tank's
  hot-water floor.
- **Single-constant pin:** a shared-tank member is no longer pinned ON by an
  in-progress single-constant run. It is temperature-driven, and pinning a
  capped source ON while the tank starts above its ceiling contradicts the cap
  and forces the relaxed fallback.
- **Warm-start cache key:** a `thermal_source` block is now part of the key, so
  changing it rebuilds the problem. Shared tanks bypass the cache anyway (#970),
  so this only matters if that bypass is lifted later.
- **Validation:** `heat_topology` with a wrong top-level type (for example
  `"flows": "x"`) or a non-boolean `extend_deferrable_loads` is rejected with a
  field-naming `ValueError`, and a malformed entry inside a list returns the 400
  validation message (before: HTTP 500 on save, and `"false"` enabled extend
  mode).
- **Anti-cycling on continuous sources:** `startup_penalty` / `max_startups`
  only bind for semi-continuous sources or sources with `min_power`; the docs
  say so.

**Size.** This PR bundles eight features. If the maintainer prefers smaller
reviews, it splits cleanly into four: (1) `max_supply_temperature` and its
warning; (2) additive demand and per-source overshoot; (3) runtime tanks, start
temperatures and extend mode; (4) the config-page text box and save-time
validation.

### Documentation

- `heat_topology.md`: the new source fields with a heat pump + booster example;
  why `supply_temperature` is not a ceiling; why a capped source should be
  continuous; per-source overshoot as a
  two-stage preference; combi tanks (and their default indoor target); a **Combining with other deferrable
  loads** section with the renumbering warning; the config page's text box and
  save-time validation; `shared_tank_start_temperatures` for rolling MPC.
- `passing_data.md`: the two runtime parameters.
- `thermal_battery.md`: `supply_temperature` is not a ceiling; use
  `max_temperatures`.

### Users without temperature management

Unchanged. A/B against master with six non-thermal configurations (defaults,
battery, semi-continuous loads with min on/off time, three loads with short
per-load arrays, `def_current_power`, single-constant loads): the result
DataFrames are byte-identical. Nothing new is read unless a topology or shared
tank sets it.

### Verification

- Each feature commit has tests that fail on the base and pass with it. Some
  tests guard against intermediate states of this PR rather than the base
  (a semi-continuous source under an overshoot threshold, the combi-tank
  default); the two
  end-to-end tests (runtime tanks, topology next to ordinary loads) are
  integration guards.
- Existing tests: no optimization, utils, web-server or command-line test is
  changed or removed. In `test_schema_contract.py` the object-parameter
  rendering tests are updated for the text box: the `<input>` rendering test is
  replaced, and the null, apostrophe and HTML-escaping cases now assert the
  same properties on the `<textarea>`.
- Browser smoke test of the configuration page (Chromium, zero-config
  defaults): the page renders, `heat_topology` is a text box, a valid topology
  is saved to `config.json`, an invalid one is rejected with
  `heat_topology is invalid: heat_topology.flows[0].from='ghost_source' does not
  match any source.id`
  and the file is left untouched. The only console error is that expected 400.
- Full suite: 1303 passed, 1 skipped, 32 xfailed. Two tests that fetch live
  open-meteo data failed in a sandbox without network; they fail identically
  on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
