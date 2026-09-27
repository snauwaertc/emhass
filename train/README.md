# Upstream integration train for the heat_topology / thermal work

All branches live on `snauwaertc/emhass`. Nothing is opened upstream yet. Each
PR has a ready-to-paste body in this folder (`prNN-body.md`); issues have
`issue-*.md`. Replace the `<link to ...>` placeholders with real numbers once the
referenced PR or issue exists.

Every PR was checked the same way: each commit with tests is red on its base and
green with the change; the full suite passes (apart from tests that need live
open-meteo / an untouched Solcast day counter, which fail identically on master
in the sandbox); `ruff check` and `ruff format --check` are clean; and an A/B
run of six configurations without thermal loads gives byte-identical results
against master.

## Order and status

| # | Branch | Base | What | Status |
|---|---|---|---|---|
| 1 | `pr/01-thermal-bugfixes` | master | fixes to thermal / heat_topology code already on master | ready |
| 1b | `pr/01b-relaxed-fallback-statuses` | master | `Optimal_Inaccurate` reported as ok; publish-data skips temp files | ready |
| 2 | `pr/02-shared-tank-fixes` | 1 | shared-tank stale plans (#970), comfort columns, validation, solver-exception republish | ready |
| 3 | `pr/03-shared-tank-extensions` | 2 | per-source limits and overshoot, combi tanks, extend mode, runtime tanks, config text box | ready |
| 4 | `pr/04-unified-thermal-model` | 3 | building-zone storage, tank-to-tank transfers, window solar, start-below-floor ramp | ready |
| 5 | `pr/05-dp-cop-solver` | 4 | opt-in DP COP refinement, heating and cooling (`cop_solver`, default `static`) | ready |
| 6 | `pr/06-max-thermal-power` | 5 | `max_thermal_power` and the semi-continuous ON level | ready |
| 7 | `pr/07-prior-heat-dead-zone` | 6 | `prior_heat` for the thermal_inertia dead zone (#1136) | after #1136 is answered |
| 8 | `pr/08-dayahead-period-peak` | master | `current_period_peak` in dayahead-optim | design question for the maintainer |
| 9 | `pr/09-relaxed-fallback` | 7 (+1b) | keep mutex in the fallback, keep time-limited incumbents, report both as ok | after `issue-relaxed-fallback.md` is answered |
| 10 | `pr/10-thermal-onboarding-docs` | 7 | which model to use, migration guide, hybrid walkthrough (tested example) | ready once 2-7 are in |

PR 5 has 34 commits (the DP solver grew through review rounds, each with its
own regression test); it reads well commit by commit, but squash-merging it is
fine too.

Suggested sequence: open 1 and 1b together, then 2, 3, 4, 5, 6 one at a time as
each merges (they are stacked), then 10. File both issues with PR 1 so the
answers are in before 7 and 9. PR 8 is independent and can go any time.

Open a PR with (example for 1):
`https://github.com/davidusb-geek/emhass/compare/master...snauwaertc:emhass:pr/01-thermal-bugfixes?expand=1`.
For a stacked PR, open it after its base has merged, or open it against master
and note in the body that it contains the base PR's commits until that merges.

## Issues to file first

| File | About | Blocks |
|---|---|---|
| `issue-lag-rounding.md` | truncate or round `thermal_inertia` to whole steps | nothing (both paths truncate for now) |
| `issue-relaxed-fallback.md` | mutex in the fallback, incumbents, reporting relaxed runs | PR 9 |

## What stays in the fork on purpose

Compared function by function with the fork tip merged with current master,
`utils.py`, `thermal_dp.py` and `web_server.py` are identical. The remaining
differences are deliberate:

- **Lag rounding** (`_resolve_lag_steps`): the fork rounds `thermal_inertia` to
  the nearest step; the train truncates on both paths until the lag issue is
  answered.
- **Solcast counter env seam** (`_solcast_rate_limit_ok`): a fork-only test seam;
  the train isolates the tests instead.
- **Fork-internal tooling and notes**: shadow-run and DP experiment scripts, the
  internal DP design note, and the experiment results were never ported.
- **`6a5a5d4f`** fixed a bug that only existed in the fork (introduced by
  `f5674f82`); upstream never had it.
- The rest are comments and docstrings reworded for upstream, and
  `Optimal_Inaccurate` / the publish temp-file fix, which live in 1b rather than
  in the chain.

## Docs per PR

See `docs-audit.md` for the audit that drove the docs in each PR.
