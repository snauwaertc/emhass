"""Parametrized experiment harness for the DP COP refinement.

Runs an arbitrary heat-topology through the optimiser TWICE - once with the DP
COP solver ON (cop_solver='auto') and once OFF (cop_solver='static') - and emits
a structured, machine-readable behavioural report so we can probe where the DP
holds and where it does not.

It is deliberately config-agnostic: callers pass a topology dict (same schema as
scripts/shadow_run_pi.py) plus optional optim_conf overrides. The harness builds
the config, attaches a log-capturing handler to read the DP's own decisions
(engaged / skipped / cannot-refine-cap / failed), runs the solve, and reports:

  - optim_status (must stay Optimal/feasible)
  - per-tank temperature trajectory (start, min, max, peak, total-variation)
  - per-tank band-violation check (did any tank leave [min,max]? -> SILENT BUG)
  - grid peak import, PV export, per-source energy
  - the DP events parsed from the log
  - a cheap realised-cost proxy (grid import cost + gas commodity cost)

The point is BEHAVIOURAL: did the DP do the correct/safe thing for this topology,
not merely "did it run". A run where the DP skip-caps safely is a PASS for a
topology it cannot model; a run where a tank silently leaves its band is a FAIL.

Run one scenario:   .venv/bin/python scripts/dp_experiments/harness.py <name>
List scenarios:     .venv/bin/python scripts/dp_experiments/harness.py --list
Run an inline spec: .venv/bin/python scripts/dp_experiments/harness.py --spec <path.json>

A spec JSON is {"topology": {...}, "overrides": {...}, "scenario": {...},
"tank_starts": {id: start_temp, ...}}. `scenario` knobs tune the base price/PV/
outdoor profile (see scenario()). Output is a single JSON object on stdout.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import sys

import numpy as np
import orjson
import pandas as pd

from emhass import utils
from emhass.optimization import Optimization
from emhass.utils import (
    build_config,
    build_params,
    build_secrets,
    get_logger,
    get_yaml_parse,
    treat_runtimeparams,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
EMHASS_CONF = {
    "data_path": ROOT / "data/",
    "root_path": ROOT / "src/emhass/",
}
EMHASS_CONF["defaults_path"] = EMHASS_CONF["root_path"] / "data/config_defaults.json"
EMHASS_CONF["associations_path"] = EMHASS_CONF["root_path"] / "data/associations.csv"

# One logger for the whole process (get_logger accumulates handlers if called
# repeatedly - the documented footgun - so build it once and reuse it).
LOGGER, _ = get_logger(__name__, EMHASS_CONF, save_to_file=False)
LOGGER.setLevel(logging.INFO)

DT_H = 0.5


class _Capture(logging.Handler):
    """Collects log messages so we can read the DP's own decisions back."""

    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def scenario(N=48, spread="two_tier", pv_scale=1.0, gas_price=0.11, export_price=0.05,
             outdoor_swing=True, peak_hours=None):
    """Base day-ahead scenario. Knobs let experiments stress specific paths.

    spread: 'two_tier' (Belgian HP/HC), 'big' (cheap night/dear day, super-heat
            bait), 'flat' (no arbitrage). pv_scale scales the midday PV bell.
    """
    idx = pd.date_range("2026-04-15 00:00", periods=N, freq="30min", tz="Europe/Brussels")
    h = np.array([t.hour + t.minute / 60 for t in idx])
    if spread == "flat":
        price = np.full(N, 0.16)
    elif spread == "big":
        price = np.where((h >= 9) & (h < 17), 0.45, 0.07)
    else:  # two_tier
        windows = peak_hours or [(2.9, 15.4), (17.4, 20.4)]
        peak = np.any([(h >= a) & (h < b) for a, b in windows], axis=0)
        price = np.where(peak, 0.1907, 0.1419)
    pv = np.clip(16 * 295 * 0.92 * pv_scale * np.exp(-((h - 13) ** 2) / 9), 0, None)
    load = np.full(N, 350.0)
    load[(h >= 7) & (h < 9)] = 700.0
    load[(h >= 18) & (h < 22)] = 900.0
    if outdoor_swing:
        outdoor = 4 + 12 * np.clip(np.sin((h - 6) / 24 * 2 * np.pi), 0, None)
    else:
        outdoor = np.full(N, 8.0)
    df = pd.DataFrame(
        {
            "unit_load_cost": price,
            "unit_prod_price": np.full(N, export_price),
            "outdoor_temperature_forecast": outdoor,
            "ghi": np.clip(pv / 3.5, 0, None),
        },
        index=idx,
    )
    df.index.freq = "30min"
    return df, pv, load, price.tolist(), gas_price


