## docs: thermal onboarding - which model to use, moving to heat_topology, a hybrid walkthrough

The thermal features now span three configuration styles (`thermal_config`,
`thermal_battery`, `heat_topology`) and several optional fields. This PR adds
the entry points a new user needs, and nothing else.
Stacked on <link to PR 7> (it documents features from PRs 2-7).

### What it adds

- **`section_thermal.md`** (the Thermal Integration landing page):
  - a short introduction;
  - **Do I need this?** Only for something that makes heat or cold; nothing
    thermal is active by default, so PV/battery-only setups can skip the
    section;
  - **Which model to use**: a table from "your system" to `thermal_config`,
    `thermal_battery` or `heat_topology`, each with a starting page;
  - **Moving from `thermal_battery` to `heat_topology`**: a field-by-field
    mapping (including fields with no equivalent), and the load count and
    per-load arrays to adjust;
  - a pointer to the optional COP refinement.
- **`study_cases/hybrid_heating_walkthrough.md`**: heat pump + gas boiler, DHW
  tank + buffer feeding the house through a tank-to-tank transfer, with a
  mutual-exclusion group. It covers the topology (in Python notation, with the
  conversion to JSON for the configuration page), the load and column
  numbering, a rolling MPC call, the default sensors and what each one drives,
  how a consumer profile aligns with the horizon, which `costfun` prices the gas
  track, what to expect, and troubleshooting. Linked from the study-case index.
- **`heat_topology.md`**: clarifies that a transfer-only storage's temperature
  and the `P_transfer_*` columns are in the plan but not published as sensors.

### The example is tested

`test_hybrid_heating_walkthrough_example_solves` compiles and solves exactly the
walkthrough's configuration through `treat_runtimeparams`, checks the documented
load and column numbering, the house comfort band, and that the heat pump never
serves both targets at once. If the example stops working, CI says so.

### Users without temperature management

Docs and one test only; no code changes.

### Verification

- The new test passes (the example solves Optimal in about a second).
- Sphinx build: no warnings on the changed pages; the new anchors resolve.
- Full suite: 1361 passed, 1 skipped, 32 xfailed. Two tests that fetch live
  open-meteo data failed in a sandbox without network; they fail identically
  on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
