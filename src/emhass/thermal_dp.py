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

# Upper bound on the number of discretized temperature states for the coupled
# store. Its grid step defaults to a fine 0.1 C, so a wide configured band (e.g.
# a mis-set 0-100 C pool) would otherwise create ~1000 states and blow up the
# backward induction. When the band would exceed this, the step is coarsened so
# the state count stays bounded; the band itself is preserved.
MAX_COUPLED_STATES = 64

# Upper bound on the number of discretized temperature states for the heat-pump
# store itself. grid_step is user-configurable, so a fine step on a wide band (e.g.
# 0.1 C over 25-65 C -> 401 states) would make the backward induction slow and, past
# ~32767 states, overflow the int16 policy array into a silently wrong plan. When the
# band would exceed this, the step is coarsened so the count stays bounded; the band
# is preserved. The default 0.5 C step stays well under the cap (unchanged behaviour).
MAX_TANK_STATES = 200


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
    # mode "heat": the unit ADDS heat, condenser runs at store_temp + approach, charging
    # raises temperature. mode "cool": the unit REMOVES heat (chiller), evaporator runs at
    # store_temp - approach, charging LOWERS temperature; the COP, standing-loss sign and
    # charging direction all invert. Cool mode does not support a coupled store yet.
    mode: str = "heat"  # "heat" | "cool"
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

    Outdoor temperature may be a scalar or a per-step array; the COP is evaluated per
    timestep against that step's outdoor temperature, so intraday swings (a cold dawn,
    a mild PV-rich midday) are reflected - not averaged away. For a charging step the COP
    is taken at the TARGET (end-of-step) temperature ``T[t+1] + approach``: over a control
    step the heat pump runs at the supply temperature needed to reach the step's setpoint,
    so the COP is set by the temperature it heats to, not the cooler one it starts from.
    """
    import time

    t0 = time.time()
    N = len(price)
    dt = time_step
    p = params
    # Sense of the unit: +1 heat (adds heat; charging raises temperature), -1 cool
    # (removes heat; charging lowers temperature). Flips the energy-balance / loss sign.
    sc = -1.0 if p.mode == "cool" else 1.0
    outdoor_arr = (
        np.full(N, float(outdoor_temperature))
        if np.ndim(outdoor_temperature) == 0
        else np.asarray(outdoor_temperature, dtype=float)
    )
    if len(outdoor_arr) < N:  # forward-fill a short outdoor series to the horizon
        outdoor_arr = np.concatenate([outdoor_arr, np.full(N - len(outdoor_arr), outdoor_arr[-1])])
    outdoor_arr = outdoor_arr[:N]
    outdoor_ref = float(np.mean(outdoor_arr))
    demand = p.demand_kw if np.ndim(p.demand_kw) else np.full(N, float(p.demand_kw))
    demand = np.broadcast_to(demand, (N,))

    span_t = p.max_temp - p.min_temp
    if span_t > 0:
        # Resolution from grid_step, hard-capped at MAX_TANK_STATES (bounds runtime and
        # keeps nt < int16 so the policy array cannot overflow). linspace for an exact
        # count; the default 0.5 C step lands below the cap, leaving the grid unchanged.
        nt = min(MAX_TANK_STATES, max(2, int(round(span_t / p.grid_step)) + 1))
        grid = np.linspace(p.min_temp, p.max_temp, nt)
    else:
        grid = np.array([p.min_temp])
    nt = len(grid)
    # COP for a charging step i -> j is taken at the TARGET temperature grid[j]: over a
    # 30-minute control step the heat pump receives one setpoint and runs its condenser
    # at the supply temperature needed to REACH it (grid[j] + approach), so the COP is set
    # by the temperature it heats TO, not the cooler temperature it starts from. This is
    # both the physically faithful model for a setpoint-driven HP and the conservative one
    # (it prices a large heating step at its true cost). cop2d[t, j] evaluates the target
    # supply against step t's outdoor temperature, so an intraday swing is still captured.
    # Supply temperature the unit runs at to reach target grid[j]. Heat: the condenser runs
    # ABOVE the store (grid + approach). Cool: the evaporator runs BELOW the store
    # (grid - approach) to extract heat. The Carnot COP pays for the lift between the hot and
    # cold sides: condenser - outdoor (heat) or outdoor - evaporator (cool). A vanishing or
    # negative lift (heat: outdoor >= supply, a low store on a hot day; cool: outdoor <=
    # supply, a chilled store on a cold day) is the maximally-efficient / free regime, so it
    # clamps to the UPPER bound - a negative Carnot denominator must NOT clip to the
    # resistive floor (cop_bounds[0]).
    if p.mode == "cool":
        supply = grid - p.hx_approach  # (nt,) cold evaporator side
        lift = outdoor_arr[:, None] - supply[None, :]  # (N, nt) outdoor - evaporator
    else:
        supply = grid + p.hx_approach  # (nt,) condenser supply needed to reach each target
        lift = supply[None, :] - outdoor_arr[:, None]  # (N, nt) condenser - source
    carnot = p.carnot_efficiency * (supply[None, :] + 273.15) / np.where(lift > 1e-6, lift, 1e-6)
    cop2d = np.clip(
        np.where(lift > 1e-6, carnot, p.cop_bounds[1]), *p.cop_bounds
    )  # (N, nt): cop2d[t, j] = COP to charge to grid[j] at step t
    hp_cap_th = p.hp_max_power * cop2d * dt  # (N, nt) thermal kWh the HP delivers reaching j
    qin_max = (p.hp_max_power * cop2d + p.backup_max_power * p.backup_efficiency) * dt  # (N, nt)
    loss = p.loss_coeff * (grid - p.ambient_temperature) * dt
    cp_backup = p.backup_price / p.backup_efficiency

    use_coupled = p.coupled_heat_capacity is not None
    if use_coupled and p.mode == "cool":
        raise NotImplementedError(
            "cool-mode thermal DP does not support a coupled store yet; "
            "the optimizer keeps the static COP for cool tanks with coupling."
        )
    if use_coupled:
        span = p.coupled_max_temp - p.coupled_min_temp
        if span > 0:
            # Resolution from the configured step, but hard-capped at MAX_COUPLED_STATES.
            # linspace (not arange) so the count is exact - arange's float endpoint fudge
            # could otherwise blow the count up on a tiny span.
            npts = min(MAX_COUPLED_STATES, max(2, int(round(span / p.coupled_grid_step)) + 1))
            cgrid = np.linspace(p.coupled_min_temp, p.coupled_max_temp, npts)
        else:
            cgrid = np.array([p.coupled_min_temp])
        ncl = len(cgrid)
        closs = p.coupled_loss_coeff * (cgrid - outdoor_ref) * dt
        qxf_levels = np.linspace(0.0, p.coupling_max_power * dt, p.coupling_levels)
    else:
        cgrid = np.array([0.0])
        ncl = 1
        qxf_levels = np.array([0.0])

    INF = 1e15

    def cheapest(Qin: np.ndarray, t: int, j: int) -> np.ndarray:
        """Cost over each current state i to deliver Qin (kWh thermal) at step t while
        charging to target j (the HP runs at grid[j]'s supply temperature, so the COP is
        the scalar cop2d[t, j])."""
        Qpos = np.maximum(Qin, 0.0)
        cop_t = cop2d[t, j]
        qhp = np.where(
            price[t] / cop_t <= cp_backup,
            np.minimum(Qpos, hp_cap_th[t, j]),
            np.maximum(Qpos - p.backup_max_power * p.backup_efficiency * dt, 0.0),
        )
        qbk = Qpos - qhp
        return (qhp / cop_t) * price[t] + (qbk / p.backup_efficiency) * p.backup_price

    # Backward induction.
    V = np.zeros((nt, ncl))
    POL = np.zeros((N, nt, ncl, 2), dtype=np.int16)
    for t in range(N - 1, -1, -1):
        Vn = np.full((nt, ncl), INF)
        best_j = np.zeros((nt, ncl), np.int16)
        best_q = np.zeros((nt, ncl), np.int16)
        for j in range(nt):
            # Energy the unit must move to reach target j from each current state. Heat
            # (sc=+1): Qin to ADD = (grid[j]-grid)*hc + demand + loss. Cool (sc=-1): Qin to
            # REMOVE = (grid-grid[j])*hc + demand - loss, i.e. sc flips the temperature
            # delta and the passive-loss term while the demand stays a positive load.
            base = sc * (grid[j] - grid) * p.heat_capacity + demand[t] * dt + sc * loss
            for qi, qxf in enumerate(qxf_levels):
                Qin = base + qxf
                cost = cheapest(Qin, t, j)
                feas_t = (Qin >= -1e-9) & (Qin <= qin_max[t, j] + 1e-9)
                if use_coupled:
                    Tc2 = cgrid + (qxf - closs) / p.coupled_heat_capacity
                    feas_c = (Tc2 >= cgrid[0] - 1e-9) & (Tc2 <= cgrid[-1] + 1e-9)
                    Vnext = np.interp(Tc2, cgrid, V[j, :])
                    # Conductance limits the transfer to coupling_coeff*(T_from-T_to), but
                    # clamp at 0: when the feeder is COLDER than the receiver heat cannot
                    # flow uphill, yet transferring NOTHING (qxf=0) must always stay legal.
                    # Without the clamp the bound goes negative and even qxf=0 is rejected,
                    # making every state with a warmer coupled store spuriously infeasible.
                    xf_ok = (
                        qxf
                        <= np.maximum(0.0, p.coupling_coeff * (grid[:, None] - cgrid[None, :])) * dt
                        + 1e-9
                    )
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
    # V now holds the optimal cost-to-go at t=0. If the start state is INF, no feasible
    # policy exists (e.g. demand exceeds what the heat pump and backup can deliver every
    # step): flag it rather than returning a plausible-looking but energy-violating plan.
    start_infeasible = bool(V[it, ic] >= INF * 0.5)
    traj = [grid[it]]
    ctraj = [cgrid[ic]] if use_coupled else None
    hp_draw = np.zeros(N)
    bk_draw = np.zeros(N)
    cost = 0.0
    for t in range(N):
        j = int(POL[t, it, ic, 0])
        qxf = qxf_levels[int(POL[t, it, ic, 1])]
        Qin = max(
            0.0,
            sc * (grid[j] - grid[it]) * p.heat_capacity + demand[t] * dt + sc * loss[it] + qxf,
        )
        cop_ij = cop2d[t, j]  # COP to reach the target temperature grid[j]
        if price[t] / cop_ij <= cp_backup:
            qhp = min(Qin, hp_cap_th[t, j])
            qbk = Qin - qhp
        else:
            qbk = min(Qin, p.backup_max_power * p.backup_efficiency * dt)
            qhp = Qin - qbk
        cost += (qhp / cop_ij) * price[t] + (qbk / p.backup_efficiency) * p.backup_price
        hp_draw[t] = qhp / cop_ij / dt
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
        total_cost=float("inf") if start_infeasible else float(cost),
        solve_seconds=time.time() - t0,
        meta={
            "tank_states": nt,
            "coupled_states": ncl,
            "horizon": N,
            "infeasible": start_infeasible,
        },
    )
