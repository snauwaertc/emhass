"""Tests for the DP thermal solver (src/emhass/thermal_dp.py)."""

import numpy as np

from emhass.thermal_dp import ThermalDPParams, solve_thermal_dp


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
        coupled_heat_capacity=163.0, coupled_min_temp=26.0, coupled_max_temp=30.0,
        demand_kw=2.0, heat_capacity=1.163,
    )
    mild = _spread_price(cheap=0.08, dear=0.22)  # 0.22/COP(~4.7) = 0.047 << gas 0.105
    res = solve_thermal_dp(mild, outdoor_temperature=8.0, params=params)
    backup_kwh = float(np.sum(res.backup_input_per_step) * 0.5)
    hp_kwh = float(np.sum(res.hp_electric_per_step) * 0.5)
    assert backup_kwh < 0.10 * hp_kwh  # backup is negligible when the HP clearly wins


def test_dp_solves_quickly():
    """The 2-state DP must be fast enough to live inside the optimisation loop."""
    params = ThermalDPParams(coupled_heat_capacity=163.0, coupled_min_temp=26.0,
                             coupled_max_temp=30.0, demand_kw=2.0)
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
        heat_capacity=2.0, loss_coeff=0.0, min_temp=44.0, max_temp=60.0,
        hp_max_power=3.0, backup_max_power=0.0, demand_kw=2.0,
    )
    per_step = solve_thermal_dp(price, warm_then_cold, params, tank_start=45.0)
    mean_run = solve_thermal_dp(price, float(np.mean(warm_then_cold)), params, tank_start=45.0)

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
        coupled_min_temp=0.0, coupled_max_temp=100.0,  # 1001 states at the raw 0.1 step
        coupled_grid_step=0.1,
        demand_kw=2.0,
    )
    res = solve_thermal_dp(_spread_price(), outdoor_temperature=8.0, params=params)
    assert res.meta["coupled_states"] <= 64  # MAX_COUPLED_STATES
    assert res.solve_seconds < 10.0
    assert res.coupled_trajectory is not None
