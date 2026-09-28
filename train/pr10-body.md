## docs: thermal onboarding - which model to use, moving to heat_topology, a hybrid walkthrough

The thermal features now span three configuration styles (`thermal_config`,
`thermal_battery`, `heat_topology`) and several optional fields. This PR adds
the entry points a new user needs, and nothing else.
Stacked on <link to PR 7>. It documents `heat_topology`, `max_thermal_power`,
`prior_heat` and `cop_solver` from the PRs it is stacked on.

### What it adds

- **`section_thermal.md`** (the Thermal Integration landing page):
  - a short introduction;
  - **Do I need this?** Only for something that makes heat or cold; nothing
    thermal is active by default, so PV/battery-only setups can skip the
    section;
  - **Which model to use**: a table from "your system" to `thermal_config`,
    `thermal_battery` or `heat_topology`, each with a starting page;
  - **Moving from `thermal_battery` to `heat_topology`**: a field-by-field
    mapping, including the per-load settings that become source fields
    (`treat_as_semi_cont` defaults to `true`), the different `density` /
    `heat_capacity` defaults (concrete vs water, about 2x), the fields with no
    equivalent, and the load count and per-load arrays to adjust;
  - a pointer to the optional COP refinement and which heat pumps it applies to.
- **`study_cases/hybrid_heating_walkthrough.md`**: a heat pump in two supply
  modes (two sources in one mutual-exclusion group, so DHW heat is priced at the
  55 C DHW supply, not the space-heating curve) + gas boiler, DHW tank + buffer
  feeding the house through a tank-to-tank transfer. It covers the topology (in Python notation, with the
  conversion to JSON for the configuration page), the load and column
  numbering, a rolling MPC call, the default sensors and what each one drives,
  how a consumer profile aligns with the horizon, which `costfun` prices the gas
  track, what to expect, and troubleshooting. Linked from the study-case index.
- **`heat_topology.md`**: clarifies that a transfer-only storage's temperature
  and the `P_transfer_*` columns are in the plan but not published as sensors.

### The example is tested

`test_hybrid_heating_walkthrough_example_solves` executes the Python block of the
walkthrough page itself, compiles and solves it through `treat_runtimeparams`,
and checks the documented load and column numbering (including load 2
publishing the DHW temperature again), the house comfort band, and that the
heat pump never serves both targets at once. If the example on the page stops
working, CI says so.

### Users without temperature management

Docs and one test only; no code changes.

### Verification

- The new test passes (the example solves Optimal in about a second).
- Sphinx build: no warnings on the changed pages; the new anchors resolve.
- Full suite: 1395 passed, 1 skipped, 32 xfailed. Two tests that fetch live
  open-meteo data failed in a sandbox without network; they fail identically
  on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