def _band_violation(series, lo, hi, tol=0.5):
    """Largest excursion (C) of `series` outside [lo, hi]; 0 if within band."""
    s = np.asarray(series, dtype=float)
    below = np.maximum(np.asarray(lo, dtype=float) - s, 0.0)
    above = np.maximum(s - np.asarray(hi, dtype=float), 0.0)
    worst = float(max(below.max(), above.max()))
    return worst if worst > tol else 0.0


async def run_once(topology, overrides, scenario_kwargs, tank_starts, N, cop_solver):
    """One solve. Returns a behavioural dict. Never raises - errors are reported."""
    cap = _Capture()
    LOGGER.addHandler(cap)
    try:
        df, pv, load, price_list, gas_price = scenario(N=N, **(scenario_kwargs or {}))
        config = await build_config(EMHASS_CONF, LOGGER, EMHASS_CONF["defaults_path"])
        _, secrets = await build_secrets(EMHASS_CONF, LOGGER, no_response=True)
        params = await build_params(EMHASS_CONF, secrets, config, LOGGER)
        params["optim_conf"]["set_use_pv"] = True
        params["optim_conf"]["cop_solver"] = cop_solver
        for k, v in (overrides or {}).items():
            params["optim_conf"][k] = v
        pj = orjson.dumps(params).decode("utf-8")
        rhc, oc, pc = get_yaml_parse(pj, LOGGER)
        # Let the topology reference the live price/gas tracks if it asks to.
        topo = json.loads(json.dumps(topology))  # deep copy
        if "cost_tracks" in topo:
            topo["cost_tracks"].setdefault("electricity", price_list)
            topo["cost_tracks"].setdefault("gas", [gas_price] * N)
        rtp = {"heat_topology": topo}
        _, _, oc, _ = await treat_runtimeparams(
            orjson.dumps(rtp).decode("utf-8"), pj, rhc, oc, pc, "dayahead-optim", LOGGER, EMHASS_CONF
        )
        opt = Optimization(
            rhc, oc, pc, "unit_load_cost", "unit_prod_price", "profit",
            EMHASS_CONF, LOGGER, num_timesteps=N,
        )
        res = opt.perform_optimization(
            df, pv, load, df["unit_load_cost"].values, df["unit_prod_price"].values
        )
        status = str(opt.optim_status)

        # Match each storage to its temp column by closest start temperature.
        # Degenerate (all-zero / constant) columns are excluded from matching: a
        # relaxed-LP fallback can emit a zeroed predicted_temp column that would
        # otherwise be mis-matched to a tank and reported as a spurious violation.
        # If the best match's start still deviates from the expected start, the
        # match is flagged uncertain rather than silently trusted.
        all_temp_cols = [c for c in res.columns if "predicted_temp_heater" in c]
        temp_cols = [c for c in all_temp_cols if not np.allclose(res[c].to_numpy(), 0.0)] or all_temp_cols
        storages = topo.get("storage", [])
        tanks = {}
        tank_series = {}
        band_violations = {}
        match_warnings = []
        for st in storages:
            tid = st["id"]
            start = tank_starts.get(tid, st.get("start_temperature", 20.0))
            col = min(temp_cols, key=lambda c: abs(res[c].to_numpy()[0] - start), default=None)
            if col is None:
                continue
            s = res[col].to_numpy()
            tank_series[tid] = s
            start_mismatch = abs(float(s[0]) - float(start))
            if start_mismatch > 2.0:
                match_warnings.append(
                    f"tank '{tid}': matched column {col} starts at {float(s[0]):.1f} "
                    f"but expected start {float(start):.1f} (mismatch {start_mismatch:.1f}C) "
                    f"- band check unreliable, likely a relaxed/degenerate solve"
                )
            tanks[tid] = {
                "start": round(float(s[0]), 2),
                "min": round(float(np.min(s)), 2),
                "max": round(float(np.max(s)), 2),
                "peak": round(float(np.max(s)), 2),
                "total_variation": round(float(np.abs(np.diff(s)).sum()), 1),
                "start_mismatch_c": round(start_mismatch, 2),
            }
            lo = st.get("min_temperature", st.get("min_temperatures", -1e9))
            hi = st.get("max_temperature", st.get("max_temperatures", 1e9))
            # Only trust the band check when the column matched cleanly.
            band_violations[tid] = round(_band_violation(s, lo, hi), 2) if start_mismatch <= 2.0 else None

        dump_dir = __import__("os").environ.get("EMHASS_DUMP_DIR")
        if dump_dir:
            p = pathlib.Path(dump_dir)
            p.mkdir(parents=True, exist_ok=True)
            res.to_csv(p / f"{cop_solver}_dump.csv")

        grid = res["P_grid"].to_numpy() if "P_grid" in res else np.zeros(N)
        gpos = res["P_grid_pos"].to_numpy() if "P_grid_pos" in res else np.maximum(grid, 0)
        gneg = res["P_grid_neg"].to_numpy() if "P_grid_neg" in res else np.minimum(grid, 0)
        def_cols = sorted(c for c in res.columns if c.startswith("P_deferrable"))
        defs = {c: round(float(res[c].to_numpy().sum() * DT_H / 1000), 2) for c in def_cols}

        # Cheap realised-cost proxy: grid import energy x tariff (export credited at
        # prod price) + gas commodity. NOT the solver objective; a comparable scalar.
        import_cost = float(np.sum(np.maximum(grid, 0) / 1000 * DT_H * df["unit_load_cost"].values))
        export_credit = float(np.sum(np.maximum(-grid, 0) / 1000 * DT_H * df["unit_prod_price"].values))

        # Raw per-step data for the fair re-costing of the static schedule under the
        # TRUE (achieved-temperature) COP. The heating-curve HP entries carry the
        # OPTIMISTIC COP the solve used (cop_static) plus carnot/approach/load_idx -
        # only populated in auto mode (entries are built when cop_solver != static),
        # but those source properties are identical in both runs, so run_pair reads
        # them from the auto run and applies them to the static schedule.
        hp_loads = []
        for e in getattr(opt, "_dp_tank_entries", []) or []:
            h = e.get("hp") or {}
            if h.get("cop_static") is None:
                continue
            hp_loads.append({
                "tank_id": e.get("tank_id"),
                "load_idx": int(h["load_idx"]),
                "carnot": float(h["carnot"]),
                "approach": float(h["approach"]),
                "cop_static": [float(x) for x in np.asarray(h["cop_static"], dtype=float)[:N]],
            })
        def_power = {}
        for c in def_cols:
            try:
                def_power[int(c.replace("P_deferrable", ""))] = res[c].to_numpy()
            except ValueError:
                continue

        dp_events = _parse_dp_events(cap.messages)
        trusted = [v for v in band_violations.values() if v is not None]
        return {
            "ok": True,
            "cop_solver": cop_solver,
            "optim_status": status,
            "feasible": "Optimal" in status or "optimal" in status,
            "tanks": tanks,
            "band_violation_c": band_violations,
            "max_band_violation_c": round(max(trusted), 2) if trusted else 0.0,
            "match_warnings": match_warnings,
            "grid_peak_import_w": round(float(np.max(gpos)), 0),
            "pv_export_kwh": round(float(np.sum(np.maximum(-gneg, 0)) * DT_H / 1000), 2),
            "deferrable_kwh": defs,
            "cost_proxy_eur": round(import_cost - export_credit, 4),
            "dp_events": dp_events,
            "solve_seconds": round(float(getattr(opt, "_dp_solve_seconds", 0.0)), 2),
            "_raw": {
                "grid": grid,
                "tariff": np.asarray(df["unit_load_cost"].values, dtype=float)[:N],
                "prod_price": np.asarray(df["unit_prod_price"].values, dtype=float)[:N],
                "outdoor": np.asarray(df["outdoor_temperature_forecast"].values, dtype=float)[:N],
                "tank_temps": tank_series,
                "def_power": def_power,
                "hp_loads": hp_loads,
                "capacity_cost_per_kw": float((overrides or {}).get("capacity_cost_per_kw", 0.0)),
            },
        }
    except Exception as exc:  # report, never crash the batch
        import traceback
        return {
            "ok": False,
            "cop_solver": cop_solver,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-1500:],
            "dp_events": _parse_dp_events(cap.messages),
        }
    finally:
        LOGGER.removeHandler(cap)


