## feat: opt-in dynamic-programming COP refinement for heat pumps, heating and cooling (#539)

A heat pump's COP falls as it pushes the store hotter, so "deliver heat Q" is a
non-convex decision the MILP cannot represent: it plans against a COP
linearized at an assumed temperature. When super-heating is profitable, for
example to bank surplus PV into a buffer, the MILP super-heats at an
optimistic COP the real condenser cannot achieve. This PR adds an exact
dynamic-programming (DP) refinement that checks the plan against the true
temperature-dependent COP and, only when they disagree, re-solves with the
corrected COP and a per-step temperature ceiling at the DP's trajectory.

**It is off by default.** `cop_solver` defaults to `static`, which never runs
the DP or re-solves. `auto` engages the DP only when the static solve is
COP-inconsistent; `dp` always runs it. An unknown value warns and falls back to
`static`.
Stacked on <link to PR 4>; the diff below is only this PR's.

### What it adds

- `src/emhass/thermal_dp.py`: a generic DP solver for one heat-pump store,
  optionally with a coupled second store (e.g. buffer + pool), with per-step
  COP (`COP[t, T]`), a marginal price that drops to the export price during PV
  surplus, the heat pump's `max_supply_temperature` (above it only a backup adds
  heat), a bounded state count, and a cooling mode.
- `Optimization._refine_cop_with_dp`: consistency check, DP, and a re-solve
  with half of the solver's time limit (HiGHS, Gurobi or CPLEX), bounded to 1 C
  above the DP's peak (not per step: see the limits below). The DP prices the
  tank's own `desired_temperatures` shortfall (`penalty_factor` per degree)
  like the solve does. It does not run when the static solve failed. A re-solve that the main
  path's own acceptance rule would reject keeps the static plan. The refined
  problem is handed to the result extraction without replacing the cached
  problem (#1048), and the DP registry is restored after a relaxed rescue.
- Cooling: a heat-pump source with a `cooling_curve` feeding a `cool` storage
  compiles through `heat_topology`, and the DP refines it in cooling mode. A
  cooling source configured with `heating_curve` (the only curve key before)
  keeps working.
- Parameters (four-step workflow: `associations.csv`, `config_defaults.json`,
  `param_definitions.json`, part of the cache key's structural hash):
  `cop_solver` (`static` | `auto` | `dp`, default `static`),
  `cop_solver_tolerance` (default `0.5`), `cop_hx_approach` (default `5` C).

### One shared acceptance rule

The main solve and the DP re-solve now decide "usable or not" with one
predicate, `_needs_relaxed_retry` (infeasible, unbounded, time-limited, no
status, or no value). The main path's behaviour is unchanged: it calls the
predicate instead of an inline list.

### What `static` changes, and known limits

- With `static`, the problem is exactly the one built without this feature:
  the heat pump's COP is only held as a `cp.Parameter` when the refinement can
  run.
- The DP models the tank with one minimum and maximum over the horizon and
  without `thermal_inertia`, and it does not see a coupled store's comfort
  target; the re-solve enforces all of them. If demand outruns the DP's estimate,
  the ceiling makes the re-solve infeasible and the static plan is kept.
- **The refined plan is not always cheaper.** The DP optimises a simplified
  model: one tank, at most one coupled store, other receivers as a fixed
  demand. A shadow run of a hybrid system (heat pump + gas boiler, DHW tank,
  buffer feeding a pool and a house), re-costed with the COP at the
  temperatures each plan reaches, cost 5.12 with `static` and 5.55 with `auto`
  (the DP keeps the buffer hotter, where the heat pump delivers less, and the
  boiler tops up). The docs recommend comparing both; `static` stays the
  default.
- The re-solve bound is a trade-off. A bound per step at the DP's trajectory
  keeps the COP exact but starved a house fed through a gradient-limited
  transfer (it stayed below its target for hours; a regression test covers
  this). The bound at the DP's peak keeps the house as warm as `static`, but a
  step the re-solve takes hotter than the DP priced keeps an optimistic COP
  (up to 2.25 in the shadow run). Iterating the COP towards the reached
  temperatures was tried: it made the plan consistent but costlier (6.80).
- The DP's runtime is not bound by the solver time limit: about 14 s for a
  buffer + pool over 96 steps on x86 at the default grid, about 60 s with the
  tank grid at its 200-state cap (the coupled grid is capped at 64).
- A coupled store's own draw-off or pool demand is not passed to the DP; only
  its loss coefficient is. A non-coupled receiver without `loss_coefficient`
  (e.g. a hot-water tank) passes its realised transfer.
- Design question: the consistency check uses the absolute COP difference, so
  it also engages when the tank sits below the curve and the refined COP is
  higher than the static one.

### Commits

1. The DP solver module (`thermal_dp.py`, heating and cooling) and its tests.
2. The optimizer wiring, cooling compile and the three parameters.
3. Docs.

### Documentation

- `heat_topology.md`: `cooling_curve`; which sources the DP refines, and when
  to turn it on.
- `advanced_math_model.md`: a **Thermal storage and heat pumps** section (store
  dynamics, non-electric sources, why the COP is non-convex, the DP
  refinement, cooling, the `cop_solver` settings) and a section on the MIP gap
  for long or complex problems (that section is general and can move to its own
  PR if preferred).
- `advanced_solvers.md` and `config.md`: `cop_solver`,
  `cop_solver_tolerance`, `cop_hx_approach`.

### Users without temperature management

Unchanged. The refinement only looks at shared-tank heat pumps, and the
default `static` never runs it. A/B against master with six non-thermal
configurations: byte-identical result DataFrames.

### Verification

- Every regression test fails without its fix and passes with it (checked
  before the review-round fixes were squashed; the DP module's own tests are
  new code); every commit passes the full suite.
- Full suite: 1370 passed, 1 skipped, 32 xfailed. Two tests that fetch live open-meteo data failed in a sandbox without network; they fail identically on the base there. Sphinx build: no warnings on the changed pages.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
