"""Dynamic-programming solver for a heat-pump-charged thermal store.

A heat pump's COP depends on the temperature it charges the store to
(``COP = carnot * T_supply_K / (T_supply - T_outdoor)``), and the delivered heat is
``P_elec * COP(T_store)`` - a bilinear, non-convex coupling that a single MILP cannot
solve exactly. Dynamic programming sidesteps it: the state is the store
temperature(s); backward induction evaluates the true COP at every state and returns
the globally-optimal dispatch in a single pass, with no convexity assumption and no
linearisation.

The store may optionally be coupled to a second store it feeds through a temperature
gradient (e.g. a tank that supplies a larger sink), which adds a second state and is
still tractable on a day-ahead horizon. Costs are evaluated against a per-timestep
electricity price for the heat pump and a commodity price for an optional backup
source (gas/oil/electric element).

The model is intentionally generic - one heat-pump store, an optional coupled store,
an optional backup source - so it applies to any such configuration. Parameters carry
neutral defaults; callers supply the values for the store they are solving.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ThermalDPParams:
    """Physical parameters for the heat-pump store (and an optional coupled store)."""

    # Heat-pump store: the charged store whose temperature sets the COP.
    heat_capacity: float = 1.0  # kWh/K
    loss_coeff: float = 0.0  # kW/K to ambient
    min_temp: float = 25.0
    max_temp: float = 65.0
    grid_step: float = 0.5
    ambient_temperature: float = 20.0  # reference the standing loss is taken against

    # Heat pump charging the store, plus an optional flat-efficiency backup source.
    carnot_efficiency: float = 0.45
    hx_approach: float = 5.0  # condenser runs at store_temp + approach
    cop_bounds: tuple[float, float] = (1.0, 8.0)
    hp_max_power: float = 3.0  # kW electric
    backup_price: float = 0.10  # commodity price of the backup per kWh input
    backup_efficiency: float = 0.95
    backup_max_power: float = 0.0  # kW input; 0 disables the backup

    # Optional second store fed by a temperature-gradient transfer from the store.
    coupled_heat_capacity: float | None = None  # None keeps the model single-state
    coupled_loss_coeff: float = 0.0  # kW/K
    coupled_min_temp: float = 0.0
    coupled_max_temp: float = 100.0
    coupled_grid_step: float = 0.1
    coupling_coeff: float = 1.0  # kW/K transfer conductance (store -> coupled)
    coupling_max_power: float = 20.0  # kW
    coupling_levels: int = 11

    # External demand drawn directly from the heat-pump store.
    demand_kw: float | np.ndarray = 0.0


@dataclass
class ThermalDPResult:
    tank_trajectory: np.ndarray
    coupled_trajectory: np.ndarray | None
    hp_electric_per_step: np.ndarray  # kW electric drawn by the heat pump each step
    backup_input_per_step: np.ndarray  # kW input to the backup source each step
    total_cost: float
    solve_seconds: float
    meta: dict = field(default_factory=dict)


def _cop_curve(grid: np.ndarray, p: ThermalDPParams, outdoor: float) -> np.ndarray:
    supply = grid + p.hx_approach
    cop = p.carnot_efficiency * (supply + 273.15) / (supply - outdoor)
    return np.clip(cop, p.cop_bounds[0], p.cop_bounds[1])


def solve_thermal_dp(
    price: np.ndarray,
    outdoor_temperature: float | np.ndarray,
    params: ThermalDPParams,
    time_step: float = 0.5,
    tank_start: float = 35.0,
    coupled_start: float = 26.5,
) -> ThermalDPResult:
    """Exact DP for a heat-pump store (and optional coupled store) against a price.

    ``price[t]`` is the marginal cost of heat-pump electricity at step t. The DP
    returns the globally optimal store temperature trajectory and the heat-pump /
    backup dispatch.

    Outdoor temperature may be a scalar or a per-step array; the COP grid is built
    from its mean (a per-step COP grid is a small extension).
    """
    import time

    t0 = time.time()
    N = len(price)
    dt = time_step
    p = params
    outdoor_arr = (
        np.full(N, float(outdoor_temperature))
        if np.ndim(outdoor_temperature) == 0
        else np.asarray(outdoor_temperature, dtype=float)
    )
    outdoor_ref = float(np.mean(outdoor_arr))
    demand = p.demand_kw if np.ndim(p.demand_kw) else np.full(N, float(p.demand_kw))
    demand = np.broadcast_to(demand, (N,))

    grid = np.arange(p.min_temp, p.max_temp + 1e-6, p.grid_step)
    nt = len(grid)
    cop = _cop_curve(grid, p, outdoor_ref)
    loss = p.loss_coeff * (grid - p.ambient_temperature) * dt
    hp_cap_th = p.hp_max_power * cop * dt
    qin_max = (p.hp_max_power * cop + p.backup_max_power * p.backup_efficiency) * dt
    cp_backup = p.backup_price / p.backup_efficiency

    use_coupled = p.coupled_heat_capacity is not None
    if use_coupled:
        cgrid = np.arange(p.coupled_min_temp, p.coupled_max_temp + 1e-6, p.coupled_grid_step)
        ncl = len(cgrid)
        closs = p.coupled_loss_coeff * (cgrid - outdoor_ref) * dt
        qxf_levels = np.linspace(0.0, p.coupling_max_power * dt, p.coupling_levels)
    else:
        cgrid = np.array([0.0])
        ncl = 1
        qxf_levels = np.array([0.0])

    INF = 1e15

    def cheapest(Qin: np.ndarray, t: int) -> np.ndarray:
        """Per-temperature cost to deliver Qin (kWh thermal) at step t."""
        Qpos = np.maximum(Qin, 0.0)
        qhp = np.where(
            price[t] / cop <= cp_backup,
            np.minimum(Qpos, hp_cap_th),
            np.maximum(Qpos - p.backup_max_power * p.backup_efficiency * dt, 0.0),
        )
        qbk = Qpos - qhp
        return (qhp / cop) * price[t] + (qbk / p.backup_efficiency) * p.backup_price

    # Backward induction.
    V = np.zeros((nt, ncl))
    POL = np.zeros((N, nt, ncl, 2), dtype=np.int16)
    for t in range(N - 1, -1, -1):
        Vn = np.full((nt, ncl), INF)
        best_j = np.zeros((nt, ncl), np.int16)
        best_q = np.zeros((nt, ncl), np.int16)
        for j in range(nt):
            base = (grid[j] - grid) * p.heat_capacity + demand[t] * dt + loss
            for qi, qxf in enumerate(qxf_levels):
                Qin = base + qxf
                cost = cheapest(Qin, t)
                feas_t = (Qin >= -1e-9) & (Qin <= qin_max + 1e-9)
                if use_coupled:
                    Tc2 = cgrid + (qxf - closs) / p.coupled_heat_capacity
                    feas_c = (Tc2 >= cgrid[0] - 1e-9) & (Tc2 <= cgrid[-1] + 1e-9)
                    Vnext = np.interp(Tc2, cgrid, V[j, :])
                    xf_ok = qxf <= p.coupling_coeff * (grid[:, None] - cgrid[None, :]) * dt + 1e-9
                    val = np.where(
                        feas_t[:, None] & feas_c[None, :] & xf_ok,
                        cost[:, None] + Vnext[None, :],
                        INF,
                    )
                else:
                    val = np.where(feas_t, cost + V[j, 0], INF)[:, None]
                upd = val < Vn
                Vn = np.where(upd, val, Vn)
                best_j = np.where(upd, j, best_j)
                best_q = np.where(upd, qi, best_q)
        V = Vn
        POL[t, :, :, 0] = best_j
        POL[t, :, :, 1] = best_q

    # Forward rollout from the start state.
    it = int(np.argmin(np.abs(grid - tank_start)))
    ic = int(np.argmin(np.abs(cgrid - coupled_start))) if use_coupled else 0
    traj = [grid[it]]
    ctraj = [cgrid[ic]] if use_coupled else None
    hp_draw = np.zeros(N)
    bk_draw = np.zeros(N)
    cost = 0.0
    for t in range(N):
        j = int(POL[t, it, ic, 0])
        qxf = qxf_levels[int(POL[t, it, ic, 1])]
        Qin = max(0.0, (grid[j] - grid[it]) * p.heat_capacity + demand[t] * dt + loss[it] + qxf)
        if price[t] / cop[it] <= cp_backup:
            qhp = min(Qin, hp_cap_th[it])
            qbk = Qin - qhp
        else:
            qbk = min(Qin, p.backup_max_power * p.backup_efficiency * dt)
            qhp = Qin - qbk
        cost += (qhp / cop[it]) * price[t] + (qbk / p.backup_efficiency) * p.backup_price
        hp_draw[t] = qhp / cop[it] / dt
        bk_draw[t] = qbk / p.backup_efficiency / dt
        if use_coupled:
            Tc2 = cgrid[ic] + (qxf - closs[ic]) / p.coupled_heat_capacity
            ic = int(np.argmin(np.abs(cgrid - Tc2)))
            ctraj.append(cgrid[ic])
        it = j
        traj.append(grid[it])

    return ThermalDPResult(
        tank_trajectory=np.array(traj),
        coupled_trajectory=np.array(ctraj) if use_coupled else None,
        hp_electric_per_step=hp_draw,
        backup_input_per_step=bk_draw,
        total_cost=float(cost),
        solve_seconds=time.time() - t0,
        meta={"tank_states": nt, "coupled_states": ncl, "horizon": N},
    )