def _parse_dp_events(messages):
    """Extract the DP's own decisions from captured log lines."""
    ev = {"eligible": [], "engaged": [], "skipped": [], "capped": [], "failed": [], "raw": []}
    for m in messages:
        if "DP COP solver (mode=" in m and "eligible" in m:
            ev["eligible"].append(m)
            ev["raw"].append(m)
        elif "DP COP refinement on tank" in m and "re-optimised" in m:
            ev["engaged"].append(m)
            ev["raw"].append(m)
        elif "COP already consistent" in m and "skipped" in m:
            ev["skipped"].append(m)
            ev["raw"].append(m)
        elif "cannot " in m and "capping it at" in m:
            ev["capped"].append(m)
            ev["raw"].append(m)
        elif "DP COP refinement failed" in m:
            ev["failed"].append(m)
            ev["raw"].append(m)
    return ev


def _cost_from_grid(grid, tariff, prod_price, capacity_cost):
    """Total EUR for a signed per-step grid array (W): energy (import x tariff,
    export credited at prod price) + capacity charge (capacity_cost x peak kW)."""
    grid = np.asarray(grid, dtype=float)
    tariff = np.asarray(tariff, dtype=float)
    prod_price = np.asarray(prod_price, dtype=float)
    imp = np.maximum(grid, 0.0)
    exp = np.maximum(-grid, 0.0)
    m = min(len(grid), len(tariff), len(prod_price))
    energy = float(np.sum(imp[:m] / 1000 * DT_H * tariff[:m]) - np.sum(exp[:m] / 1000 * DT_H * prod_price[:m]))
    peak = float(imp.max()) if len(imp) else 0.0
    cap = capacity_cost * peak / 1000.0
    return {"peak_w": round(peak, 0), "energy_eur": round(energy, 4),
            "capacity_eur": round(cap, 4), "total_eur": round(energy + cap, 4)}


