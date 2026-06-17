"""Experiment matrix for the DP COP refinement.

Each scenario is a deliberate stress test of ONE genericity boundary identified
in the code review (see docs notes / optimization.py:2520-3143). A scenario
returns a spec dict consumed by harness.run_pair:

    {topology, overrides, scenario, tank_starts, hypothesis, limit_probed,
     pass_criteria}

Pass criteria are written as the SAFE behaviour, not "optimal": for a topology
the DP cannot model exactly, the correct outcome is a feasible, in-band plan
(skip-cap or approximate) - never a silent band violation or an infeasible solve.
"""

from __future__ import annotations

N = 48


def populate(register, hp, gas, tank, scenario):
    # Shared building blocks ------------------------------------------------
    draw_off = [1.0 if (i % 48) in (14, 15, 38, 39) else 0.0 for i in range(N)]
    showers = {"id": "showers", "target": "dhw", "type": "profile", "profile": draw_off}
    pool_solar = {"id": "pool_solar", "target": "pool", "type": "pool_comfort",
                  "solar_absorption_area": 30.0, "solar_absorption_factor": 0.7}

    def tracks():
        return {}  # harness fills electricity + gas

    # --- CONTROLS ----------------------------------------------------------

    def your_config():
        topo = {
            "sources": [hp(), gas()],
            "storage": [
                tank("dhw", 50, 45, 62, 52, volume=0.20, loss=0.10, penalty=30),
                tank("buffer", 38, 30, 52, 35, volume=0.10, loss=0.08, penalty=5),
                tank("pool", 26, 18, 30, 26, thermal_mass=50.0, loss_coefficient=0.20, penalty=5),
                tank("house", 20, 19, 23, 20.5, thermal_mass=10.0, loss_coefficient=0.25, penalty=20),
            ],
            "consumers": [showers, pool_solar],
            "flows": [
                {"from": "hp", "to": "buffer"}, {"from": "hp", "to": "dhw"},
                {"from": "gas", "to": "buffer"}, {"from": "gas", "to": "dhw"},
                {"from": "buffer", "to": "pool", "transfer_coefficient": 0.5, "max_transfer_power": 4000},
                {"from": "buffer", "to": "house", "transfer_coefficient": 0.3, "max_transfer_power": 6000},
            ],
            "cost_tracks": tracks(),
            "actuator_groups": [
                {"flows": [["hp", "buffer"], ["hp", "dhw"]], "mutual_exclusion": True},
                {"flows": [["gas", "buffer"], ["gas", "dhw"]], "mutual_exclusion": True},
            ],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {},
            "tank_starts": {"dhw": 50, "buffer": 38, "pool": 26, "house": 20},
            "limit_probed": "baseline (the modelled-exact topology)",
            "hypothesis": "DP engages on the buffer, lands ~38-41 C, everything in band.",
            "pass_criteria": "auto feasible AND buffer engaged AND zero band violation.",
        }

    def gas_only_noop():
        topo = {
            "sources": [gas()],
            "storage": [tank("buffer", 38, 30, 52, 35, volume=0.10, loss=0.08, penalty=5)],
            "consumers": [], "flows": [{"from": "gas", "to": "buffer"}],
            "cost_tracks": tracks(),
            "actuator_groups": [],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {},
            "tank_starts": {"buffer": 38},
            "limit_probed": "no heat pump at all (gas-only)",
            "hypothesis": "No heating-curve HP -> DP must no-op; auto == static.",
            "pass_criteria": "auto feasible AND zero engaged AND zero eligible HP tanks.",
        }

    def fixed_supply_noop():
        # A heat pump with a FIXED supply_temperature and NO heating_curve: is_hp is
        # False, its COP is constant by design, the DP must leave it alone.
        src = {"id": "hpfix", "type": "heatpump", "nominal_power": 3000, "min_power": 0,
               "treat_as_semi_cont": False, "carnot_efficiency": 0.45,
               "supply_temperature": 45, "cost_track": "electricity"}
        topo = {
            "sources": [src],
            "storage": [tank("buffer", 38, 30, 52, 35, volume=0.10, loss=0.08, penalty=5)],
            "consumers": [], "flows": [{"from": "hpfix", "to": "buffer"}],
            "cost_tracks": tracks(), "actuator_groups": [],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"buffer": 38},
            "limit_probed": "fixed-supply HP (constant COP, not DP-refinable)",
            "hypothesis": "is_hp False -> DP no-op even though a HP is present.",
            "pass_criteria": "auto feasible AND zero engaged.",
        }

    def lone_hp_dhw():
        topo = {
            "sources": [hp(max_supply=62, slope=-0.8, offset=45)],
            "storage": [tank("dhw", 48, 45, 62, 52, volume=0.20, loss=0.10, penalty=30)],
            "consumers": [{"id": "showers", "target": "dhw", "type": "profile", "profile": draw_off}],
            "flows": [{"from": "hp", "to": "dhw"}],
            "cost_tracks": tracks(), "actuator_groups": [],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"dhw": 48},
            "limit_probed": "simplest exact case: lone HP DHW tank, no transfers",
            "hypothesis": "DP engages (single-state) and is exact; tank stays in band.",
            "pass_criteria": "auto feasible AND zero band violation.",
        }

    # --- STRUCTURAL LIMITS -------------------------------------------------

    def two_bankable_pools():
        # Buffer feeds TWO large equal-mass pools that BOTH want pre-charging on a
        # big spread. Only the largest becomes the coupled DP state; the other is a
        # fixed-demand non-coupled receiver. This is the documented out-of-scope case.
        topo = {
            "sources": [hp(nominal=6000), gas()],
            "storage": [
                tank("buffer", 38, 30, 60, 35, volume=0.15, loss=0.08, penalty=5),
                tank("poolA", 26, 18, 45, 30, thermal_mass=50.0, loss_coefficient=0.20, penalty=8),
                tank("poolB", 27, 18, 45, 30, thermal_mass=50.0, loss_coefficient=0.20, penalty=8),
            ],
            "consumers": [],
            "flows": [
                {"from": "hp", "to": "buffer"}, {"from": "gas", "to": "buffer"},
                {"from": "buffer", "to": "poolA", "transfer_coefficient": 1.0, "max_transfer_power": 8000},
                {"from": "buffer", "to": "poolB", "transfer_coefficient": 1.0, "max_transfer_power": 8000},
            ],
            "cost_tracks": tracks(),
            "actuator_groups": [{"flows": [["hp", "buffer"], ["gas", "buffer"]], "mutual_exclusion": False}],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"buffer": 38, "poolA": 26, "poolB": 27},
            "limit_probed": "TWO large bankable downstream stores (only one coupled)",
            "hypothesis": "Only the largest pool is a real DP decision; the other is "
                          "approximated as comfort load and may be under-banked.",
            "pass_criteria": "auto feasible AND zero band violation (safety); observe "
                             "whether poolB banks less than poolA despite symmetry.",
        }

    def highmass_wideband_receiver():
        # Buffer feeds a coupled pool (largest) AND a high-mass, wide-band slab as a
        # NON-coupled receiver. Banking into the slab is genuinely economic, but the
        # DP models it as steady-state comfort loss -> understates the opportunity.
        topo = {
            "sources": [hp(nominal=6000), gas()],
            "storage": [
                tank("buffer", 38, 30, 60, 35, volume=0.15, loss=0.08, penalty=5),
                tank("pool", 26, 18, 32, 28, thermal_mass=80.0, loss_coefficient=0.20, penalty=8),
                tank("slab", 24, 20, 45, 24, thermal_mass=40.0, loss_coefficient=0.10, penalty=15),
            ],
            "consumers": [],
            "flows": [
                {"from": "hp", "to": "buffer"}, {"from": "gas", "to": "buffer"},
                {"from": "buffer", "to": "pool", "transfer_coefficient": 1.0, "max_transfer_power": 8000},
                {"from": "buffer", "to": "slab", "transfer_coefficient": 0.8, "max_transfer_power": 8000},
            ],
            "cost_tracks": tracks(),
            "actuator_groups": [{"flows": [["hp", "buffer"], ["gas", "buffer"]], "mutual_exclusion": False}],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"buffer": 38, "pool": 26, "slab": 24},
            "limit_probed": "high-mass wide-band NON-coupled receiver (banking economic)",
            "hypothesis": "Slab modelled as comfort loss; DP under-banks it vs a run "
                          "that could treat it as a decision.",
            "pass_criteria": "auto feasible AND zero band violation; observe slab peak.",
        }

    def cascade_two_hop():
        # HP -> buffer -> mid -> pool. The DP sees only the buffer's direct transfer
        # (to mid); the second hop (mid -> pool) is invisible to it.
        topo = {
            "sources": [hp(nominal=6000), gas()],
            "storage": [
                tank("buffer", 38, 30, 60, 35, volume=0.15, loss=0.08, penalty=5),
                tank("mid", 30, 20, 45, 30, thermal_mass=40.0, loss_coefficient=0.15, penalty=8),
                tank("pool", 26, 18, 32, 28, thermal_mass=60.0, loss_coefficient=0.20, penalty=8),
            ],
            "consumers": [],
            "flows": [
                {"from": "hp", "to": "buffer"}, {"from": "gas", "to": "buffer"},
                {"from": "buffer", "to": "mid", "transfer_coefficient": 1.0, "max_transfer_power": 8000},
                {"from": "mid", "to": "pool", "transfer_coefficient": 0.8, "max_transfer_power": 8000},
            ],
            "cost_tracks": tracks(),
            "actuator_groups": [{"flows": [["hp", "buffer"], ["gas", "buffer"]], "mutual_exclusion": False}],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"buffer": 38, "mid": 30, "pool": 26},
            "limit_probed": "two-hop cascade (buffer -> mid -> pool)",
            "hypothesis": "DP models only the buffer->mid hop; the mid->pool second "
                          "hop is invisible. Should stay safe.",
            "pass_criteria": "auto feasible AND zero band violation.",
        }

    def two_independent_hp():
        # Two fully independent HP tanks. Each should refine on its own.
        topo = {
            "sources": [
                hp(id="hpA", nominal=4000), hp(id="hpB", nominal=4000),
            ],
            "storage": [
                tank("bufA", 38, 30, 55, 35, volume=0.12, loss=0.08, penalty=5),
                tank("bufB", 40, 30, 55, 36, volume=0.12, loss=0.08, penalty=5),
            ],
            "consumers": [],
            "flows": [{"from": "hpA", "to": "bufA"}, {"from": "hpB", "to": "bufB"}],
            "cost_tracks": tracks(), "actuator_groups": [],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"bufA": 38, "bufB": 40},
            "limit_probed": "two independent HP tanks (per-tank refinement + isolation)",
            "hypothesis": "Both buffers refine independently; one bad tank must not "
                          "abort the other.",
            "pass_criteria": "auto feasible AND both tanks in band AND >=1 engaged.",
        }

    def hc_threshold_edge_below():
        # A bankable store with heat capacity just BELOW the hc>=20 coupling threshold
        # (thermal_mass ~12). It will NOT be coupled -> treated as fixed demand.
        topo = _buffer_plus_store(hp, gas, tank, tracks, store_mass=12.0)
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"buffer": 38, "store": 26},
            "limit_probed": "downstream store BELOW the hc>=20 coupling threshold",
            "hypothesis": "Store hc<20 is never coupled, even though banking pays; "
                          "treated as fixed demand -> under-optimised.",
            "pass_criteria": "auto feasible AND zero band violation; compare store "
                             "peak against hc_threshold_edge_above.",
        }

    def hc_threshold_edge_above():
        # Same store but heat capacity ABOVE the threshold (thermal_mass ~30): now
        # it IS coupled. The pair isolates the threshold's effect.
        topo = _buffer_plus_store(hp, gas, tank, tracks, store_mass=30.0)
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"buffer": 38, "store": 26},
            "limit_probed": "same store ABOVE the hc>=20 coupling threshold (control)",
            "hypothesis": "Store hc>=20 becomes the coupled DP state and can bank.",
            "pass_criteria": "auto feasible AND zero band violation; store should bank "
                             "MORE than the below-threshold twin if the threshold bites.",
        }

    # --- ECONOMIC / PRICING ------------------------------------------------

    def capacity_tariff_peak():
        topo = your_config()["topology"]
        return {
            "topology": topo,
            # The 4-tank capacity MILP is heavy; a MIP gap keeps the STATIC baseline
            # from timing out (User_Limit), so the fair comparison is actually valid.
            "overrides": {"capacity_cost_per_kw": 8.0, "lp_solver_mip_rel_gap": 0.06},
            "scenario": {"spread": "big"},
            "tank_starts": {"dhw": 50, "buffer": 38, "pool": 26, "house": 20},
            "limit_probed": "capacity/demand charge invisible to the DP",
            "hypothesis": "DP super-heats peak-blind; the re-solve must re-impose the "
                          "demand charge. Risk: DP proposes a peak it then walks back.",
            "pass_criteria": "auto feasible AND zero band violation AND auto grid peak "
                             "not wildly above static (the cap is an upper bound).",
        }

    def lone_hp_capacity():
        # Tractable version of capacity_tariff_peak: ONE heating-curve HP charging ONE
        # buffer, so the static baseline actually solves (the 4-tank version timed out).
        # Optimistic low-supply curve (static COP wrong once the tank is driven above
        # it) + a high physical cap so the DP wants to bank; demand concentrated in the
        # DEAR midday window (big spread = 0.45 at 09-17, 0.07 elsewhere) so pre-heating
        # in the cheap pre-dawn window is attractive; a capacity charge is active and PV
        # is small so the grid peak is HP-driven. Probes whether the DP banks into a
        # peak the demand charge punishes, and whether that peak is cap- or COP-driven.
        src = {
            "id": "hp", "type": "heatpump", "nominal_power": 4000, "min_power": 0,
            "treat_as_semi_cont": False, "carnot_efficiency": 0.45,
            "heating_curve": {"slope": 0.7, "offset": 30, "min_supply": 25, "max_supply": 40},
            "max_supply_temperature": 60, "cost_track": "electricity",
        }
        draw = [0.0] * 48
        for i in range(18, 34):  # steps 18-33 = 09:00-16:30, the dear tariff window
            draw[i] = 1.5
        topo = {
            "sources": [src],
            "storage": [tank("buffer", 45, 35, 60, 50, volume=0.30, loss=0.10, penalty=20)],
            "consumers": [{"id": "draw", "target": "buffer", "type": "profile", "profile": draw}],
            "flows": [{"from": "hp", "to": "buffer"}],
            "cost_tracks": tracks(),
            "actuator_groups": [],
        }
        return {
            "topology": topo,
            "overrides": {"capacity_cost_per_kw": 8.0, "lp_solver_mip_rel_gap": 0.01},
            "scenario": {"spread": "big", "pv_scale": 0.25},
            "tank_starts": {"buffer": 45},
            "limit_probed": "capacity/demand charge invisible to the DP (tractable lone HP)",
            "hypothesis": "The DP banks into the cheap pre-dawn window, raising the grid "
                          "peak the capacity charge punishes; static spreads it. Quantify "
                          "the harm and trace whether the peak is cap- or COP-driven.",
            "pass_criteria": "diagnostic: compare auto vs static grid peak and TOTAL cost "
                             "(energy + capacity charge).",
        }

    def timevarying_backup_price():
        # Gas commodity price swings sharply intraday; the DP flattens it to its mean.
        gas_track = [0.04 if 9 <= (i // 2) < 15 else 0.30 for i in range(N)]
        topo = your_config()["topology"]
        topo["cost_tracks"] = {"gas": gas_track}  # electricity filled by harness
        return {
            "topology": topo, "overrides": {}, "scenario": {},
            "tank_starts": {"dhw": 50, "buffer": 38, "pool": 26, "house": 20},
            "limit_probed": "time-varying backup price (DP uses the mean)",
            "hypothesis": "DP prices gas at its mean, so it cannot time the backup to "
                          "its cheap window; the re-solve's MILP still can.",
            "pass_criteria": "auto feasible AND zero band violation.",
        }

    def export_superheat():
        topo = your_config()["topology"]
        return {
            "topology": topo, "overrides": {},
            "scenario": {"pv_scale": 1.5, "export_price": 0.02, "spread": "two_tier"},
            "tank_starts": {"dhw": 50, "buffer": 38, "pool": 26, "house": 20},
            "limit_probed": "super-heat into a large PV surplus (marginal-price path)",
            "hypothesis": "With near-free midday PV the DP should bank the buffer hotter "
                          "in the PV window than a tariff-only run.",
            "pass_criteria": "auto feasible AND zero band violation; buffer peak should "
                             "rise vs the two_tier baseline (banks into PV).",
        }

    def big_spread_night():
        topo = your_config()["topology"]
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"dhw": 50, "buffer": 38, "pool": 26, "house": 20},
            "limit_probed": "large day/night arbitrage (banking incentive)",
            "hypothesis": "DP banks heat in the cheap window; buffer max in auto should "
                          "exceed the no-arbitrage flat run.",
            "pass_criteria": "auto feasible AND zero band violation.",
        }

    # --- NUMERICAL / ROBUSTNESS -------------------------------------------

    def pathological_wide_pool():
        topo = {
            "sources": [hp(nominal=6000), gas()],
            "storage": [
                tank("buffer", 38, 30, 60, 35, volume=0.15, loss=0.08, penalty=5),
                # Absurd 0..100 band with a fine implied step -> exercises the coupled
                # state cap (MAX_COUPLED_STATES).
                tank("pool", 26, 0, 100, 30, thermal_mass=60.0, loss_coefficient=0.20, penalty=8),
            ],
            "consumers": [],
            "flows": [
                {"from": "hp", "to": "buffer"}, {"from": "gas", "to": "buffer"},
                {"from": "buffer", "to": "pool", "transfer_coefficient": 1.0, "max_transfer_power": 8000},
            ],
            "cost_tracks": tracks(),
            "actuator_groups": [{"flows": [["hp", "buffer"], ["gas", "buffer"]], "mutual_exclusion": False}],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"buffer": 38, "pool": 26},
            "limit_probed": "pathologically wide coupled band (state-space cap)",
            "hypothesis": "MAX_COUPLED_STATES coarsens the grid; solve stays bounded "
                          "and correct rather than blowing up.",
            "pass_criteria": "auto feasible AND zero band violation AND solve completes.",
        }

    def infeasible_demand():
        # Undersized HP, NO gas backup, a hard draw-off, store pinned near its floor:
        # the DP can find no feasible trajectory and must skip-cap, NOT trust the
        # optimistic static COP.
        # Drain-dominated, base-feasible: a hot start, heavy continuous draw, a small
        # HP and NO backup. The tank must coast DOWN through its band to meet demand
        # (no banking headroom). Exercises the DP where there is nothing to super-heat:
        # it should engage and track the forced descent, or skip-cap, never violate.
        heavy_draw = [1.4 for _ in range(N)]
        topo = {
            "sources": [hp(nominal=1500, max_supply=60, carnot=0.35)],
            "storage": [tank("dhw", 60, 45, 62, 50, volume=0.20, loss=0.10, penalty=40)],
            "consumers": [{"id": "showers", "target": "dhw", "type": "profile", "profile": heavy_draw}],
            "flows": [{"from": "hp", "to": "dhw"}],
            "cost_tracks": tracks(), "actuator_groups": [],
        }
        return {
            "topology": topo, "overrides": {}, "scenario": {"spread": "big"},
            "tank_starts": {"dhw": 60},
            "limit_probed": "drain-dominated tank (heavy draw, undersized HP, no backup)",
            "hypothesis": "No banking headroom; the tank is forced to descend through "
                          "its band. DP must engage or skip-cap, never violate the band.",
            "pass_criteria": "auto feasible AND zero band violation AND (engaged OR "
                             "capped, not a silent miss).",
        }

    for name, fn in [
        ("your_config", your_config),
        ("gas_only_noop", gas_only_noop),
        ("fixed_supply_noop", fixed_supply_noop),
        ("lone_hp_dhw", lone_hp_dhw),
        ("two_bankable_pools", two_bankable_pools),
        ("highmass_wideband_receiver", highmass_wideband_receiver),
        ("cascade_two_hop", cascade_two_hop),
        ("two_independent_hp", two_independent_hp),
        ("hc_threshold_edge_below", hc_threshold_edge_below),
        ("hc_threshold_edge_above", hc_threshold_edge_above),
        ("capacity_tariff_peak", capacity_tariff_peak),
        ("lone_hp_capacity", lone_hp_capacity),
        ("timevarying_backup_price", timevarying_backup_price),
        ("export_superheat", export_superheat),
        ("big_spread_night", big_spread_night),
        ("pathological_wide_pool", pathological_wide_pool),
        ("infeasible_demand", infeasible_demand),
    ]:
        register(name, fn)


def _buffer_plus_store(hp, gas, tank, tracks, store_mass):
    return {
        "sources": [hp(nominal=6000), gas()],
        "storage": [
            tank("buffer", 38, 30, 60, 35, volume=0.15, loss=0.08, penalty=5),
            tank("store", 26, 18, 45, 30, thermal_mass=store_mass, loss_coefficient=0.20, penalty=8),
        ],
        "consumers": [],
        "flows": [
            {"from": "hp", "to": "buffer"}, {"from": "gas", "to": "buffer"},
            {"from": "buffer", "to": "store", "transfer_coefficient": 1.0, "max_transfer_power": 8000},
        ],
        "cost_tracks": tracks(),
        "actuator_groups": [{"flows": [["hp", "buffer"], ["gas", "buffer"]], "mutual_exclusion": False}],
    }
