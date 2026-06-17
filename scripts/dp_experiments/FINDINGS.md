# DP COP refinement - genericity and safety findings

A reproducible stress-test of the post-MILP DP COP refinement
(`optimization.py::_refine_cop_with_dp` + `thermal_dp.py`): does it stay safe and
beneficial across topologies unlike the one it was built for?

## How to run

```
PYTHONPATH=. .venv/bin/python scripts/dp_experiments/harness.py --list
PYTHONPATH=. .venv/bin/python scripts/dp_experiments/harness.py <scenario>
PYTHONPATH=. EMHASS_DUMP_DIR=/tmp/x .venv/bin/python scripts/dp_experiments/harness.py <scenario>  # + per-step CSV
```

`harness.py` runs any topology through the optimiser TWICE - DP on (`cop_solver=auto`)
and off (`cop_solver=static`) - and reports per-tank trajectories, band violations,
grid peak, the DP's own log decisions, and two cost comparisons (see below).
`scenarios.py` holds the experiment matrix, each scenario targeting one limit.

## Bottom line

- **Safe everywhere.** All scenarios: feasible, `Optimal`, **zero band violations** -
  including deliberately pathological ones (0-100 C pool band, two-hop cascade,
  drain-to-floor). Outside the topology it models exactly, the DP degrades to "static
  COP + conservative cap", never to a wrong-but-Optimal plan.
- **Beneficial or neutral everywhere (when compared honestly).** Under the fair
  comparison (below): **13 HELPS, 4 neutral, 0 hurts**. The neutrals are the two no-op
  controls plus two within MIP-gap noise.

## The measurement trap (important)

`static` prices a heating-curve heat pump with an **optimistic COP** taken at the
curve supply temperature, which can sit well below the tank temperature it actually
reaches. So the static solve's reported electricity and grid peak **understate** what
executing that schedule really draws - a real controller chases the temperature
setpoints, pulling whatever electricity the true COP demands.

Comparing the DP's honest (true-COP) plan against static's optimistic self-report is
apples-to-oranges, and it **systematically under-credits the DP**. The harness now
re-costs the static schedule under the true COP before comparing:

```
true_elec = elec_static * cop_static / cop_real     # cop_real at the achieved temp
```

- `delta` (legacy): auto vs static-as-reported - kept for contrast, **do not trust**.
- `fair_delta`: both under the true COP - the trustworthy number. Skipped (with a
  recorded reason) when either run did not solve cleanly, so a timed-out `User_Limit`
  static cannot masquerade as a result.

Worked example (`lone_hp_capacity`): legacy delta said the DP HURT (+0.91 EUR, +534 W
peak); the fair comparison shows it HELPS (-1.67 EUR, peak 1517 vs static's true
1632 W). Static's reported 983 W peak was fiction - that schedule really draws 1632 W.

## Topology limits (these are real; they bound the DP's *refinement*, not the MILP)

The base MILP optimises any graph with a static COP; the DP only corrects the
temperature-dependent-COP non-convexity. Outside its sweet spot it is safe but not
COP-optimal. No topology is ever rejected.

1. **One coupled (bankable) store per HP tank** - the single largest with `hc >= 20`
   (`optimization.py:2830`); other downstream stores become fixed-demand receivers
   approximated as comfort loss. Safe, suboptimal. (`two_bankable_pools`,
   `highmass_wideband_receiver`)
2. **The `hc >= 20` kWh/K threshold** is a magic constant; a sub-20 store worth
   banking is never coupled. Safe, suboptimal. (`hc_threshold_edge_below`)
3. **One heat pump refined per tank** (`optimization.py:2546`) - a second HP on the
   same tank keeps its static COP. Safe, internally inconsistent. (untested)
4. **One-hop transfers only** (`optimization.py:2596-2604`) - a cascade's second hop
   is invisible to the DP. Safe. (`cascade_two_hop`)
5. ~~Capacity/demand-charge blind - can actively hurt.~~ **STRUCK.** Measured fairly,
   the DP HELPS under a demand tariff on both the lone-HP and 4-tank cases
   (`lone_hp_capacity`, `capacity_tariff_peak`): it is the only stage that prices the
   COP honestly, which also corrects static's blindness to its own true grid peak. The
   DP price is still energy-only, so it *may* be peak-suboptimal - but it is not
   harmful.
6. **Coupled-store discretisation** (`MAX_COUPLED_STATES=64`, `MAX_TANK_STATES=200`,
   `coupling_levels=11`) - a robustness cap, not a modelling gap. (`pathological_wide_pool`)

## Caveats

- Scenarios are synthetic; magnitudes are illustrative (some use a deliberately
  extreme COP inconsistency to force banking). The *direction* of the static-cost bias
  is structural, not scenario-specific.
- The fair cost is grid energy +/- export + capacity charge. It does not include gas
  commodity cost; for dual-fuel scenarios read the per-source energy too.
- `capacity_tariff_peak` needs a MIP gap (set in the scenario) so the static baseline
  does not time out; without it the fair comparison is correctly reported as n/a.
