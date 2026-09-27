# Testing the upstream train on the Pi

`pi/train-final` is PR 9 (which contains PRs 1-7 and 1b), merged with PR 10 and
PR 8. It exists only for testing on real hardware. It is not an upstream PR.

## 1. Shadow run (safe: nothing is published, nothing is controlled)

On the Pi, in the checkout you use for the fork:

```bash
git fetch origin
git switch -c pi/train-final --track origin/pi/train-final   # first time
# git switch pi/train-final && git pull                        # later updates
uv sync
.venv/bin/python scripts/shadow_run_pi.py                 # 24 h, cop_solver from config (static)
.venv/bin/python scripts/shadow_run_pi.py 48 180 auto     # 24 h, 180 s limit, DP COP refinement
EMHASS_GAS_ONLY=1 .venv/bin/python scripts/shadow_run_pi.py   # today's gas-only setup
EMHASS_DUMP_CSV=/tmp/shadow.csv .venv/bin/python scripts/shadow_run_pi.py   # full result
```

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
