"""Tests for the DP thermal solver (src/emhass/thermal_dp.py)."""

import numpy as np

from emhass.thermal_dp import (
    MAX_COUPLED_STATES,
    MAX_TANK_STATES,
    ThermalDPParams,
    solve_thermal_dp,
)


def _spread_price(n=48, dt=0.5, cheap=0.05, dear=0.50, start_h=8):
    hrs = [(start_h + i * dt) % 24 for i in range(n)]
    return np.array([cheap if 8 <= h < 16 else dear for h in hrs])


def test_dp_super_heats_only_when_spread_pays():
    """No spread -> no super-heating; a big spread -> the store banks heat hot."""
    params = ThermalDPParams(demand_kw=4.0)
    flat = solve_thermal_dp(np.full(48, 0.20), outdoor_temperature=8.0, params=params)
    spread = solve_thermal_dp(_spread_price(), outdoor_temperature=8.0, params=params)
    assert flat.tank_trajectory.max() < spread.tank_trajectory.max()
    assert spread.tank_trajectory.max() > 45.0  # genuinely super-heats on a big spread


def test_dp_prefers_heat_pump_when_genuinely_cheaper():
    """When the heat pump is genuinely cheaper than the backup at every step (mild
    prices, cool store -> COP ~5-6 -> price/COP well below the backup commodity cost),
    the global optimum uses almost no backup. (On a big night price the HP/backup
    costs tie and the backup can be optimal for forced maintenance - the DP gets that
    right too; this test isolates the clear case.)"""
    params = ThermalDPParams(
        coupled_heat_capacity=163.0,
        coupled_min_temp=26.0,
        coupled_max_temp=30.0,
        demand_kw=2.0,
        heat_capacity=1.163,
    )
    mild = _spread_price(cheap=0.08, dear=0.22)  # 0.22/COP(~4.7) = 0.047 << gas 0.105
    res = solve_thermal_dp(mild, outdoor_temperature=8.0, params=params)
    backup_kwh = float(np.sum(res.backup_input_per_step) * 0.5)
    hp_kwh = float(np.sum(res.hp_electric_per_step) * 0.5)
    assert backup_kwh < 0.10 * hp_kwh  # backup is negligible when the HP clearly wins


def test_dp_solves_quickly():
    """The 2-state DP must be fast enough to live inside the optimisation loop."""
    params = ThermalDPParams(
        coupled_heat_capacity=163.0, coupled_min_temp=26.0, coupled_max_temp=30.0, demand_kw=2.0
    )
    res = solve_thermal_dp(_spread_price(), outdoor_temperature=8.0, params=params)
    assert res.solve_seconds < 10.0
    assert res.coupled_trajectory is not None
    assert len(res.tank_trajectory) == 49  # N + 1


def test_dp_uses_per_step_outdoor_not_the_mean():
    """The COP follows the per-step outdoor temperature, not its average. With a warm
    first half (high COP) and a cold second half (low COP), the heat pump should bank
    heat early even though the price is marginally cheaper late - a schedule the
    mean-outdoor approximation (uniform COP) would not produce."""
    N = 6
    # Price marginally cheaper in the (cold) second half: a uniform-COP solver would
    # lean late; the true per-step COP makes the warm first half clearly cheaper.
    price = np.array([0.21, 0.21, 0.21, 0.20, 0.20, 0.20])
    warm_then_cold = np.array([15.0, 15.0, 15.0, -5.0, -5.0, -5.0])
    params = ThermalDPParams(
        heat_capacity=2.0,
        loss_coeff=0.0,
        min_temp=44.0,
        max_temp=60.0,
        hp_max_power=3.0,
        backup_max_power=0.0,
        demand_kw=2.0,
    )
    per_step = solve_thermal_dp(price, warm_then_cold, params, tank_start=45.0)
    mean_run = solve_thermal_dp(price, float(np.mean(warm_then_cold)), params, tank_start=45.0)
    assert len(per_step.tank_trajectory) == N + 1

    def early_share(res):
        total = res.hp_electric_per_step.sum()
        return res.hp_electric_per_step[:3].sum() / total if total > 0 else 0.0

    # The per-step run concentrates HP electricity in the warm, high-COP first half;
    # the mean-outdoor run (uniform COP, marginally cheaper late) does not.
    assert early_share(per_step) > early_share(mean_run) + 0.2


