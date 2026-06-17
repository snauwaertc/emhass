"""Shadow run of the hybrid-heating branch on the Pi: the REAL future topology -
a heat pump and a gas boiler that can each heat a 200 L DHW tank and a 100 L
buffer, with the buffer distributing heat to a pool (coupled tank) and the house
(building zone). On the real two-tier day/night tariff plus a flat gas commodity
price, with the real PV array.

There is NO electric booster: the only backup is gas (priced on its own track,
off the electric balance and the capacity tariff). The heat pump is the future
addition whose temperature-dependent COP the DP refinement targets.

Produces an optimization plan for inspection ONLY. Nothing is published to Home
Assistant and nothing controls the heating - this is a parallel shadow.

A spring day is used on purpose: a midday PV surplus and a cold-dawn -> mild-midday
outdoor swing exercise the DP COP refinement's marginal-price (super-heat into PV)
and per-step-outdoor COP paths. Pool/house physics are illustrative placeholders
(sizes the user can refine); the DHW (200 L) and buffer (100 L) are the real ones.

Run on the Pi:  .venv/bin/python scripts/shadow_run_pi.py
"""

import asyncio
import os
import pathlib
import sys

import numpy as np
import orjson
import pandas as pd

from emhass.optimization import Optimization
from emhass.utils import (
    build_config,
    build_params,
    build_secrets,
    get_logger,
    get_yaml_parse,
    treat_runtimeparams,
)

root = pathlib.Path(__file__).resolve().parent.parent
emhass_conf = {
    "data_path": root / "data/",
    "root_path": root / "src/emhass/",
}
emhass_conf["defaults_path"] = emhass_conf["root_path"] / "data/config_defaults.json"
emhass_conf["associations_path"] = emhass_conf["root_path"] / "data/associations.csv"
logger, _ = get_logger(__name__, emhass_conf, save_to_file=False)

# Horizon in 30-min steps: 48 = 24 h (default), pass 96 on the CLI for a 48 h forecast.
N = int(sys.argv[1]) if len(sys.argv) > 1 else 48
DT_H = 0.5

# Real two-tier tariff from the live config.json (heures pleines / creuses)
OFFPEAK, PEAK = 0.1419, 0.1907
PEAK_WINDOWS = [(2.9, 15.4), (17.4, 20.4)]  # 02:54-15:24 and 17:24-20:24
GAS_PRICE = 0.11   # EUR per kWh of gas INPUT (boiler efficiency applied separately)
EXPORT_PRICE = 0.05  # low feed-in: super-heating into PV surplus is nearly free
PV_WP = 16 * 295   # the real array: 16 x CSUN 295 W ~= 4.7 kWp


def scenario():
    idx = pd.date_range("2026-04-15 00:00", periods=N, freq="30min", tz="Europe/Brussels")
    h = np.array([t.hour + t.minute / 60 for t in idx])
    price = np.where(
        np.any([(h >= a) & (h < b) for a, b in PEAK_WINDOWS], axis=0), PEAK, OFFPEAK
    )
    # Spring PV bell - generous midday so the system exports (and can super-heat into it)
    pv = np.clip(PV_WP * 0.92 * np.exp(-((h - 13) ** 2) / 9), 0, None)
    load = np.full(N, 350.0)
    load[(h >= 7) & (h < 9)] = 700.0
    load[(h >= 18) & (h < 22)] = 900.0
    # Cold dawn -> mild midday -> cool evening: a clear outdoor swing (drives COP)
    outdoor = 4 + 12 * np.clip(np.sin((h - 6) / 24 * 2 * np.pi), 0, None)
    df = pd.DataFrame(
        {
            "unit_load_cost": price,
            "unit_prod_price": np.full(N, EXPORT_PRICE),
            "outdoor_temperature_forecast": outdoor,
            "ghi": np.clip(pv / 3.5, 0, None),
        },
        index=idx,
    )
    df.index.freq = "30min"
    return df, pv, load, price.tolist()


