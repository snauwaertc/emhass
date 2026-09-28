# Testing the upstream train on the Pi

`pi/train-final` is PR 9 (which contains PRs 1-7 and 1b), merged with PR 10 and
PR 8. It exists only for testing on real hardware. It is not an upstream PR.

## 1. Shadow run (safe: nothing is published, nothing is controlled)

On the Pi, in the checkout you use for the fork:

```bash
git fetch origin
git switch -c pi/train-final --track origin/pi/train-final   # first time
# later updates: the branch is rebuilt (force-pushed), so do not pull, reset:
# git switch pi/train-final && git fetch origin && git reset --hard origin/pi/train-final
uv sync
.venv/bin/python scripts/shadow_run_pi.py                 # 24 h, cop_solver from config (static)
.venv/bin/python scripts/shadow_run_pi.py 48 180 auto     # 24 h, 180 s limit, DP COP refinement
EMHASS_GAS_ONLY=1 .venv/bin/python scripts/shadow_run_pi.py   # today's gas-only setup
EMHASS_DUMP_CSV=/tmp/shadow.csv .venv/bin/python scripts/shadow_run_pi.py   # full result
.venv/bin/python scripts/shadow_run_pi.py 96                  # 48 h horizon
```

`git reset --hard` discards local changes in that checkout; keep your own
config outside it (or commit it on another branch) first.

Reference results from the sandbox (x86, same script, 24 h unless noted), to
compare with the Pi:

| Run | optim_status | HP elec | gas input | Wall time |
|---|---|---|---|---|
| `static` (default) | Optimal | 32.6 kWh | 2.4 kWh | 9 s |
| `48 180 auto` | Optimal | 28.3 kWh | 5.4 kWh | 10 s |
| `96` (48 h, static) | Optimal (Incumbent) | 56.7 kWh | 2.4 kWh | 47 s |
| `96 180 auto` (48 h) | Optimal | 49.4 kWh | 5.4 kWh | 57 s |
| `EMHASS_GAS_ONLY=1` | Optimal | - | 134.2 kWh | 7 s |

Re-costed with the COP at the temperatures each plan reaches, the 24 h plans
cost 5.12 (`static`) and 5.55 (`auto`): on this topology the DP refinement
does not pay off, so keep `cop_solver: static` and run `auto` only to compare.
Both keep the house in its band and the DHW tank at or below the heat pump's
55 C (gas covers anything above).

Arguments: `[horizon steps] [lp_solver_timeout s] [cop_solver] [mip_rel_gap]
[gas startup penalty] [gas max_startups]`.

What to look at:

- `optim_status` should be `Optimal` (or `Optimal (Incumbent)` when the time
  limit is hit with a feasible plan). A time-out without any plan must now fall
  back to the relaxed solve, never publish an all-zero plan.
- The heat pump never serves the buffer and the DHW tank in the same step
  (mutual exclusion).
- The house stays within 19-23 C and the DHW tank within 45-62 C.
- Run time on the Pi, with `static` and with `auto`.

## 2. Live run with the add-on or Docker (optional)

Build the image from this branch, or point your local install at it, and keep
your current configuration. With `heat_topology` set, check after a day:

- `publish-data` publishes one `sensor.p_deferrable{k}` per compiled load
  without passing custom ids (this used to raise IndexError);
- `/api/v1/last-run` reports `ok` and `/api/v1/plan` serves the plan;
- the logs show no warnings you did not expect.

Switch back with `git switch master` (or your usual branch).
