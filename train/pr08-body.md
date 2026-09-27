## fix: honour current_period_peak in dayahead-optim, not only in MPC

> A design question as much as a fix: `current_period_peak` was deliberately
> wired for `naive-mpc-optim` only (see the comments in `treat_runtimeparams`).
> Consider opening an issue first; this PR proposes to accept it in
> `dayahead-optim` too, and I'm happy to close it if MPC-only is intended.

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
  `capacity_charge_current_interval_history`) stay MPC-only, and
  `perfect-optim` still ignores the value (it covers past data).
- **Plan change for existing callers:** anyone who already sends
  `current_period_peak` to `dayahead-optim` (for example from a payload shared
  with the MPC call) with a capacity charge configured now gets a plan that
  uses it. Before, the value was silently ignored.
- **Billing-period rollover:** day-ahead has no `capacity_charge_window`, so it
  cannot exclude the next billing period's steps. A plan that crosses into a new
  period must not carry the old period's peak; the docs say so. Honouring the
  window in day-ahead too would be the fuller alternative.

Independent of the other PRs in this series; based on master.

### Documentation

- `passing_data.md`: `current_period_peak` is used by `naive-mpc-optim` and
  `dayahead-optim` (section heading, parameter list, structural-vs-runtime
  note), and the rollover caveat for day-ahead.
- `runtime_params.json`: the web UI help text no longer says MPC only.
- `cookbook/tariff_demand_charge.md`: Step 3 applies to day-ahead as well; the
  notes list which inputs stay MPC-only.

### Existing setups

Without `current_period_peak` in the call, plans are unchanged: A/B against
master with six configurations (defaults, battery, semi-continuous loads,
three loads, `def_current_power`, single-constant loads) gives byte-identical
result DataFrames.

### Verification

- End-to-end regression test: `dayahead-optim` with a capacity tariff and
  `current_period_peak=8000` plans a peak of 8000 W (4500 W on master); a unit
  test checks that `treat_runtimeparams` keeps the value.
- Full suite: all tests pass except ones that need network access or a fresh
  Solcast daily quota, which fail identically on master.
- `uvx ruff check .` and `uvx ruff format --check --diff`: clean.
