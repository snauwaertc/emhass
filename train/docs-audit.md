# Documentation audit per PR (final)

Rule for every PR: the docs that describe a change ship in the same PR, and every
PR states what it means for setups without thermal loads.

| PR | Docs shipped |
|---|---|
| 1 | heat_topology: `min_power` bound, building_demand gains, **Publishing results**, outdoor temperature sources and fallback; thermal_battery: one demand model, `null` floors; thermal_model: `thermal_inertia` whole steps and horizon cap; config: min on/off padding and `null` |
| 1b | publish_data: every `optim_status` value and how last-run / plan report it |
| 2 | heat_topology: comfort columns, **Rolling MPC** (rebuilt every run), new validation messages; thermal_model: overshoot on continuous loads |
| 3 | heat_topology: per-source `max_supply_temperature`, `overshoot_temperature`, `startup_penalty`, `max_startups` (example), `supply_temperature` is not a ceiling, combi tanks, **Combining with other deferrable loads**, config text box and save-time validation; passing_data: runtime tanks and start temperatures; thermal_battery: use `max_temperatures` as the ceiling |
| 4 | heat_topology: building-zone storage (example, equivalence table), tank-to-tank transfers, start-below-floor ramp, transfer-only temperature and `P_transfer_*` columns, shared-ID rule; plan_output_schema: `P_transfer_*` |
| 5 | heat_topology: `cooling_curve`, when to use `cop_solver`; advanced_math_model: thermal storage and heat pumps, DP refinement, cooling, MIP gap; advanced_solvers and config: `cop_solver`, `cop_solver_tolerance`, `cop_hx_approach` |
| 6 | heat_topology: `max_thermal_power` (why, example, ON level, `min_power` warning) |
| 7 | heat_topology: `prior_heat` under rolling MPC and how to keep it current; thermal_model: per-load `prior_heat`; passing_data: `shared_tank_prior_heat` |
| 8 | passing_data and demand-charge cookbook: `current_period_peak` in dayahead-optim |
| 9 | publish_data: relaxed and incumbent statuses; heat_topology: mutex in the fallback; advanced_math_model and config: `lp_solver_timeout` and the incumbent |
| 10 | section_thermal: "Do I need this?", which model to use, migration from `thermal_battery`; hybrid heating walkthrough (example guarded by a test); heat_topology: what is and is not published as a sensor |

Onboarding gaps from the first audit, all closed:

1. Walkthrough for a hybrid system: PR 10.
2. A "do I need this?" entry point: PR 10 (`section_thermal.md`).
3. Migration from `thermal_battery` to `heat_topology`: PR 10.
4. `cop_hx_approach` undocumented: PR 5.
5. Tank-to-tank transfers missing from the user reference: PR 4.
6. Relaxed / incumbent statuses undocumented: PR 1b and PR 9.
7. Demand-charge cookbook said MPC only: PR 8.

Known gap, not a docs issue: a transfer-only storage's temperature and the
`P_transfer_*` columns are not published as sensors (they are in the plan). A
follow-up could add publish support for them.
