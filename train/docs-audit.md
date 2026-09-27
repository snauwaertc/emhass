# Documentation audit per PR (upstream integration train)

Audited against the fork tip `feature/hp-thermal-cap` (docs diff vs upstream
master: 10 files, +766/-283, of which `heat_topology.md` +737 lines rewritten).
The rule for every PR: the docs that describe a feature ship in the same PR as
the feature, and every PR states that setups without thermal loads are
unaffected (verified A/B, as in PR 1).

| PR | Feature | Docs on the tip | Gap to close before opening |
|---|---|---|---|
| 1 | Bugfixes on existing code | done on the PR 1 branch | none |
| 1b | `Optimal_Inaccurate` reported as ok on last-run and /plan | done on `pr/01b-relaxed-fallback-statuses` (`publish_data.md` explains every `optim_status` value) | none |
| 1c | Relaxed fallback: mutual exclusion, incumbent acceptance, `Optimal (Relaxed)` reporting | n/a | waits for the maintainer's answer on the relaxed-fallback issue; `6a5a5d4f` fixes a fork-only bug (introduced by `f5674f82`) and must not go upstream |
| 2 | Shared-tank extensions: per-source `max_supply_temperature`, soft comfort + additive demand, zone tanks (`thermal_mass`, `loss_coefficient`), runtime `shared_thermal_tanks` / `shared_tank_start_temperatures`, `extend_deferrable_loads`, per-source startup controls, config-page textarea | `heat_topology.md`, `passing_data.md`, `section_thermal.md` | the rewrite of `heat_topology.md` must be split so each PR carries only its own sections; keep upstream's "Publishing results" and troubleshooting sections (PR 1) when merging |
| 3 | Tank-to-tank transfers | `advanced_math_model.md`, `section_thermal.md` only | user-level reference in `heat_topology.md` (schema, units, example, what "no uphill transfer" means) |
| 4 | Cooling (`sense: cool`, `cooling_curve`) | `heat_topology.md` | a short cooling example (chiller + zone) and the sign convention for published power/temperature |
| 5 | `thermal_inertia` on shared tanks, `prior_heat` | `heat_topology.md` | explain how to feed `prior_heat` between MPC runs from an automation (the tip has the text; check it names the sensor/value to pass) |
| 6 | DP COP solver (`cop_solver`, opt-in) | `advanced_math_model.md`, `advanced_solvers.md`, `heat_topology.md`, `section_thermal.md` | `cop_hx_approach` is in `param_definitions.json` but documented nowhere; add a "when to turn this on" paragraph for users (default `static` = no change) |
| 7 | `max_thermal_power` + semi-continuous fixes | `heat_topology.md` | none beyond the min_power / max_thermal_power collision warning already documented |
| 8 | Stress-test fixes | n/a | per fix, same rule as PR 1 |
| 9 | Dayahead honours `current_period_peak` | `config.md`, `passing_data.md`, `cookbook/tariff_demand_charge.md` | cookbook step 3 says "(MPC)"; update it for dayahead once the maintainer agrees |
| 10 | Dead-zone fix (#1136) | n/a | depends on the answer on #1136 |

## Onboarding gaps across the whole train

1. **No walkthrough for heat_topology.** Upstream has
   `study_cases/heat_pump_walkthrough.md` and `dhw_walkthrough.md`, but no
   study case takes a new user from "I have a heat pump, a buffer and a gas
   boiler" to a working config and published sensors. Proposal: add
   `study_cases/hybrid_heating_walkthrough.md` with PR 2 (the first PR where
   the full hybrid use case works), using the worked example that is already
   in `heat_topology.md`.
2. **No "do I need this?" entry point.** `section_thermal.md` on the tip
   explains the three ways to configure heat. Add one line at the top: users
   without a heat pump, boiler or tank need none of it, and leaving
   `heat_topology` at `null` keeps the optimisation unchanged.
3. **No migration note** from `thermal_battery` to `heat_topology` for users
   who start simple and grow into a hybrid system.
