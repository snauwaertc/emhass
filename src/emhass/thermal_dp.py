"""Dynamic-programming thermal solver - prototype replacement for the COP fixed-point.

Why this exists
---------------
The heat-pump COP depends on the tank temperature the HP charges to
(``COP = carnot * T_supply_K / (T_supply - T_outdoor)``), and the delivered heat is
``P_elec * COP(T_tank)`` - a bilinear, non-convex coupling. EMHASS handled it with a
successive-substitution fixed-point (solve with a fixed COP, recompute COP from the
achieved temperature, re-solve). On marginal HP-vs-alternative-source days that
iteration *limit-cycles*: it freezes mid-oscillation dispatching the gas/backup source
against a stale COP, and the resulting plan can cost ~2x the true optimum.

Dynamic programming sidesteps the non-convexity entirely. The state is the tank
temperature(s); backward induction evaluates the *true* COP at every state and finds
the global optimum in a single pass - no convexity, no linearization, no oscillation.
The buffer is a single state; adding the pool (a second slow store that can bank heat)
is a 2-state DP and still solves in ~1-2 s on a 48-step horizon.

Scope / status
--------------
PROTOTYPE. This module solves the *thermal core* (buffer + optional pool) against a
per-timestep electricity price. Coordinating it with the rest of the EMHASS MILP
(PV, grid, battery, EV, capacity tariff) is done by passing in the effective marginal
price per step; see ``solve_buffer_pool_dp``. The MILP <-> DP coordination loop is not
yet wired into ``optimization.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ThermalDPParams:
    """Physical parameters for the buffer (+ optional pool) DP."""

    # Buffer (the HP-charged store whose temperature sets the COP).
    buffer_heat_capacity: float = 1.163  # kWh/K  (e.g. 1000 L water ~= 1.163)
    buffer_loss_coeff: float = 0.05  # kW/K to indoor ambient
    buffer_min_temp: float = 25.0
    buffer_max_temp: float = 65.0  # the super-heat ceiling - DP uses it only when it pays
    buffer_grid_step: float = 0.5

    # Heat pump + backup source feeding the buffer.
    carnot_efficiency: float = 0.45
    hx_approach: float = 5.0  # condenser is tank_temp + approach
    cop_bounds: tuple[float, float] = (1.0, 8.0)
    hp_max_power: float = 4.2  # kW electric
    backup_price: float = 0.10  # commodity price of the non-electric source (gas) per kWh input
    backup_efficiency: float = 0.95
    backup_max_power: float = 24.0  # kW input

    # Optional pool fed by buffer->pool transfer.
    pool_heat_capacity: float | None = None  # kWh/K; None disables the pool state
    pool_loss_coeff: float = 0.7  # kW/K to outdoor
    pool_min_temp: float = 26.5
    pool_max_temp: float = 30.0
    pool_grid_step: float = 0.1
    transfer_coeff: float = 2.0  # kW/K (buffer->pool emitter/HX conductance)
    transfer_max_power: float = 20.0  # kW
    transfer_levels: int = 11

    # House (or other) demand drawn directly from the buffer.
    house_demand_kw: float | np.ndarray = 0.0

    indoor_ambient: float = 20.0


@dataclass
class ThermalDPResult:
    buffer_trajectory: np.ndarray
    pool_trajectory: np.ndarray | None
    hp_electric_per_step: np.ndarray  # kW electric drawn by the HP each step
    backup_input_per_step: np.ndarray  # kW input to the backup source each step
    total_cost: float
    solve_seconds: float
    meta: dict = field(default_factory=dict)


def _cop_curve(buffer_grid: np.ndarray, p: ThermalDPParams, outdoor: float) -> np.ndarray:
    supply = buffer_grid + p.hx_approach
    cop = p.carnot_efficiency * (supply + 273.15) / (supply - outdoor)
    return np.clip(cop, p.cop_bounds[0], p.cop_bounds[1])


def solve_buffer_pool_dp(
    price: np.ndarray,
    outdoor_temperature: float | np.ndarray,
    params: ThermalDPParams,
    time_step: float = 0.5,
    buffer_start: float = 35.0,
    pool_start: float = 26.5,
) -> ThermalDPResult:
    """Exact DP for the buffer (+ optional pool) against a per-step electricity price.

    ``price[t]`` is the marginal cost of HP electricity at step t (the rest of the
    system - PV, grid, capacity - reduces to this number per step). The DP returns the
    globally optimal buffer/pool temperature trajectory and the HP/backup dispatch.

    Outdoor temperature may be a scalar or a per-step array; a scalar is broadcast.
    Currently the COP grid is built from a scalar outdoor (mean if an array is given) -
    a per-step COP grid is a small extension left for the integration step.
    """
    import time

    t0 = time.time()
    N = len(price)
    dt = time_step
    p = params
    outdoor_arr = np.full(N, float(outdoor_temperature)) if np.ndim(outdoor_temperature) == 0 \
        else np.asarray(outdoor_temperature, dtype=float)
    outdoor_ref = float(np.mean(outdoor_arr))
    house = p.house_demand_kw if np.ndim(p.house_demand_kw) else np.full(N, float(p.house_demand_kw))
    house = np.broadcast_to(house, (N,))

    bufg = np.arange(p.buffer_min_temp, p.buffer_max_temp + 1e-6, p.buffer_grid_step)
    nb = len(bufg)
    copb = _cop_curve(bufg, p, outdoor_ref)
    bufloss = p.buffer_loss_coeff * (bufg - p.indoor_ambient) * dt
    hp_cap_th = p.hp_max_power * copb * dt
    qin_max = (p.hp_max_power * copb + p.backup_max_power * p.backup_efficiency) * dt
    cp_backup = p.backup_price / p.backup_efficiency

    use_pool = p.pool_heat_capacity is not None
    if use_pool:
        poolg = np.arange(p.pool_min_temp, p.pool_max_temp + 1e-6, p.pool_grid_step)
        npl = len(poolg)
        poolloss = p.pool_loss_coeff * (poolg - outdoor_ref) * dt
        qxf_levels = np.linspace(0.0, p.transfer_max_power * dt, p.transfer_levels)
    else:
        poolg = np.array([0.0])
        npl = 1
        qxf_levels = np.array([0.0])

    INF = 1e15

    def cheapest(Qin: np.ndarray, t: int) -> np.ndarray:
        """Per-buffer-temp cost to deliver Qin (kWh thermal) at step t."""
        Qpos = np.maximum(Qin, 0.0)
        qhp = np.where(price[t] / copb <= cp_backup,
                       np.minimum(Qpos, hp_cap_th),
                       np.maximum(Qpos - p.backup_max_power * p.backup_efficiency * dt, 0.0))
        qbk = Qpos - qhp
        return (qhp / copb) * price[t] + (qbk / p.backup_efficiency) * p.backup_price

    # Backward induction.
    V = np.zeros((nb, npl))
    POL = np.zeros((N, nb, npl, 2), dtype=np.int16)
    for t in range(N - 1, -1, -1):
        Vn = np.full((nb, npl), INF)
        best_jb = np.zeros((nb, npl), np.int16)
        best_q = np.zeros((nb, npl), np.int16)
        for jb in range(nb):
            base = (bufg[jb] - bufg) * p.buffer_heat_capacity + house[t] * dt + bufloss
            for qi, qxf in enumerate(qxf_levels):
                Qin = base + qxf
                cost = cheapest(Qin, t)
                feas_b = (Qin >= -1e-9) & (Qin <= qin_max + 1e-9)
                if use_pool:
                    Tp2 = poolg + (qxf - poolloss) / p.pool_heat_capacity
                    feas_p = (Tp2 >= poolg[0] - 1e-9) & (Tp2 <= poolg[-1] + 1e-9)
                    Vnext = np.interp(Tp2, poolg, V[jb, :])
                    xf_ok = qxf <= p.transfer_coeff * (bufg[:, None] - poolg[None, :]) * dt + 1e-9
                    val = np.where(feas_b[:, None] & feas_p[None, :] & xf_ok,
                                   cost[:, None] + Vnext[None, :], INF)
                else:
                    val = np.where(feas_b, cost + V[jb, 0], INF)[:, None]
                upd = val < Vn
                Vn = np.where(upd, val, Vn)
                best_jb = np.where(upd, jb, best_jb)
                best_q = np.where(upd, qi, best_q)
        V = Vn
        POL[t, :, :, 0] = best_jb
        POL[t, :, :, 1] = best_q

    # Forward rollout from the start state.
    ib = int(np.argmin(np.abs(bufg - buffer_start)))
    ip = int(np.argmin(np.abs(poolg - pool_start))) if use_pool else 0
    btraj = [bufg[ib]]
    ptraj = [poolg[ip]] if use_pool else None
    hp_draw = np.zeros(N)
    bk_draw = np.zeros(N)
    cost = 0.0
    for t in range(N):
        jb = int(POL[t, ib, ip, 0])
        qxf = qxf_levels[int(POL[t, ib, ip, 1])]
        Qin = max(0.0, (bufg[jb] - bufg[ib]) * p.buffer_heat_capacity + house[t] * dt + bufloss[ib] + qxf)
        if price[t] / copb[ib] <= cp_backup:
            qhp = min(Qin, hp_cap_th[ib])
            qbk = Qin - qhp
        else:
            qbk = min(Qin, p.backup_max_power * p.backup_efficiency * dt)
            qhp = Qin - qbk
        cost += (qhp / copb[ib]) * price[t] + (qbk / p.backup_efficiency) * p.backup_price
        hp_draw[t] = qhp / copb[ib] / dt
        bk_draw[t] = qbk / p.backup_efficiency / dt
        if use_pool:
            Tp2 = poolg[ip] + (qxf - poolloss[ip]) / p.pool_heat_capacity
            ip = int(np.argmin(np.abs(poolg - Tp2)))
            ptraj.append(poolg[ip])
        ib = jb
        btraj.append(bufg[ib])

    return ThermalDPResult(
        buffer_trajectory=np.array(btraj),
        pool_trajectory=np.array(ptraj) if use_pool else None,
        hp_electric_per_step=hp_draw,
        backup_input_per_step=bk_draw,
        total_cost=float(cost),
        solve_seconds=time.time() - t0,
        meta={"buffer_states": nb, "pool_states": npl, "horizon": N},
    )