def _recost_static_true(auto_raw, static_raw):
    """Re-cost the STATIC schedule under the TRUE (achieved-temperature) COP.

    The static solve prices heating-curve heat pumps with an OPTIMISTIC COP (taken at
    the curve supply, which can sit well below the achieved tank temperature), so its
    reported electricity / grid peak understate what executing that schedule really
    draws - the controller chases the temperature setpoints, drawing whatever
    electricity the true COP demands. For each heating-curve HP load:

        true_elec = elec_static * cop_static / cop_real

    where cop_real is the COP at the achieved tank temperature. Non-HP loads (gas,
    boosters, fixed-supply HPs) have temperature-independent COPs and are unchanged.
    Returns the static schedule's true cost and the auto plan's cost (already true,
    because the re-solve uses the corrected COP) on the same basis.
    """
    cap_cost = static_raw.get("capacity_cost_per_kw", 0.0)
    outdoor = np.asarray(static_raw["outdoor"], dtype=float)
    grid = np.asarray(static_raw["grid"], dtype=float).copy()
    n = len(grid)
    delta = np.zeros(n)
    recosted = []
    for hp in auto_raw.get("hp_loads", []):
        temps = static_raw["tank_temps"].get(hp["tank_id"])
        elec = static_raw["def_power"].get(hp["load_idx"])
        if temps is None or elec is None:
            continue
        temps = np.asarray(temps, dtype=float)[:n]
        elec = np.asarray(elec, dtype=float)[:n]
        cop_static = np.asarray(hp["cop_static"], dtype=float)[:n]
        cop_real = np.asarray(
            utils.cop_from_tank_temperature(temps, hp["carnot"], outdoor[:n], approach=hp["approach"]),
            dtype=float,
        )
        mn = min(len(elec), len(cop_static), len(cop_real), n)
        true_elec = elec[:mn] * cop_static[:mn] / np.maximum(cop_real[:mn], 1e-6)
        delta[:mn] += true_elec - elec[:mn]
        recosted.append(hp["tank_id"])
    static_true = _cost_from_grid(grid + delta, static_raw["tariff"], static_raw["prod_price"], cap_cost)
    auto_true = _cost_from_grid(auto_raw["grid"], auto_raw["tariff"], auto_raw["prod_price"], cap_cost)
    return static_true, auto_true, recosted


