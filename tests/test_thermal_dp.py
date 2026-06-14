"""Tests for the prototype DP thermal solver (src/emhass/thermal_dp.py)."""

import numpy as np

from emhass.thermal_dp import ThermalDPParams, solve_buffer_pool_dp


def _spread_price(n=48, dt=0.5, cheap=0.05, dear=0.50, start_h=8):
    hrs = [(start_h + i * dt) % 24 for i in range(n)]
    return np.array([cheap if 8 <= h < 16 else dear for h in hrs])


def test_dp_super_heats_only_when_spread_pays():
    """No spread -> no super-heating; a big spread -> the buffer banks heat hot.
    This is the behaviour the COP fixed-point could not reliably find."""
    params = ThermalDPParams(house_demand_kw=4.0)
    flat = solve_buffer_pool_dp(np.full(48, 0.20), outdoor_temperature=8.0, params=params)
    spread = solve_buffer_pool_dp(_spread_price(), outdoor_temperature=8.0, params=params)
    assert flat.buffer_trajectory.max() < spread.buffer_trajectory.max()
    assert spread.buffer_trajectory.max() > 45.0  # genuinely super-heats on a big spread


def test_dp_prefers_heat_pump_when_genuinely_cheaper():
    """When the HP is genuinely cheaper than the backup at every step (mild prices,
    cool buffer -> COP ~5-6 -> price/COP well below the gas commodity cost), the
    global optimum uses almost no gas. This is the behaviour the limit-cycling
    fixed-point lost: it dispatched gas against a stale COP even where the HP won.
    (On a *big* night price the HP/gas cost tie and gas can be optimal for forced
    pool maintenance - the DP gets that right too; this test isolates the clear case.)"""
    params = ThermalDPParams(
        pool_heat_capacity=163.0, house_demand_kw=2.0, buffer_heat_capacity=1.163
    )
    mild = _spread_price(cheap=0.08, dear=0.22)  # 0.22/COP(~4.7) = 0.047 << gas 0.105
    res = solve_buffer_pool_dp(mild, outdoor_temperature=8.0, params=params)
    backup_kwh = float(np.sum(res.backup_input_per_step) * 0.5)
    hp_kwh = float(np.sum(res.hp_electric_per_step) * 0.5)
    assert backup_kwh < 0.10 * hp_kwh  # backup is negligible when the HP clearly wins


def test_dp_solves_quickly():
    """The 2-state DP must be fast enough to live inside the optimisation loop."""
    params = ThermalDPParams(pool_heat_capacity=163.0, house_demand_kw=2.0)
    res = solve_buffer_pool_dp(_spread_price(), outdoor_temperature=8.0, params=params)
    assert res.solve_seconds < 10.0
    assert res.pool_trajectory is not None
    assert len(res.buffer_trajectory) == 49  # N + 1
