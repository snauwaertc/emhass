## feat: cap a heat pump's delivered heat with max_thermal_power (#539)

A heat pump's delivered heat is `COP * electrical power`. With a
weather-compensated `heating_curve` the COP climbs steeply on mild days, so a
small unit can be modelled as delivering far more heat than it physically can
(a 5.7 kW-electrical heat pump at COP 8 "delivers" about 46 kW against a rated
15 kW). `nominal_power` bounds electrical input, not thermal output. This PR
adds an optional per-source `max_thermal_power` that caps the delivered heat.
Stacked on <link to PR 5>; the diff below is only this PR's.

### What it adds

- Source field `max_thermal_power` (W, scalar), compiled through
  `heat_topology` into the source's `thermal_source` block. Omitted means
  uncapped (unchanged).
- The LP constrains `COP * p <= max_thermal_power`; the DP COP refinement
  honours the same cap.
- **Semi-continuous sources.** EMHASS's semi-continuous convention is
  `p == nominal * bin`, so a binding cap made OFF the only feasible state and
  the solver returned an "Optimal" plan that abandoned the heat pump (objective
  about 50x worse than the feasible plan). The ON level is now a per-step
  Parameter, `min(nominal, max_thermal_power / COP)` for a capped source and
  exactly `nominal` otherwise. Parameter * binary stays DPP-affine, and for
  every uncapped load it is a no-op.
- The ON-level registry is restored after a relaxed rescue, so a reused
  problem keeps it.
- **Warnings instead of silent abandonment.** Where `COP * min_power` exceeds
  the cap, `p >= min_power * bin` and the lowered ON level cannot both hold, so
  the source is off at those steps. The solve still succeeds, and a warning now
  names the source and the number of affected steps, both in the build and
  where the DP re-derives the ON level.

### Documentation

- `heat_topology.md`: the `max_thermal_power` field and a
  **Per-source thermal-output ceiling** section (why, example, ON-level
  semantics, the `min_power` collision warning).

### Users without temperature management

Unchanged. The ON-level Parameter equals `nominal_power` for every load
without `max_thermal_power`. A/B against master with six non-thermal
configurations, including semi-continuous loads with min on/off time:
byte-identical result DataFrames.

### Verification

- Every commit with tests: red on the base, green with the change.
- Full suite: 1353 passed, 1 skipped, 32 xfailed. Two tests that fetch live
  open-meteo data failed in a sandbox without network; they fail identically
  on the base there.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QGQMaX47ARAZFK2bVCiJwC