async def run_pair(spec, N=48):
    """Run a spec with the DP ON and OFF and diff the two."""
    topo = spec["topology"]
    ov = spec.get("overrides", {})
    sc = spec.get("scenario", {})
    starts = spec.get("tank_starts", {})
    auto = await run_once(topo, ov, sc, starts, N, "auto")
    static = await run_once(topo, ov, sc, starts, N, "static")
    delta = {}
    fair = {}
    if auto.get("ok") and static.get("ok"):
        delta = {
            "cost_proxy_delta_eur": round(auto["cost_proxy_eur"] - static["cost_proxy_eur"], 4),
            "grid_peak_delta_w": round(auto["grid_peak_import_w"] - static["grid_peak_import_w"], 0),
            "dp_engaged_tanks": len(auto["dp_events"]["engaged"]),
            "dp_capped_tanks": len(auto["dp_events"]["capped"]),
            "auto_max_band_violation_c": auto["max_band_violation_c"],
            "static_max_band_violation_c": static["max_band_violation_c"],
        }
        if "_raw" in auto and "_raw" in static and auto["feasible"] and static["feasible"]:
            # The apples-to-apples comparison: re-cost the static schedule under the
            # true COP (the `delta` above compares auto's honest peak/cost against
            # static's optimistic-COP self-report, which understates static). Requires
            # BOTH runs to have solved cleanly - re-costing a timed-out (User_Limit) or
            # infeasible static schedule against a degenerate trajectory is meaningless.
            static_true, auto_true, recosted = _recost_static_true(auto["_raw"], static["_raw"])
            fair = {
                "basis": "both under TRUE COP (static schedule re-costed; auto already true)",
                "recosted_hp_tanks": recosted,
                "static_true": static_true,
                "auto_true": auto_true,
                "cost_delta_eur": round(auto_true["total_eur"] - static_true["total_eur"], 4),
                "peak_delta_w": round(auto_true["peak_w"] - static_true["peak_w"], 0),
                "dp_helps_cost": auto_true["total_eur"] <= static_true["total_eur"] + 1e-9,
            }
        else:
            fair = {"basis": "n/a", "reason": (
                f"auto={auto.get('optim_status')} static={static.get('optim_status')} "
                "- fair re-costing needs both runs to solve cleanly")}
    # Drop the bulky (non-JSON) raw arrays now that re-costing is done.
    auto.pop("_raw", None)
    static.pop("_raw", None)
    return {
        "name": spec.get("name", "inline"),
        "hypothesis": spec.get("hypothesis", ""),
        "limit_probed": spec.get("limit_probed", ""),
        "pass_criteria": spec.get("pass_criteria", ""),
        "auto": auto,
        "static": static,
        "delta": delta,
        "fair_delta": fair,
    }


# ---------------------------------------------------------------------------
# Topology builders. Defaults match scripts/shadow_run_pi.py; experiments
# override only what they probe so the schema stays correct.
# ---------------------------------------------------------------------------

def hp(id="hp", nominal=3000, max_supply=55, slope=-1.0, offset=38, min_supply=28,
       carnot=0.45, cost_track="electricity"):
    return {
        "id": id, "type": "heatpump", "nominal_power": nominal, "min_power": 0,
        "treat_as_semi_cont": False, "carnot_efficiency": carnot,
        "heating_curve": {"slope": slope, "offset": offset, "min_supply": min_supply,
                          "max_supply": max_supply},
        "max_supply_temperature": max_supply, "cost_track": cost_track,
    }


def gas(id="gas", nominal=38000, min_power=4400, efficiency=0.92, startup_penalty=0.3,
        cost_track="gas"):
    return {
        "id": id, "type": "gas", "efficiency": efficiency, "nominal_power": nominal,
        "min_power": min_power, "treat_as_semi_cont": False, "cost_track": cost_track,
        "startup_penalty": startup_penalty,
    }


def tank(id, start, lo, hi, desired, N=48, volume=None, thermal_mass=None,
         loss=0.10, loss_coefficient=None, penalty=10):
    t = {"id": id, "start_temperature": start, "desired_temperature": desired,
         "min_temperature": [lo] * N, "max_temperature": [hi] * N, "penalty_factor": penalty}
    if volume is not None:
        t["volume"] = volume
        t["thermal_loss"] = loss
    if thermal_mass is not None:
        t["thermal_mass"] = thermal_mass
        t["loss_coefficient"] = loss_coefficient if loss_coefficient is not None else 0.2
    return t


# Scenarios are added by the registry file; harness exposes the primitives.
SCENARIOS = {}


def register(name, builder):
    SCENARIOS[name] = builder


def _load_builtin_scenarios():
    try:
        from scripts.dp_experiments import scenarios as _s  # noqa
        _s.populate(register, hp, gas, tank, scenario)
    except Exception:
        # Allow running with --spec even if the scenario module is absent.
        try:
            import scenarios as _s  # type: ignore
            _s.populate(register, hp, gas, tank, scenario)
        except Exception:
            pass


def main():
    _load_builtin_scenarios()
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if sys.argv[1] == "--list":
        for k in sorted(SCENARIOS):
            print(k)
        return
    N = 48
    if "--n" in sys.argv:
        N = int(sys.argv[sys.argv.index("--n") + 1])
    if sys.argv[1] == "--spec":
        spec = json.loads(pathlib.Path(sys.argv[2]).read_text())
    else:
        name = sys.argv[1]
        if name not in SCENARIOS:
            print(json.dumps({"ok": False, "error": f"unknown scenario {name}"}))
            return
        spec = SCENARIOS[name]()
        spec.setdefault("name", name)
    result = asyncio.run(run_pair(spec, N=N))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
