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
The only existing behaviour that changes is the tank-level
`overshoot_temperature`: a semi-continuous source is now gated through its
on/off binary and big-M is sized from the tank's bounds instead of a fixed 100.
The upstream soft-comfort tests pass unchanged.

### Documentation

- `heat_topology.md`: the new source fields with a heat pump + booster example;
  why `supply_temperature` is not a ceiling; per-source overshoot as a
  two-stage preference; combi tanks; a **Combining with other deferrable
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

- Each feature commit has tests that fail on the base and pass with it; the two
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
  `heat_topology.flows[0].from='ghost_source' does not match any source.id`
  and the file is left untouched. The only console error is that expected 400.
- Full suite: 1293 passed, 1 skipped, 32 xfailed. Two tests that fetch live
  open-meteo data failed in a sandbox without network; they fail identically
  on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QGQMaX47ARAZFK2bVCiJwC
