# Upstream integration train for the heat_topology / thermal work

All branches live on `snauwaertc/emhass`. Nothing is opened upstream yet. Each
PR has a ready-to-paste body in this folder (`prNN-body.md`); issues have
`issue-*.md`. Replace the `<link to ...>` placeholders with real numbers once the
referenced PR or issue exists.

Every PR was reviewed independently twice; the findings and what was done
about each are in `reviews.md` (round 1) and `reviews-round2.md` (round 2). Every PR was checked the same way: each commit with tests is red on its base and
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
| 3 | `pr/03-shared-tank-extensions` | 2 | per-source limits and overshoot, combi tanks, extend mode, runtime tanks, config text box | ready (large: a 4-way split is offered in the body) |
| 4 | `pr/04-unified-thermal-model` | 3 | building-zone storage, tank-to-tank transfers, window solar, start-below-floor ramp | ready |
| 5 | `pr/05-dp-cop-solver` | 4 | opt-in DP COP refinement, heating and cooling (`cop_solver`, default `static`) | ready |
| 6 | `pr/06-max-thermal-power` | 5 | `max_thermal_power` and the semi-continuous ON level | ready |
| 7 | `pr/07-prior-heat-dead-zone` | 6 | `prior_heat` for the thermal_inertia dead zone (#1136) | after #1136 is answered |
| 8 | `pr/08-dayahead-period-peak` | master | `current_period_peak` in dayahead-optim | design question: an issue first is safer |
| 9 | `pr/09-relaxed-fallback` | 7 (+1b) | keep mutex in the fallback, keep time-limited incumbents, report both as ok | after `issue-relaxed-fallback.md` is answered |
| 10 | `pr/10-thermal-onboarding-docs` | 7 | which model to use, migration guide, hybrid walkthrough (tested example) | ready once 2-7 are in |

The review-round fix-on-fix commits of PRs 4, 5, 6 and 9 are squashed: PR 4
has 3 commits, PR 5 3, PR 6 2 and PR 9 5 (one per proposal, the PR 1b commit
and docs). Every commit passes the full suite, and each PR's final tree is unchanged.
The unsquashed history is kept on the fork as `backup/pre-squash/*` (the
whole chain from PR 4 to PR 10 and the Pi branch as they were just before
the squash). These branches are for reference only and never go upstream.

Suggested sequence: open 1 and 1b together, then 2, 3, 4, 5, 6 one at a time as
each merges (they are stacked), then 10. File both issues with PR 1 so the
answers are in before 7 and 9. PR 8 is independent and can go any time.

Open a PR with (example for 1):
`https://github.com/davidusb-geek/emhass/compare/master...snauwaertc:emhass:pr/01-thermal-bugfixes?expand=1`.
For a stacked PR, open it after its base has merged, or open it against master
and note in the body that it contains the base PR's commits until that merges.

## Testing on real hardware

`pi/train-final` merges PR 9 (which contains 1-7 and 1b), PR 10 and PR 8, plus a
shadow-run script. See `scripts/PI_TEST.md` on that branch. It is test-only and
never goes upstream.

## Issues to file first

| File | About | Blocks |
|---|---|---|
| `issue-lag-rounding.md` | truncate or round `thermal_inertia` to whole steps | nothing (both paths truncate for now) |
| `issue-relaxed-fallback.md` | mutex in the fallback, incumbents, reporting relaxed runs | PR 9 |

Reviewers also suggest an issue first (AGENTS.md: visible behaviour changes in
`optimization.py`) for PR 2's overshoot change on continuous loads, PR 3's size,
PR 4's helper extraction and PR 8's MPC-only question. Each PR body flags
these, so they can also be raised in the PR itself.

## What stays in the fork on purpose

After the first review round, the train and the fork tip merged with current
master had identical `utils.py`, `thermal_dp.py` and `web_server.py`. The fixes
from the second review round (`reviews-round2.md`) are only on these branches
and on `pi/train-final`, so the train is now ahead of the fork. Apart from
that, the differences are deliberate:

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

## Decision: the DP re-solve bound (PR 5)

A final shadow run of the real hybrid topology (heat pump + gas, DHW, buffer,
pool, house; `scripts/shadow_run_pi.py` on `pi/train-final`) compared the
options, re-costing each plan with the COP at the temperatures it reaches:

| `cop_solver` / re-solve bound | True cost | House comfort | Worst COP overstatement |
|---|---|---|---|
| `static` | 5.12 | in band | 0.96 |
| `auto`, bound per step (round 2) | 6.53 | below target for hours | 0.22 |
| `auto`, bound at the DP peak (chosen) | 5.55 | in band | 2.25 |
| `auto`, peak + 1 COP-tightening pass | 5.89 | in band | 1.52 |
| `auto`, peak + 3 COP-tightening passes | 6.80 | in band | 0.98 |

Chosen: the bound at the DP's peak, plus a fix so the DP respects a heat pump's
`max_supply_temperature` (it planned the DHW tank to 61 C against a 55 C
condenser). On this topology `static` stays cheapest, so it remains the
default and the docs recommend comparing both. Letting the refinement accept
its plan only when it is cheaper at the true COP is a possible follow-up
(issue first).
