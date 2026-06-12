# Heat topology graph model (hybrid heating)

The `heat_topology` parameter lets you describe a hybrid heating system as a small
directed graph instead of hand-rolling the flat deferrable-load arrays. When set,
EMHASS compiles the graph down to the primitives the optimizer already understands
(`def_load_config`, `shared_thermal_tanks`, `deferrable_load_groups`,
`cost_forecast_per_deferrable_load`, ...) so you do not have to keep a dozen
parallel lists index-aligned by hand.

A typical system it describes: a heat pump and a gas boiler that can both feed the
same buffer and the same domestic-hot-water (DHW) tank, each priced against its own
tariff, with the constraint that one source can only serve one target at a time.

```{note}
`heat_topology` is an advanced parameter. If you have a single heat source and a
single thermal store, the flat [thermal_battery](thermal_battery.md) configuration
is simpler and is what you want. Reach for the graph model when you have more than
one source, more than one store, or sources priced against different commodities.
```

## The model

A topology is a JSON object with five collections and one optional cost map:

| Key | Type | What it is |
| --- | --- | --- |
| `sources` | list | Heat producers (heat pump, gas boiler, ...). |
| `storage` | list | Thermal stores / buffers (each is a thermal battery). |
| `consumers` | list | Demand on a store (DHW draw-off, building heat loss, pool). |
| `flows` | list | A `source -> storage` edge. **Each flow becomes one deferrable load.** |
| `actuator_groups` | list | Optional. Couples flows that share one physical actuator (mutual exclusion / shared power cap). |
| `cost_tracks` | object | Optional. Named per-timestep cost arrays referenced by sources. |

The compiler turns this graph into flat `optim_conf` fields:

| Graph element | Compiles to |
| --- | --- |
| each `flow` | one deferrable load (with a `thermal_source` block in `def_load_config`) |
| each `storage` | one entry in `shared_thermal_tanks`, with `load_ids` pointing at the flows feeding it |
| each `consumer` | folded into its target storage (`draw_off_demand`, building physics, or pool solar gain) |
| each `actuator_group` | one entry in `deferrable_load_groups` |
| each source `cost_track` | one entry in `cost_forecast_per_deferrable_load` |
| source `type` | per-load `is_electric_load` (electric bus membership) |

Flows are numbered in the order they appear: the first flow is `deferrable0`, the
second `deferrable1`, and so on. Those names are what `actuator_groups` reference.

## Schema reference

### `sources`

Each source is one heat producer. Common fields:

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `id` | string | required | Unique across sources. |
| `type` | string | required | One of `heatpump`/`heat_pump`, `gas`, `oil`, `district`, `electric`, `constant_efficiency`. |
| `nominal_power` | number | `0` | Maximum electrical/thermal input power (W). |
| `min_power` | number | `0` | Minimum power when running (W). Use for modulating boilers whose floor is well above 0. |
| `treat_as_semi_cont` | bool | `true` | `true` = on/off only; `false` = modulating between `min_power` and `nominal_power`. |
| `operating_hours` | int | `4` | Target run hours over the horizon. |
| `electric` | bool | by type | Overrides bus membership. Defaults: heat pump / electric / constant_efficiency -> `true`; gas / oil / district -> `false`. |
| `cost_track` | string | none | Key into `cost_tracks`. Sets this load's per-timestep cost (gas tariff vs electricity tariff). |

**Heat-pump sources** (`heatpump` / `heat_pump`) additionally need a supply temperature,
which drives the Carnot COP:

- `heating_curve`: `{ "slope": .., "offset": .., "min_supply": 25, "max_supply": 70 }`
  (`slope` and `offset` required; weather-compensated supply temperature). Takes precedence
  if present.
- or `supply_temperature`: a constant supply temperature (used when no `heating_curve`).
- `carnot_efficiency`: COP efficiency factor, default `0.4`.

A heat-pump source must provide one of `heating_curve` or `supply_temperature`.

**Fuel / constant-efficiency sources** (`gas`, `oil`, `district`, `electric`,
`constant_efficiency`) instead need:

- `efficiency`: constant conversion efficiency (required).

Because gas/oil/district default to `electric: false`, those loads contribute only to
their thermal target, **not** to the electric power balance - which is exactly what
makes a gas boiler price against gas while the heat pump prices against electricity.

### `storage`

Each storage entry is a thermal store (buffer, DHW tank, pool, ...). It accepts the
same physics as a standalone [thermal_battery](thermal_battery.md):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `id` | string | required | Unique across storage. |
| `volume` | number | required | Litres. |
| `density` | number | `1000` | kg/m3 (use ~`997` for hot water). |
| `heat_capacity` | number | `4.186` | kJ/(kg.K). |
| `start_temperature` | number | `20.0` | Initial tank temperature (degC). |
| `thermal_loss` | number | `0.045` | Standing-loss coefficient. |
| `min_temperature` / `min_temperatures` | list | `[]` | Per-timestep hard floor (degC). |
| `max_temperature` / `max_temperatures` | list | `[]` | Per-timestep hard ceiling (degC). |
| `min_temperature_curve` | object | none | Weather-compensated floor `{slope, offset, min_supply, max_supply}` (same law as a heating curve). |