def topology(price_list):
    # DHW draw-off (showers): morning (~07:00) and evening (~19:00) each day, so the
    # pattern repeats over a multi-day horizon (step i % 48 keys the time of day).
    draw_off = [1.0 if (i % 48) in (14, 15, 38, 39) else 0.0 for i in range(N)]
    gas_track = [GAS_PRICE] * N
    topo = {
        "sources": [
            {
                "id": "hp", "type": "heatpump", "nominal_power": 3000, "min_power": 0,
                "treat_as_semi_cont": False, "carnot_efficiency": 0.45,
                "heating_curve": {"slope": -1.0, "offset": 38, "min_supply": 28, "max_supply": 55},
                "max_supply_temperature": 55,  # condenser ceiling; gas tops the DHW above it
                "cost_track": "electricity",
            },
            {
                # Real unit: Vaillant ecoTEC plus VC 35 CS/1-5 (35 kW solo condensing).
                # Datasheet: max output 34.9 kW @ 80/60, modulation ~11.5% (turndown ~1:9).
                # p_deferrable models gas INPUT (fuel); delivered heat = efficiency * input,
                # so nominal_power = 34.9/0.92 ~= 38 kW input, floor = 4.0/0.92 ~= 4.4 kW input.
                # min_power > 0 with treat_as_semi_cont False = "off, or modulate 4.4-38 kW":
                # the boiler physically cannot trickle below its floor (it cycles instead).
                # startup_penalty prices each off->on switch: on the gas-only buffer it
                # cuts 11 short burns to 2 (oscillation -66%) for ~+2.4% gas cost. 0.3 is
                # tuned to this scenario's objective scale; re-tune on real demand data.
                "id": "gas", "type": "gas", "efficiency": 0.92, "nominal_power": 38000,
                "min_power": 4400, "treat_as_semi_cont": False, "cost_track": "gas",
                "startup_penalty": 0.3,
            },
        ],
        "storage": [
            {  # 200 L DHW (real)
                "id": "dhw", "volume": 0.20, "start_temperature": 50,
                "thermal_loss": 0.10, "min_temperature": [45.0] * N,
                "max_temperature": [62.0] * N, "desired_temperature": 52, "penalty_factor": 30,
            },
            {  # 100 L buffer (real) - distributes to pool + house
                "id": "buffer", "volume": 0.10, "start_temperature": 38,
                "thermal_loss": 0.08, "min_temperature": [30.0] * N,
                "max_temperature": [52.0] * N, "desired_temperature": 35, "penalty_factor": 5,
            },
            {  # pool - coupled tank (illustrative size); loose floor, soft target, solar gain
                "id": "pool", "thermal_mass": 50.0, "loss_coefficient": 0.20,
                "start_temperature": 26, "min_temperature": [18.0] * N,
                "max_temperature": [30.0] * N, "desired_temperature": 26, "penalty_factor": 5,
            },
            {  # house - building zone (illustrative RC); comfort band 19-23
                "id": "house", "thermal_mass": 10.0, "loss_coefficient": 0.25,
                "start_temperature": 20, "min_temperature": [19.0] * N,
                "max_temperature": [23.0] * N, "desired_temperature": 20.5, "penalty_factor": 20,
            },
        ],
        "consumers": [
            {"id": "showers", "target": "dhw", "type": "profile", "profile": draw_off},
            {"id": "pool_solar", "target": "pool", "type": "pool_comfort",
             "solar_absorption_area": 30.0, "solar_absorption_factor": 0.7},
        ],
        "flows": [
            {"from": "hp", "to": "buffer"},
            {"from": "hp", "to": "dhw"},
            {"from": "gas", "to": "buffer"},
            {"from": "gas", "to": "dhw"},
            {"from": "buffer", "to": "pool", "transfer_coefficient": 0.5, "max_transfer_power": 4000},
            {"from": "buffer", "to": "house", "transfer_coefficient": 0.3, "max_transfer_power": 6000},
        ],
        "cost_tracks": {
            "electricity": price_list,
            "gas": gas_track,
        },
        "actuator_groups": [
            {"flows": [["hp", "buffer"], ["hp", "dhw"]], "mutual_exclusion": True},
            {"flows": [["gas", "buffer"], ["gas", "dhw"]], "mutual_exclusion": True},
        ],
    }
    # EMHASS_GAS_ONLY=1 reproduces the user's CURRENT setup (heat pump not yet
    # installed): drop the hp source, its flows, and its actuator group, leaving
    # the 35 kW gas boiler as the sole source feeding the 100 L buffer.
    if os.environ.get("EMHASS_GAS_ONLY"):
        topo["sources"] = [s for s in topo["sources"] if s["id"] != "hp"]
        topo["flows"] = [f for f in topo["flows"] if f["from"] != "hp"]
        topo["actuator_groups"] = [
            g for g in topo["actuator_groups"]
            if not any("hp" in flow for flow in g["flows"])
        ]
    return topo


