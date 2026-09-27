## feat: opt-in dynamic-programming COP refinement for heat pumps, heating and cooling (#539)

A heat pump's COP falls as it pushes the store hotter, so "deliver heat Q" is a
non-convex decision the MILP cannot represent: it plans against a COP
linearized at an assumed temperature. When super-heating is profitable, for
example to bank surplus PV into a buffer, the MILP super-heats at an
optimistic COP the real condenser cannot achieve. This PR adds an exact
dynamic-programming (DP) refinement that checks the plan against the true
temperature-dependent COP and, only when they disagree, re-solves with the
corrected COP and a ceiling at the DP-optimal peak.

**It is off by default.** `cop_solver` defaults to `static`, which keeps the
current behaviour exactly and never re-solves. `auto` engages the DP only when
the static solve is COP-inconsistent; `dp` always runs it.
Stacked on <link to PR 4>; the diff below is only this PR's.

### What it adds

- `src/emhass/thermal_dp.py`: a generic DP solver for one heat-pump store,
  optionally with a coupled second store (e.g. buffer + pool), with per-step
  COP (`COP[t, T]`), a marginal price that drops to the export price during PV
  surplus, a bounded state count, and a cooling mode.
- `Optimization._refine_cop_with_dp`: consistency check, DP, and a
  warm-started re-solve with half the time budget. A re-solve that the main
  path's own acceptance rule would reject keeps the static plan. The refined
  problem is handed to the result extraction without replacing the cached
  problem (#1048), and the DP registry is restored after a relaxed rescue.
- Cooling: a heat-pump source with a `cooling_curve` feeding a `cool` storage
  compiles through `heat_topology`, and the DP refines it in cooling mode.
- Parameters (four-step workflow: `associations.csv`, `config_defaults.json`,
  `param_definitions.json`, part of the cache key's structural hash):
  `cop_solver` (`static` | `auto` | `dp`, default `static`),
  `cop_solver_tolerance` (default `0.5`), `cop_hx_approach` (default `5` C).

### One shared acceptance rule

The main solve and the DP re-solve now decide "usable or not" with one
predicate, `_needs_relaxed_retry` (infeasible, unbounded, time-limited, no
status, or no value). The main path's behaviour is unchanged: it calls the
predicate instead of an inline list.

### Documentation

- `heat_topology.md`: `cooling_curve`; which sources the DP refines, and when
  to turn it on.
- `advanced_math_model.md`: a **Thermal storage and heat pumps** section (store
  dynamics, non-electric sources, why the COP is non-convex, the DP
  refinement, cooling, the `cop_solver` settings) and a section on the MIP gap
  for long or complex problems.
- `advanced_solvers.md` and `config.md`: `cop_solver`,
  `cop_solver_tolerance`, `cop_hx_approach`.

### Users without temperature management

Unchanged. The refinement only looks at shared-tank heat pumps, and the
default `static` never runs it. A/B against master with six non-thermal
configurations: byte-identical result DataFrames.

### Verification

- Every commit with tests: red on the base, green with the change (the DP
  module's own tests are new code).
- Full suite: 1344 passed, 1 skipped, 32 xfailed. Two tests that fetch live open-meteo data failed in a sandbox without network; they fail identically on the base there. Sphinx build: no warnings on the changed pages.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QGQMaX47ARAZFK2bVCiJwC
