"""Does the horizon length decide whether the optimiser pre-charges for tomorrow's
price peak?

The live Pi shadow runs a 24h (48-step) day-ahead horizon. On a day where the real
all-in price has a sharp peak TOMORROW evening (~0.63 EUR/kWh at ~20:00), that peak
sits ~3h beyond the 24h window, so the optimiser never sees it and never pre-charges
the thermal stores to coast it.

This script runs the SAME real HP+gas topology against the SAME chart-shaped price
curve (modest evening today ~0.31, a big peak tomorrow ~0.63, midday dips ~0.16) at
two horizons - 24h (peak out of window) and 48h (peak in window) - and prints the
peak-window dispatch (grid / HP / gas) and the pre-charge so the difference is visible.

Run:  PYTHONPATH=. .venv/bin/python scripts/dp_experiments/peak_horizon_test.py
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import numpy as np
import orjson
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import shadow_run_pi as S  # noqa: E402  (reuse its topology + emhass_conf + logger)

from emhass.optimization import Optimization  # noqa: E402
from emhass.utils import (  # noqa: E402
    build_config,
    build_params,
    build_secrets,
    get_yaml_parse,
    treat_runtimeparams,
)

TZ = "Europe/Brussels"
START = "2026-06-17 18:00"  # align to the live run's horizon start
DT_H = 0.5


def chart_price(hfs: float) -> float:
    """All-in EUR/kWh as a function of hours-from-start (18:00 today), shaped to the
    user's chart: modest evening today, a big peak TOMORROW ~19:00-21:00, midday dips."""
    seg = [
        (0, 4, 0.31, 0.31),    # today 18-22  modest evening
        (4, 13, 0.28, 0.27),   # tonight 22-07
        (13, 19, 0.27, 0.16),  # tomorrow 07-13  -> midday dip
        (19, 23, 0.16, 0.26),  # tomorrow 13-17
        (23, 25, 0.26, 0.45),  # tomorrow 17-19  ramp up
        (25, 27, 0.63, 0.63),  # tomorrow 19-21  PEAK
        (27, 29, 0.45, 0.31),  # tomorrow 21-23
        (29, 37, 0.28, 0.27),  # night
        (37, 44, 0.27, 0.18),  # day3 morning -> dip
        (44, 96, 0.18, 0.27),  # tail
    ]
    for a, b, va, vb in seg:
        if a <= hfs < b:
            return va + (vb - va) * (hfs - a) / (b - a)
    return 0.27


def scenario(n: int):
    idx = pd.date_range(START, periods=n, freq="30min", tz=TZ)
    h = np.array([t.hour + t.minute / 60 for t in idx])
    hfs = np.arange(n) * DT_H
    price = np.array([chart_price(x) for x in hfs])
    pv = np.clip(S.PV_WP * 0.92 * np.exp(-((h - 13) ** 2) / 9), 0, None)  # daily bell, both days
    load = np.full(n, 350.0)
    load[(h >= 7) & (h < 9)] = 700.0
    load[(h >= 18) & (h < 22)] = 900.0
    outdoor = 4 + 12 * np.clip(np.sin((h - 6) / 24 * 2 * np.pi), 0, None)
    df = pd.DataFrame(
        {
            "unit_load_cost": price,
            "unit_prod_price": np.full(n, 0.05),
            "outdoor_temperature_forecast": outdoor,
            "ghi": np.clip(pv / 3.5, 0, None),
        },
        index=idx,
    )
    df.index.freq = "30min"
    return df, pv, load, price.tolist()


async def run(n: int):
    df, pv, load, price_list = scenario(n)
    config = await build_config(S.emhass_conf, S.logger, S.emhass_conf["defaults_path"])
    _, secrets = await build_secrets(S.emhass_conf, S.logger, no_response=True)
    params = await build_params(S.emhass_conf, secrets, config, S.logger)
    params["optim_conf"]["set_use_pv"] = True
    params["optim_conf"]["lp_solver_mip_rel_gap"] = 0.06  # keep 96 steps tractable
    pj = orjson.dumps(params).decode("utf-8")
    rhc, oc, pc = get_yaml_parse(pj, S.logger)
    rtp = {"heat_topology": S.topology(price_list), "current_period_peak": 3790}
    _, _, oc, _ = await treat_runtimeparams(
        orjson.dumps(rtp).decode("utf-8"), pj, rhc, oc, pc, "dayahead-optim", S.logger, S.emhass_conf
    )
    opt = Optimization(
        rhc, oc, pc, "unit_load_cost", "unit_prod_price", "profit", S.emhass_conf, S.logger,
        num_timesteps=n,
    )
    res = opt.perform_optimization(
        df, pv, load, df["unit_load_cost"].values, df["unit_prod_price"].values
    )
    res.index = df.index
    return opt, res


def temp_col(res, start):
    cols = [c for c in res.columns if "predicted_temp_heater" in c]
    return min(cols, key=lambda c: abs(res[c].to_numpy()[0] - start), default=None)


def summarize(tag, opt, res):
    print(f"\n================ {tag} (status {opt.optim_status}) ================")
    defs = sorted(c for c in res.columns if c.startswith("P_deferrable"))
    # Identify the tomorrow-evening peak window present in this horizon.
    price = res["unit_load_cost"].to_numpy()
    pk = int(price.argmax())
    print(f"horizon: {res.index[0]:%m-%d %H:%M} -> {res.index[-1]:%m-%d %H:%M} "
          f"({len(res)} steps); max price {price[pk]:.3f} at {res.index[pk]:%m-%d %H:%M}")
    buf = temp_col(res, 38)
    dhw = temp_col(res, 50)
    # The real evening peak is tomorrow ~20:00. Report the window around it if in horizon.
    mask = [(t.day == res.index[0].day + 1) and (18 <= t.hour <= 22) for t in res.index]
    if any(mask):
        print("  -- tomorrow 18:00-22:00 (the 0.63 peak window) --")
        print("   time   price  P_grid   " + "  ".join(d[-3:] for d in defs) + "   buf   dhw")
        for t, m in zip(res.index, mask):
            if not m:
                continue
            r = res.loc[t]
            ds = "  ".join(f"{float(r[d]):5.0f}" for d in defs)
            print(f"  {t:%H:%M}  {float(r['unit_load_cost']):.3f} {float(r['P_grid']):6.0f}   {ds}"
                  f"   {float(r[buf]):4.1f}  {float(r[dhw]):4.1f}")
    else:
        print("  (tomorrow's 18:00-22:00 peak window is OUTSIDE this horizon - never seen)")
    # Pre-charge readout: buffer/DHW peak temp reached the day before the peak.
    print(f"  buffer span {res[buf].min():.0f}-{res[buf].max():.0f} C; "
          f"dhw span {res[dhw].min():.0f}-{res[dhw].max():.0f} C")


async def main():
    for n in (48, 96):
        opt, res = await run(n)
        summarize("24h horizon" if n == 48 else "48h horizon", opt, res)


if __name__ == "__main__":
    asyncio.run(main())
