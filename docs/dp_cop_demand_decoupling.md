# DP COP refinement: decoupling the demand from the first solve

Status: **implemented** on this branch. Kept as a design record.

Implementing it surfaced a SECOND, independent bug that also kept the DP from
engaging: the coupled-store transfer-feasibility check (`thermal_dp.py`) bounded the
transfer at `coupling_coeff * (T_from - T_to)` without clamping at 0. When the feeder
starts COLDER than the coupled store (the buffer below the pool's temperature), that
bound is negative, so even "transfer nothing" (`qxf = 0`) is rejected and every such
state is spuriously infeasible. Fixed by clamping the bound at 0 (heat cannot flow
uphill, but coasting is always legal). With both fixes the DP engages on the real
topology and prices the COP instead of falling back to the cap.

## Problem

`Optimization._refine_cop_with_dp` takes its per-step demand for a heat-pump tank from
the **first** (static-COP) MILP solve. That solve uses an optimistic static COP
(computed at the heating-curve supply temperature, so it does not penalise driving the
tank above that supply), so it **over-banks** the buffer toward its ceiling.

The buffer feeds downstream stores through tank-to-tank transfers. Only the largest
downstream store is modelled as a *coupled DP state*; every other downstream store
becomes a **fixed demand** term, taken from the realised transfer in the first solve.
That realised transfer is `conductance x (T_buffer - T_receiver)`, so it scales with the
**banked** buffer temperature - it is inflated by the very over-banking the DP exists to
correct. On the real topology the inflated buffer->house transfer (~0.7 x (65 - 20) ~=
31 kW, capped 20 kW) exceeds the HP+boiler deliverable at the hot steps, the DP flags
itself infeasible, and skips refinement (falling back to the conservative cap). The DP's
input is poisoned by the solve it is meant to correct.

## Fix: substitute the receiver's true need for the inflated transfer

In the demand-assembly block of `_refine_cop_with_dp`, for each **non-coupled** outgoing
transfer, replace the realised transfer with the receiver's own heat need, which is
independent of the buffer temperature:

```
substituted = max(0, loss_coef * (desired - outdoor) - solar_gain + draw_off)
```

Use `desired` (not `min`) as the comfort temperature: this slightly **overstates** the
need, so the DP keeps the buffer warm enough to coast the receiver through its comfort
band - the conservative direction, never under-serving.

### Guard 1 - avoid double-counting (correctness)

`ext = heating_demand - xfer_net` already folds in `+q_transfer*dt` (xfer_net is negative
for outflows). The substitution must therefore **back out `q_transfer*dt` first, then add
the substituted demand** - a clean *swap*, not an addition. Adding without backing out
double-counts the receiver and the DP can stay infeasible.

### Guard 2 - protect the lower bound (safety)

The conservative cap protects the **upper** bound (no over-banking) but not the lower. If
the substituted demand **under**-estimates (a large, wide-band receiver with a demand
spike), the DP under-schedules, the peak cap it hands the re-solve is too tight, the
re-solve goes infeasible and is **rejected** - reverting to the **over-banked first
solve**, which is worse than the cap. Close this by routing the re-solve-rejection
fall-back to the **conservative cap** instead of the first solve, so the worst case is
always "capped at the static-COP-valid temperature", never "reverted to the banked
temperature".

## Out of scope (separate feature)

For a **high-mass, wide-band** non-coupled receiver where banking heat into it is
genuinely economic, the loss approximation is wrong: that store's transfer is a real
decision, not steady-state comfort maintenance. The correct answer there is to model the
transfer as a decision variable in the **main MILP** (the DP is structurally limited to a
single coupled state, so adding more coupled states would need to restructure
`thermal_dp.py` and would blow up the coupled-state grid). Not this fix.

## Validation bar

- The DP **engages** on the real topology (no "cannot refine" log line).
- Existing DP tests stay green: `test_dp_cop_refinement_curbs_over_superheating`,
  `test_dp_cop_refinement_couples_to_pool`,
  `test_dp_cop_refinement_engages_on_drainable_coupled_pool`.
- Add a test reproducing the real topology shape (a non-coupled receiver fed by a buffer
  that the first solve banks hot) and assert the DP refines rather than skip-caps.
- The conservative skip-cap remains as the safety net for genuine infeasibility.
- `thermal_dp.py` stays untouched; the change is confined to the demand-assembly block
  plus a per-tank metadata lookup populated at constraint-build time.

## Provenance

Root cause and design from a Claude/Codex debate on this branch. Codex independently
confirmed the root cause with line evidence and surfaced both guards (the double-count and
the under-scheduling fall-back).
