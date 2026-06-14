# 🔥 Thermal Integration

EMHASS does not treat heat as an afterthought bolted onto the electrical
optimization: a thermal store is a first-class part of the same plan. Whether it
is a domestic-hot-water (DHW) tank, a space-heating buffer, a swimming pool, or
the thermal mass of the house itself, EMHASS models it as **a temperature it
steers through time**, charged by one or more heat sources, inside a comfort
band you define. The optimizer then decides *when* to make heat - banking it on
cheap power or surplus PV and coasting through price peaks - exactly as it does
for a battery's state of charge.

## One model, two faces

Historically EMHASS had two separate thermal models: a heat-pump **water tank**
(temperature-dependent COP, hot-water draw-off) and an **RC building zone**
(thermal mass, heat loss to outdoor, comfort band). These are now the **same
underlying model** - a thermal mass with a temperature state, a loss term, a
demand term, and one or more sources - and the differences are just which
options you set:

| Concept | Water tank | Building zone |
| --- | --- | --- |
| Heat capacity | from `volume` (water) | `thermal_mass` (kWh/K) directly |
| Standing loss | flat hot-water loss | state-dependent `loss_coefficient` $UA\,(T-T_{out})$ |
| Demand | `draw_off` profile | building physics / heat loss |
| Sources | heat pump, boiler, element | the same hybrid sources |

Because it is one model, a single store can be **both** at once (a combi-tank
that serves hot water *and* space heating), and a building zone can be fed by the
same temperature-dependent heat pump as a tank.

## Three ways to configure it

Pick the simplest description that fits your system - they all compile to the
same primitives:

- **[Thermal battery](thermal_battery.md)** - one heat pump charging one store,
  with a temperature-dependent COP and an optional hot-water draw-off. The
  simplest case; start here if you have a single tank and a single source.
- **[Deferrable load thermal model](thermal_model.md)** - one source heating one
  building zone (thermal mass + heat loss + inertia + a comfort band). The
  load-shifting "house as a battery" model.
- **[Heat topology graph model](heat_topology.md)** - the general form. Describe a
  small graph of **sources** (heat pump, gas boiler, electric element), **stores**
  (DHW, buffer, pool, house zone), **flows** between them, and **transfers** from
  one store to another. Use this for hybrid systems: more than one source, more
  than one store, sources priced against different commodities (electricity vs
  gas), or a buffer that distributes heat to several zones. The two models above
  are special cases of it.

## Temperature-dependent COP and global optimality

A heat pump's efficiency is not constant: the hotter it has to push the store,
the lower its COP. That makes "deliver heat $Q$" a **non-convex** decision - the
electricity it costs depends on the temperature you choose - which a single
linear program cannot solve exactly. EMHASS handles it with a two-stage scheme:
the linear program plans against a linearized COP, then an exact
**dynamic-programming (DP) refinement** checks whether the temperature it landed
on is consistent with the COP it assumed, and if not re-solves the store's
temperature trajectory against the *true* temperature-dependent COP. This is what
lets the optimizer safely **super-heat a buffer into surplus PV** without being
fooled by an over-optimistic COP. The DP runs automatically only when it is
needed and is a no-op otherwise.

The mechanics - the COP non-convexity, the DP refinement, the PV marginal price,
the shared-tank constraints, and the start-temperature recovery - are documented
in [the mathematical model](advanced_math_model.md#thermal-storage-and-heat-pumps).

```{toctree}
:maxdepth: 2
thermal_model
thermal_battery
heat_topology
```
