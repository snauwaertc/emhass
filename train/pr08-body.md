## fix: honour current_period_peak in dayahead-optim, not only in MPC

> A design question as much as a fix: `current_period_peak` was deliberately
> wired for `naive-mpc-optim` only. This PR proposes to accept it in
> `dayahead-optim` too; happy to close it if MPC-only is intended.

With a capacity or demand charge (`capacity_cost_per_kw > 0`), the planned
import peak is priced. `current_period_peak` floors that peak at the billed
peak already incurred this billing period, so importing up to it is free and
only new peaks above it cost money. `dayahead-optim` dropped the value
(`treat_runtimeparams`' non-MPC branch set it to `None`), so a day-ahead plan
treated the incurred peak as 0 and minimised the absolute import peak: a flat
grid, at the expense of price arbitrage underneath a peak that is already paid
for. A household that runs a day-ahead plan with a dynamic tariff and a monthly
capacity tariff gets a worse plan than the MPC path would give.

### Change

- `treat_runtimeparams` keeps `current_period_peak` for the non-MPC actions.
- `dayahead_forecast_optim` passes it to
  `perform_dayahead_forecast_optim`, which forwards it to the solver exactly as
  the MPC path does.
- Nothing changes when `current_period_peak` is not sent (it stays `None`), or
  when no capacity charge is configured. The other capacity runtime inputs
  (`capacity_charge_window`, `capacity_charge_consideration`,
  `capacity_charge_current_interval_history`) stay MPC-only.

Independent of the other PRs in this series; based on master.

### Documentation

- `passing_data.md`: `current_period_peak` is used by `naive-mpc-optim` and
  `dayahead-optim`.
- `cookbook/tariff_demand_charge.md`: Step 3 applies to day-ahead as well; the
  notes list which inputs stay MPC-only.

### Users without temperature management

This PR is not thermal. Without `current_period_peak` in the call, plans are
unchanged: A/B against master with six configurations (defaults, battery,
semi-continuous loads, three loads, `def_current_power`, single-constant
loads) gives byte-identical result DataFrames.

### Verification

- Regression test: the day-ahead solve floors the peak at
  `current_period_peak`; it fails on master.
- Full suite: 1228 passed, 1 skipped, 34 xfailed. Six tests failed in a sandbox
  without network and with that machine's Solcast day counter exhausted; they
  fail identically on master there (three open-meteo, three Solcast; the
  Solcast ones are fixed by <link to PR 1>).
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QGQMaX47ARAZFK2bVCiJwC