Optional soft-comfort fields (penalise deviation instead of hard bounds - useful for a
pool or any low-priority store):

| Field | Type | Notes |
| --- | --- | --- |
| `desired_temperature` / `desired_temperatures` | number or list | Comfort target (scalar is broadcast across the horizon). |
| `overshoot_temperature` | number | Allowed overshoot before penalty. |
| `penalty_factor` | number | Weight of the comfort penalty in the objective. |
| `comfort_sense` | string | `"heat"` or `"cool"`. |

### `consumers`

Each consumer puts demand on one storage. `target` must be a storage `id`. `type`
selects the demand model:

- `type: "profile"` - explicit draw-off: `profile` is a per-timestep demand list
  (kWh per step). Multiple `profile` consumers on the same storage are summed.
- `type: "building_demand"` - space-heating load computed from building physics. Any
  of: `u_value`, `envelope_area`, `ventilation_rate`, `heated_volume`,
  `indoor_target_temperature`, `window_area`, `shgc`, `internal_gains_factor`,
  `specific_heating_demand`, `area`, `base_temperature`, `annual_reference_hdd`.
  Only **one** `building_demand` is allowed per storage.
- `type: "pool_comfort"` - surface solar gain: `solar_absorption_area`,
  `solar_absorption_factor`.

See [thermal_battery.md](thermal_battery.md) for the meaning and calibration of the
building-physics and solar-gain fields.

### `flows`

Each flow is a `source -> storage` edge and becomes one deferrable load:

```json
{ "from": "<source id>", "to": "<storage id>" }
```

`from` must match a source `id` and `to` must match a storage `id`. The list order
sets the deferrable-load index (`deferrable0`, `deferrable1`, ...).

### `actuator_groups`

Optional. Use a group when several flows are driven by one physical device that can
only do one thing at a time (for example, a single heat pump that heats either the
buffer or the DHW tank, never both at once):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `flows` | list of `[from, to]` pairs | required | The flows in this group. |
| `mutual_exclusion` | bool | `false` | If `true`, at most one flow in the group runs per timestep. |
| `max_combined_power` | number | none | Shared power cap across the group's flows (W). |

### `cost_tracks`

Optional map of named per-timestep cost arrays (Currency/kWh) that sources reference
through `cost_track`. This is how each source gets its own tariff:

```text
"cost_tracks": {
  "electricity": [0.28, 0.26, ...],
  "gas":         [0.11, 0.11, ...]
}
```

## Worked example: heat pump + gas boiler, shared buffer and DHW

A heat pump and a modulating gas boiler can each feed a space-heating buffer and a
DHW tank. Each source can only serve one target at a time (mutual exclusion). The
heat pump is priced on electricity; the gas boiler on gas.

```json
{
  "sources": [
    {
      "id": "heatpump",
      "type": "heatpump",
      "nominal_power": 3000,
      "min_power": 500,
      "treat_as_semi_cont": false,
      "carnot_efficiency": 0.45,
      "heating_curve": { "slope": -1.0, "offset": 38, "min_supply": 28, "max_supply": 55 },
      "cost_track": "electricity"
    },
    {
      "id": "gasboiler",
      "type": "gas",
      "efficiency": 0.92,
      "nominal_power": 24000,
      "min_power": 6000,
      "treat_as_semi_cont": false,
      "cost_track": "gas"
    }
  ],
  "storage": [
    {
      "id": "buffer",
      "volume": 200,
      "start_temperature": 40,
      "min_temperature_curve": { "slope": -0.8, "offset": 30, "min_supply": 28, "max_supply": 55 },
      "max_temperature": [55, 55, 55, 55]
    },
    {
      "id": "dhw",
      "volume": 150,
      "density": 997,
      "start_temperature": 52,
      "min_temperature": [48, 48, 48, 48],
      "max_temperature": [62, 62, 62, 62]
    }
  ],
  "consumers": [
    {
      "id": "house",
      "target": "buffer",
      "type": "building_demand",
      "u_value": 0.6,
      "envelope_area": 320,
      "ventilation_rate": 0.5,
      "heated_volume": 400,
      "indoor_target_temperature": 20
    },
    {
      "id": "showers",
      "target": "dhw",
      "type": "profile",
      "profile": [0.0, 1.5, 0.0, 0.0]
    }
  ],
  "flows": [
    { "from": "heatpump",  "to": "buffer" },
    { "from": "heatpump",  "to": "dhw" },
    { "from": "gasboiler", "to": "buffer" },
    { "from": "gasboiler", "to": "dhw" }
  ],
  "cost_tracks": {
    "electricity": [0.28, 0.26, 0.30, 0.25],
    "gas":         [0.11, 0.11, 0.11, 0.11]
  },
  "actuator_groups": [
    { "flows": [["heatpump", "buffer"], ["heatpump", "dhw"]], "mutual_exclusion": true },
    { "flows": [["gasboiler", "buffer"], ["gasboiler", "dhw"]], "mutual_exclusion": true }
  ]
}
```