def test_dp_caps_coupled_state_count():
    """A pathologically wide coupled band must not blow up the state space: the grid
    step is coarsened so the coupled state count stays bounded (and the DP stays fast),
    while the band itself is preserved."""
    params = ThermalDPParams(
        coupled_heat_capacity=163.0,
        coupled_min_temp=0.0,
        coupled_max_temp=100.0,  # 1001 states at the raw 0.1 step
        coupled_grid_step=0.1,
        demand_kw=2.0,
    )
    res = solve_thermal_dp(_spread_price(), outdoor_temperature=8.0, params=params)
    assert res.meta["coupled_states"] <= MAX_COUPLED_STATES
    assert res.solve_seconds < 10.0
    assert res.coupled_trajectory is not None

    # Micro-span edge case: a near-degenerate band with a tiny configured step must
    # not blow up the count (an arange-with-epsilon would have produced thousands).
    micro = ThermalDPParams(
        coupled_heat_capacity=100.0,
        coupled_min_temp=26.0,
        coupled_max_temp=26.00000001,
        coupled_grid_step=1e-9,
        demand_kw=1.0,
    )
    res_micro = solve_thermal_dp(np.full(6, 0.2), outdoor_temperature=8.0, params=micro)
    assert res_micro.meta["coupled_states"] <= MAX_COUPLED_STATES


def test_dp_caps_tank_state_count():
    """A fine grid_step on a wide band must not blow up the heat-pump-store grid: it is
    coarsened to stay within MAX_TANK_STATES (bounding runtime and keeping the int16
    policy array from overflowing). The default 0.5 C step stays under the cap."""
    fine = ThermalDPParams(min_temp=25.0, max_temp=65.0, grid_step=0.1, demand_kw=2.0)
    res = solve_thermal_dp(_spread_price(), outdoor_temperature=8.0, params=fine)
    assert res.meta["tank_states"] <= MAX_TANK_STATES  # 401 raw -> capped
    # The default 0.5 C step is unchanged (well under the cap).
    default = ThermalDPParams(min_temp=25.0, max_temp=65.0, grid_step=0.5, demand_kw=2.0)
    res_def = solve_thermal_dp(_spread_price(), outdoor_temperature=8.0, params=default)
    assert res_def.meta["tank_states"] == 81


def test_dp_flags_infeasible_when_demand_exceeds_deliverable_heat():
    """A store starting at its floor (no stored heat to drain) with demand that exceeds
    what the heat pump can deliver every step and no backup has no feasible trajectory -
    the DP must flag it (meta['infeasible'], total_cost=inf) rather than return a
    plausible-looking plan that silently violates the energy balance."""
    params = ThermalDPParams(
        hp_max_power=1.0, backup_max_power=0.0, demand_kw=7.0, min_temp=30.0, max_temp=60.0
    )
    # start at the floor: cannot drain, and 3.5 kWh/step demand >> HP's ~2 kWh/step max.
    res = solve_thermal_dp(
        np.full(4, 0.2), outdoor_temperature=10.0, params=params, tank_start=30.0
    )
    assert res.meta["infeasible"] is True
    assert res.total_cost == float("inf")

    # The same store with a capable backup IS feasible (sanity: the flag is not stuck on).
    ok = ThermalDPParams(
        hp_max_power=1.0, backup_max_power=10.0, demand_kw=7.0, min_temp=30.0, max_temp=60.0
    )
    res_ok = solve_thermal_dp(np.full(4, 0.2), outdoor_temperature=10.0, params=ok, tank_start=30.0)
    assert res_ok.meta["infeasible"] is False
    assert np.isfinite(res_ok.total_cost)


def test_dp_feasible_when_feeder_colder_than_coupled_store():
    """A coupled store warmer than its feeder must NOT make the DP infeasible. Heat
    can't flow uphill into it, but transferring nothing (qxf=0) is always legal -
    the store just coasts. The conductance bound must be clamped at 0; without the
    clamp it goes negative and qxf in [0, negative] is empty, spuriously flagging
    every such state infeasible (the buffer/pool case where the buffer starts cool)."""
    params = ThermalDPParams(
        min_temp=25.0,
        max_temp=65.0,
        hp_max_power=4.0,
        backup_max_power=20.0,
        demand_kw=0.5,
        coupled_heat_capacity=100.0,
        coupled_loss_coeff=0.5,
        coupled_min_temp=15.0,
        coupled_max_temp=30.0,
        coupling_coeff=2.0,
        coupling_max_power=50.0,
    )
    # The feeder starts COLDER (25) than the coupled store (28): no uphill flow, but
    # the DP must still find the do-nothing policy rather than declaring infeasible.
    res = solve_thermal_dp(
        np.full(8, 0.2), outdoor_temperature=10.0, params=params,
        tank_start=25.0, coupled_start=28.0,
    )
    assert res.meta["infeasible"] is False
    assert np.isfinite(res.total_cost)
