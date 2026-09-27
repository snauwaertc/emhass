## fix: last-run/plan status for Optimal_Inaccurate runs, and publish-data robustness

Two small, independent fixes outside the optimizer. Each has a regression test that fails on master and passes with the fix.

### 1. Optimal_Inaccurate is a healthy run

When CVXPY returns `optimal_inaccurate`, the optimizer already accepts the
solution and publishes it to the sensors like an optimal one, with
`optim_status` `"Optimal_Inaccurate"`. But `last_run` only mapped the literal
`"Optimal"` to `ok`, so:

- `/api/v1/last-run` reported the run as `error`, and health checks built on it
  flagged a healthy run; and
- the `/api/v1/plan` gate, which mirrors the same criterion, kept serving the
  previous plan, so the endpoint disagreed with the sensors.

#### Change

- `last_run.OK_OPTIM_STATUSES = {"Optimal", "Optimal_Inaccurate"}`, used by
  both `last_run.record` and the plan gate in `_record_optim_snapshot`, so
  "plan published iff last-run is ok" still holds.
- `"Optimal (Relaxed)"` deliberately stays `error`. Whether a plan without the
  binary constraints counts as healthy is a separate question, raised in
  <link to issue>; a test pins the current behaviour.
- `publish_data.md`: the `optim_status` row said "Optimal or Infeasible". It
  now explains each value (`Optimal`, `Optimal_Inaccurate`,
  `Optimal (Relaxed)`, `Infeasible`), what it means for the plan, and how
  last-run and `/api/v1/plan` report it.

### 2. publish-data skips atomic-write temp files

`retrieve_hass.post_data` writes each entity via `<name>.json.<pid>.<uuid>.tmp`
followed by `os.replace`. The continual-publish loop already skips those temp
files, but `_publish_from_saved_entities` (publish-data) did not: a stray temp
file, left behind by a crash or seen mid-write, derived a bogus entity_id,
raised a `KeyError` on the metadata lookup, and aborted the whole publish
instead of skipping that one file. It now skips them the same way.

### Scope

No schema change: last-run still uses `ok` / `infeasible` / `error`. The
optimizer itself is not touched, so no plan changes for any configuration,
with or without thermal loads.

### Verification

- The three regression tests (last-run mapping, plan gate, temp-file skip)
  fail on master and pass with the fix.
- Full suite: 1231 passed, 1 skipped, 34 xfailed. Six tests failed in a sandbox without network and with this machine's Solcast day counter exhausted: three fetch live open-meteo data, three hit the machine-global Solcast quota counter. All six fail identically on master there, none touches this change, and PR <link to PR 1> fixes the three Solcast tests and one of the open-meteo ones.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QGQMaX47ARAZFK2bVCiJwC
