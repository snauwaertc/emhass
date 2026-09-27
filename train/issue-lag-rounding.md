**Title:** thermal_inertia: truncate or round the lag to whole timesteps?

**Describe the bug**
Not a bug yet, a convention question before it becomes one.

`_add_thermal_load_constraints` turns `thermal_inertia` (hours) into a lag of
`int(thermal_inertia / time_step)` timesteps, so the value is truncated. For a
ratio with a fractional part, the lag is shorter than configured: `0.75` h at a
30-minute step is 1.5 steps and becomes a 1-step lag, so heat reaches the
modelled temperature one step earlier than the user asked for.

I am preparing a PR that adds `thermal_inertia` to shared thermal tanks
(heat_topology storage). That implementation rounds to the nearest step, so
`0.75` h would be a 2-step lag there. The same config value would then mean two
different models depending on whether the load is a `thermal_config` or a
shared-tank member. I would like both paths to use one convention before that
lands.

**To Reproduce**
1. Configure a `thermal_config` load with `"thermal_inertia": 0.75` and the
   default 30-minute `optimization_time_step`.
2. Set a `min_temperatures` floor at index 2 that can only be met by heat
   applied at t=0.
3. With truncation (lag 1), heat applied at t=0 already reaches index 2 and the
   plan is Optimal. With rounding (lag 2), index 2 is still inside the dead
   zone, so the floor is unreachable and the plan is Infeasible.

**Expected behavior**
One documented convention for both paths. The options:

- **Round to nearest** (my preference): the lag is the closest whole-step
  approximation of what the user configured. It changes plans only for
  ratios with a fractional part >= 0.5 (e.g. 0.75 h or 1.25 h at a 30-minute
  step). Exact multiples, like every value in the docs and tests (1.0 h at
  30 min), are unaffected.
- **Truncate** (current per-load behaviour): no change for existing users;
  the shared-tank path would truncate too.

Either way, the docs (`thermal_model.md`) would state the rule explicitly.
The crash for a lag at or beyond the horizon is fixed separately in
<link to PR 1> and does not depend on this choice.

**Screenshots**
n/a

**Home Assistant installation type**
 - Home Assistant OS

**Your hardware**
- OS: HA OS
- Architecture: aarch64 (Raspberry Pi)

**EMHASS installation type**
 - Add-on

**Additional context**
Found while aligning the per-load and shared-tank thermal models for #539.
Happy to implement whichever convention you prefer, with a regression test
and the docs update.