async def main():
    df, pv, load, price_list = scenario()
    config = await build_config(emhass_conf, logger, emhass_conf["defaults_path"])
    _, secrets = await build_secrets(emhass_conf, logger, no_response=True)
    params = await build_params(emhass_conf, secrets, config, logger)
    params["optim_conf"]["set_use_pv"] = True  # mimic the PV array
    # Defaults come from config_defaults.json; these CLI args are optional ad-hoc
    # overrides: argv[2]=lp_solver_timeout (s), argv[3]=cop_solver,
    # argv[4]=lp_solver_mip_rel_gap (0 = prove exact optimum; >0 = accept near-optimal).
    if len(sys.argv) > 2:
        params["optim_conf"]["lp_solver_timeout"] = int(sys.argv[2])
    if len(sys.argv) > 3:
        params["optim_conf"]["cop_solver"] = sys.argv[3]
    if len(sys.argv) > 4:
        params["optim_conf"]["lp_solver_mip_rel_gap"] = float(sys.argv[4])
    pj = orjson.dumps(params).decode("utf-8")
    rhc, oc, pc = get_yaml_parse(pj, logger)
    rtp = {"heat_topology": topology(price_list)}
    _, _, oc, _ = await treat_runtimeparams(
        orjson.dumps(rtp).decode("utf-8"), pj, rhc, oc, pc, "dayahead-optim", logger, emhass_conf
    )
    # Optional gas-boiler startup penalty (argv[5]): each on-switch costs
    # scale*penalty*nominal_power*unit_load_cost, discouraging short-cycling.
    # The compiler sized set_deferrable_startup_penalty to [0]*4; override the
    # gas loads only (2 = gas->buffer, 3 = gas->dhw); the HP loads stay at 0.
    # The gas source carries startup_penalty: 0.3 via the topology (compiled
    # natively). argv[5] / argv[6] override the gas loads for sweeps: argv[5] =
    # startup penalty, argv[6] = max_startups hard cap. Both target the gas
    # (non-electric) loads via is_electric_load, so they work in gas-only too.
    elec = oc.get("is_electric_load", [True] * oc["number_of_deferrable_loads"])
    if len(sys.argv) > 5:
        pen = float(sys.argv[5])
        oc["set_deferrable_startup_penalty"] = [0.0 if e else pen for e in elec]
    if len(sys.argv) > 6:
        cap = int(sys.argv[6])
        oc["set_deferrable_max_startups"] = [0 if e else cap for e in elec]
    opt = Optimization(rhc, oc, pc, "unit_load_cost", "unit_prod_price", "profit",
                       emhass_conf, logger, num_timesteps=N)
    res = opt.perform_optimization(
        df, pv, load, df["unit_load_cost"].values, df["unit_prod_price"].values
    )
    print("SHADOW RUN - hybrid HP + gas, DHW(200L) + buffer(100L) -> pool + house")
    print("optim_status =", opt.optim_status)
    # EMHASS_DUMP_CSV=<path> writes the full per-step result for trace inspection.
    dump = os.environ.get("EMHASS_DUMP_CSV")
    if dump:
        res.to_csv(dump)
        print(f"  (full result written to {dump})")
    # Loads, in flow order: 0 hp->buffer, 1 hp->dhw, 2 gas->buffer, 3 gas->dhw
    cols = {c.lower(): c for c in res.columns}

    def series(name):
        return res[cols[name.lower()]].to_numpy() if name.lower() in cols else np.zeros(N)

    hp_buf, hp_dhw = series("P_deferrable0"), series("P_deferrable1")
    gas_buf, gas_dhw = series("P_deferrable2"), series("P_deferrable3")
    # Temperature columns are named predicted_temp_heater{load_idx}, not by tank id;
    # match each tank to the column whose first value matches its start temperature
    # (dhw 50, buffer 38, pool 26, house 20 are all distinct).
    temp_cols = [c for c in res.columns if "predicted_temp_heater" in c]
    starts = {"dhw": 50.0, "buffer": 38.0, "pool": 26.0, "house": 20.0}
    tcol = {
        tid: min(temp_cols, key=lambda c: abs(res[c].to_numpy()[0] - st), default=None)
        for tid, st in starts.items()
    }
    exp = res["P_grid_neg"].to_numpy() if "P_grid_neg" in res else np.zeros(N)

    hdr = f"  {'time':>5}{'price':>7}{'PV':>6}{'exp':>6}{'HPbuf':>6}{'HPdhw':>6}{'GASbf':>6}{'GASdhw':>7}"
    for tid in ("dhw", "buffer", "pool", "house"):
        hdr += f"{tid[:4]:>6}"
    print(hdr)
    for i in range(0, N, 2):
        t = df.index[i].strftime("%H:%M")
        row = (f"  {t:>5}{df['unit_load_cost'].iloc[i]:>7.4f}{pv[i]:>6.0f}{-exp[i]:>6.0f}"
               f"{hp_buf[i]:>6.0f}{hp_dhw[i]:>6.0f}{gas_buf[i]:>6.0f}{gas_dhw[i]:>7.0f}")
        for tid in ("dhw", "buffer", "pool", "house"):
            c = tcol[tid]
            row += f"{(res[c].to_numpy()[i] if c else float('nan')):>6.1f}"
        print(row)
    print(f"\n  HP {(hp_buf + hp_dhw).sum() * DT_H / 1000:.1f} kWh elec, "
          f"gas input {(gas_buf + gas_dhw).sum() * DT_H / 1000:.1f} kWh, "
          f"PV export {(-exp).sum() * DT_H / 1000:.1f} kWh")

    # Objective smoothness metrics over ALL N steps (the 2-step table hides the
    # fine oscillation). A "start" is an off->on transition; total variation is the
    # summed absolute step-to-step change. Lower = smoother.
    def starts_and_runtime(p, floor=100.0):
        on = p > floor
        n_start = int(np.sum(on[1:] & ~on[:-1])) + int(on[0])
        return n_start, int(on.sum())

    def total_variation(name):
        c = tcol[name]
        if not c:
            return float("nan")
        s = res[c].to_numpy()
        return float(np.abs(np.diff(s)).sum())

    gb_starts, gb_on = starts_and_runtime(gas_buf)
    gd_starts, gd_on = starts_and_runtime(gas_dhw)
    print(f"  smoothness: gas->buffer {gb_starts} starts / {gb_on} on-steps, "
          f"gas->dhw {gd_starts} starts / {gd_on} on-steps")
    print(f"              temp total-variation (sum|dT|): "
          f"buffer {total_variation('buffer'):.1f}C, dhw {total_variation('dhw'):.1f}C")
    print("  (shadow only - not published to HA, not controlling anything)")


if __name__ == "__main__":
    asyncio.run(main())