This compiles to four deferrable loads (one per flow):

- `deferrable0` heat pump -> buffer, `deferrable1` heat pump -> DHW,
  `deferrable2` gas boiler -> buffer, `deferrable3` gas boiler -> DHW.
- The buffer tank lists `load_ids: [0, 2]` (both sources feed it); the DHW tank lists
  `load_ids: [1, 3]`.
- The heat-pump loads stay on the electric balance and are priced with the
  `electricity` track; the gas-boiler loads leave the electric balance and are priced
  with the `gas` track.
- The two `actuator_groups` enforce that the heat pump heats either the buffer or the
  DHW per slot (never both), and likewise for the boiler.

```{note}
The arrays above are shortened to four steps for readability. In practice
`min_temperature`, `max_temperature`, `profile`, and each `cost_tracks` entry must
span the full optimization horizon.
```

## Configuring it

`heat_topology` lives in `optim_conf`. Because it is a nested object, set it in one of
these ways:

- **Web configuration page.** In the list view, `heat_topology` shows up as a single
  JSON text field (it is an object parameter): paste the topology JSON there. For more
  room, switch to the JSON (box) view and edit the `heat_topology` key directly.
- **`config.json` / `secrets`.** Add the `heat_topology` object directly to your
  persisted configuration.
- **`runtimeparams`.** Pass `heat_topology` in the runtime parameters of an
  optimization call to set or override it per run (useful for dynamic profiles and
  cost tracks). See [passing_data.md](passing_data.md).

When `heat_topology` is set, the compiler fills in `number_of_deferrable_loads` and the
per-load arrays for you. By default it **replaces** the whole deferrable-load set - do
not set the per-load arrays by hand at the same time unless you also set
`extend_deferrable_loads` (below).

## Combining with other deferrable loads

By default the compiler cannot tell your configured deferrable loads apart from the
shipped defaults, so it replaces the entire load set with the topology's flows. If you
have real non-thermal deferrable loads (washing machine, EV charger, ...) configured in
the flat per-load arrays, set the topology-level flag:

```json
{
  "heat_topology": {
    "extend_deferrable_loads": true,
    "sources": ["..."],
    "storage": ["..."],
    "flows": ["..."]
  }
}
```

With the flag set, your configured loads keep their indices `0..N-1` and the compiled
topology loads are appended at `N..N+M-1`. Shared-tank `load_ids` and actuator-group
references are shifted accordingly, and per-load arrays are padded to your configured
load count (with the usual defaults) before the topology values are appended. Setting
the flag is you asserting that the flat per-load config describes real loads.

Manually declared `shared_thermal_tanks` / `deferrable_load_groups` entries are kept;
the compiled ones are appended after them.

```{warning}
The appended topology loads are numbered relative to your configured load count:
adding or removing a manual deferrable load later **renumbers** the topology loads
(`sensor.p_deferrable2` silently changes meaning). Keep the manual load count stable
once a topology is in use, or remap the published entities via
`custom_deferrable_forecast_id`. If your load set changes often, a manual
`shared_thermal_tanks` configuration (which you index yourself) may be the better
fit.
```

## Validation

The compiler fails fast with a `ValueError` naming the offending field when:

- a source or storage `id` is duplicated;
- a `flow.from` / `flow.to` does not match a source / storage `id`;
- a `consumer.target` does not match a storage `id`;
- a heat-pump source has neither `supply_temperature` nor `heating_curve`, or a
  `heating_curve` is missing `slope` / `offset`;
- a source `type` is not recognised;
- a source `cost_track` is not present in `cost_tracks`;
- a storage gets two `building_demand` consumers;
- a `consumer.type` is not one of `profile`, `building_demand`, `pool_comfort`;
- a `min_temperature_curve` is missing `slope` / `offset`;
- a `comfort_sense` is not `heat` or `cool`;
- an `actuator_groups[..].flows` entry references a flow that does not exist.

If `heat_topology` is set to something that is not a non-empty object, it is ignored
and a warning is logged.

## See also

- [thermal_battery.md](thermal_battery.md) - the underlying per-store model, every
  physics parameter, calibration steps, and troubleshooting.
- [Heat-pump walkthrough](study_cases/heat_pump_walkthrough.md) - an end-to-end
  single-source scenario.
- [passing_data.md](passing_data.md) - passing `heat_topology` (and cost/demand
  profiles) as runtime parameters.
