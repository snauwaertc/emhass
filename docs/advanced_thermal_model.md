# Advanced Thermal Model Enhancements for EMHASS

This document outlines how to enhance the current thermal model in EMHASS to support more sophisticated thermal systems including water heating boilers and thermal buffer vats. These enhancements are designed to be generic and configurable, allowing users to enable or disable specific thermal components based on their system configuration.

## Current Thermal Model Overview

EMHASS currently implements a simple linear thermal model for space heating/cooling based on the equation:

$$
T_{in}^{pred}[k+1] = T_{in}^{pred}[k] + P_{def}[k]\frac{\alpha_h\Delta t}{P_{def}^{nom}}-(\gamma_c(T_{in}^{pred}[k] - T_{out}^{fcst}[k]))
$$

This model works well for direct space heating but lacks support for:
- Domestic hot water (DHW) heating via tanks
- Thermal buffer systems that decouple heat generation from heat demand
- Multiple thermal zones with different characteristics

## Integration with Hybrid Heating System

This document extends the **Hybrid Heating Optimization** approach described in `hybrid_heating.md` by adding support for a thermal buffer system architecture where heat sources supply thermal storage, which then supplies thermal loads.

**System Architecture:**
- **Heat Sources**: Heat pump and gas boiler supply heat to thermal buffer and DHW tank
- **Thermal Buffer**: Acts as central thermal storage, heated by HP/GB, supplies space heating
- **DHW Tank**: Heated directly by HP/GB for domestic hot water needs
- **Space Heating**: Supplied by thermal buffer discharge, not directly by heat sources

**Key Integration Points:**
- **Heat Sources**: Uses the same heat pump and gas boiler definitions from `hybrid_heating.md`
- **Heat Flow**: HP/GB → [Buffer + DHW], Buffer → Space Heating
- **Cost Optimization**: Considers electricity prices (for HP) and gas prices (for GB) when deciding charging strategy
- **Priority Management**: DHW gets direct priority, space heating served via buffer storage

## Proposed Enhancements

### 1. Domestic Hot Water (DHW) Tank Component

#### Purpose
Many homes require domestic hot water heating, typically served by a hot water tank heated by the same heat sources (heat pump and/or gas boiler) as space heating, but with distinct characteristics:
- **Time patterns**: Usually highest demand in morning hours (showers, washing)
- **Storage capacity**: Hot water tanks provide thermal mass and scheduling flexibility
- **Temperature requirements**: Higher temperature setpoints than space heating (typically 45-65°C vs 20-24°C)
- **Priority**: Often takes precedence over space heating during peak demand

#### Implementation Approach

**Configuration Structure:**
```json
"def_load_config": [
  {
    "thermal_config": {
      "type": "space_heating",
      "heating_rate": 5.0,
      "cooling_constant": 0.1,
      "overshoot_temperature": 24.0,
      "start_temperature": 20,
      "desired_temperatures": [21, 21, ...]
    }
  },
  {
    "thermal_config": {
      "type": "dhw_tank",
      "tank_capacity_liters": 300,
      "target_temperature": 55,
      "minimum_temperature": 45,
      "start_temperature": 50,
      "demand_profile": [10, 15, 5, 2, ...],
      "heat_loss_coefficient": 0.002,
      "priority": 1,
      "legionella_cycle": {
        "enabled": true,
        "temperature": 65,
        "frequency_hours": 168,
        "duration_minutes": 30
      }
    }
  }
]
```

**Heat Source Configuration (from hybrid_heating.md):**
```json
"heat_sources_config": {
  "heat_pump": {
    "enabled": true,
    "heating_rate_kw": 8.0,
    "cop_curve": {...},
    "min_outdoor_temp": -15
  },
  "gas_boiler": {
    "enabled": true,
    "heating_rate_kw": 15.0,
    "efficiency": 0.92,
    "gas_price_per_kwh": 0.06
  }
}
```
**Key Parameters:**
- `tank_capacity_liters`: Physical tank volume affecting thermal mass
- `target_temperature`: Normal operating temperature (e.g., 55°C)
- `minimum_temperature`: Minimum acceptable temperature (e.g., 45°C)
- `demand_profile`: Expected hot water consumption per timestep (liters)
- `reheat_priority`: Whether water heating takes priority over space heating
- `legionella_cycle`: Optional periodic high-temperature sterilization

**Mathematical Model:**
$$
T_{tank}[k+1] = T_{tank}[k] + \frac{Q_{heat\_sources}[k] \cdot \Delta t}{C_{water} \cdot V_{tank}} - \frac{Q_{loss}[k] + Q_{demand}[k]}{C_{water} \cdot V_{tank}}
$$

Where:
$$
Q_{heat\_sources}[k] = P_{HP\_to\_DHW}[k] \cdot COP_{HP}[k] + P_{GB\_to\_DHW}[k] \cdot \eta_{GB}
$$

Parameters:
- $T_{tank}$: DHW tank water temperature
- $Q_{heat\_sources}$: Combined heat input from heat pump and gas boiler to DHW (direct connection)
- $P_{HP\_to\_DHW}$: Heat pump electrical power allocated to DHW heating
- $P_{GB\_to\_DHW}$: Gas boiler thermal power allocated to DHW heating
- $COP_{HP}$: Heat pump coefficient of performance (from hybrid_heating.md)
- $\eta_{GB}$: Gas boiler efficiency (from hybrid_heating.md)
- $C_{water}$: Specific heat capacity of water (4.18 kJ/kg·K)
- $V_{tank}$: Tank volume
- $Q_{loss}$: Heat loss to environment
- $Q_{demand}$: Heat removed by hot water consumption

### 2. Thermal Buffer Vat Component

#### Purpose
A thermal buffer vat (also called a thermal store or accumulator tank) provides:
- **Decoupling**: Allows heat sources to operate independently of immediate demand
- **Efficiency**: Enables heat sources to run at optimal efficiency points
- **Storage**: Stores excess thermal energy for later use
- **Multiple sources**: Can accept heat from various sources (heat pump, boiler, solar thermal)

#### Implementation Approach

**Configuration Structure:**
```json
"thermal_buffer_config": {
  "enabled": true,
  "capacity_kwh": 50,
  "max_charge_rate_kw": 10,
  "max_discharge_rate_kw": 8,
  "efficiency_charge": 0.95,
  "efficiency_discharge": 0.95,
  "standby_loss_rate": 0.002,
  "temperature_layers": 3,
  "min_temp": 35,
  "max_temp": 80,
  "initial_temp": 45,
  "connected_sources": ["heat_pump", "boiler"],
  "connected_loads": ["space_heating", "water_heating"]
}
```

**Key Parameters:**
- `capacity_kwh`: Total thermal storage capacity
- `max_charge_rate_kw`/`max_discharge_rate_kw`: Power limits
- `efficiency_charge`/`efficiency_discharge`: Round-trip efficiency losses
- `standby_loss_rate`: Hourly heat loss rate when idle
- `temperature_layers`: Number of thermal stratification layers to model
- `connected_sources`/`connected_loads`: Which components can charge/discharge the buffer

**Mathematical Model (Simplified Single-Zone):**
$$
E_{buffer}[k+1] = E_{buffer}[k] \cdot (1 - loss_{rate} \cdot \Delta t) + Q_{heat\_sources\_to\_buffer}[k] \cdot \eta_{charge} \cdot \Delta t - \frac{P_{discharge}[k]}{\eta_{discharge}} \cdot \Delta t
$$

Where:
$$
Q_{heat\_sources\_to\_buffer}[k] = P_{HP\_to\_buffer}[k] \cdot COP_{HP}[k] + P_{GB\_to\_buffer}[k] \cdot \eta_{GB}
$$

**Space Heating Supply (from Buffer):**
$$
T_{space}[k+1] = T_{space}[k] + \frac{P_{buffer\_to\_space}[k] \cdot \eta_{discharge} \cdot \Delta t}{C_{space}} - \gamma_c \cdot (T_{space}[k] - T_{outdoor}[k]) \cdot \Delta t
$$

Where $P_{buffer\_to\_space}[k]$ is the thermal power discharged from buffer to space heating.

For stratified tanks with multiple temperature layers:
$$
T_{layer,i}[k+1] = T_{layer,i}[k] + \frac{Q_{in,i}[k] - Q_{out,i}[k] - Q_{mix,i}[k]}{C_{layer} \cdot V_{layer}}
$$

## Generic Implementation Strategy

### 1. Modular Configuration System

**Enhanced def_load_config Structure:**
```json
"def_load_config": [
  {
    "thermal_config": {
      "enabled": true,
      "type": "space_heating|water_heating|buffer_vat",
      "priority": 1,
      "dependencies": ["buffer_vat_0"],
      "type_specific_config": { ... }
    }
  }
]
```

### 2. Component Registration System

**New Configuration Section:**
```json
"thermal_system_config": {
  "enabled": true,
  "components": {
    "space_heating": {
      "enabled": true,
      "def_load_index": 0
    },
    "dhw_tank": {
      "enabled": true,
      "def_load_index": 1
    },
    "thermal_buffer": {
      "enabled": false,
      "capacity_kwh": 50
    }
  },
  "heat_allocation": {
    "heat_pump": {
      "can_serve": ["dhw_tank", "thermal_buffer"],
      "priority_order": ["dhw_tank", "thermal_buffer"]
    },
    "gas_boiler": {
      "can_serve": ["dhw_tank", "thermal_buffer"],
      "priority_order": ["dhw_tank", "thermal_buffer"]
    }
  },
  "buffer_connections": {
    "can_charge_from": ["heat_pump", "gas_boiler"],
    "can_discharge_to": ["space_heating"],
    "space_heating_source": "thermal_buffer_only"
  }
}
```

### 3. Code Implementation Changes

#### A. Configuration Loading (utils.py)

**New function to handle thermal system configuration:**
```python
def load_thermal_system_config(params: dict) -> dict:
    """Load and validate thermal system configuration."""
    thermal_config = params.get("thermal_system_config", {})
    
    if not thermal_config.get("enabled", False):
        return {}
    
    # Validate component dependencies
    # Process thermal buffer configuration
    # Set up thermal component interconnections
    
    return thermal_config
```

#### B. Optimization Logic (optimization.py)

**Enhanced thermal constraint generation:**
```python
def add_thermal_buffer_constraints(self, opt_model, constraints, set_I):
    """Add thermal buffer vat constraints to optimization model."""
    if not self.thermal_system_config.get("thermal_buffer", {}).get("enabled"):
        return
    
    buffer_config = self.thermal_system_config["thermal_buffer"]
    
    # Create buffer state variables
    buffer_energy = [plp.LpVariable(f"buffer_energy_{i}", 
                                   lowBound=0, 
                                   upBound=buffer_config["capacity_kwh"]) 
                    for i in set_I]
    
    # Add buffer dynamics constraints
    for i in set_I[1:]:
        # Energy balance equation
        constraints[f"buffer_energy_balance_{i}"] = plp.LpConstraint(
            buffer_energy[i] == 
            buffer_energy[i-1] * (1 - buffer_config["standby_loss_rate"] * self.timeStep) +
            sum(charge_power_sources) * buffer_config["efficiency_charge"] * self.timeStep -
            sum(discharge_power_loads) / buffer_config["efficiency_discharge"] * self.timeStep,
            sense=plp.LpConstraintEQ,
            rhs=0
        )

def add_dhw_tank_constraints(self, opt_model, constraints, set_I, k):
    """Add domestic hot water tank heating constraints."""
    hc = self.optim_conf["def_load_config"][k]["thermal_config"]
    
    if hc.get("type") != "dhw_tank":
        return
    
    # Tank temperature tracking
    tank_temp = [hc["start_temperature"]]
    
    for i in set_I[1:]:
        # Heat input from heat sources (HP + GB allocation to DHW)
        heat_input_hp = P_HP_to_DHW[i-1] * COP_HP[i-1]  # Heat from heat pump
        heat_input_gb = P_GB_to_DHW[i-1] * self.heat_sources_config["gas_boiler"]["efficiency"]  # Heat from gas boiler
        total_heat_input = heat_input_hp + heat_input_gb
        
        # Heat losses and demand
        heat_loss = hc["heat_loss_coefficient"] * (tank_temp[i-1] - outdoor_temp[i-1])
        heat_demand = hc["demand_profile"][i] * 4.18 * (tank_temp[i-1] - 10) / 3600  # kWh
        
        tank_temp.append(
            tank_temp[i-1] + 
            (total_heat_input - heat_loss - heat_demand) * self.timeStep * 3600 / 
            (hc["tank_capacity_liters"] * 4.18)
        )
        
        # Temperature constraints
        constraints[f"dhw_tank_min_temp_{i}"] = plp.LpConstraint(
            tank_temp[i] >= hc["minimum_temperature"],
            sense=plp.LpConstraintGE,
            rhs=0
        )
        
        constraints[f"dhw_tank_max_temp_{i}"] = plp.LpConstraint(
            tank_temp[i] <= hc["target_temperature"] + 5,  # Allow 5°C overshoot
            sense=plp.LpConstraintLE,
            rhs=0
        )
```

### 4. Configuration Examples

#### Simple System (Current + DHW Tank)
```yaml
# Heat sources from hybrid_heating.md
heat_sources_config:
  heat_pump:
    enabled: true
    heating_rate_kw: 8.0
    cop_curve: {outdoor_temp: [-15, 0, 15], cop: [2.5, 3.2, 4.1]}
    min_outdoor_temp: -15
    can_serve: ["dhw_tank", "thermal_buffer"]
  gas_boiler:
    enabled: true
    heating_rate_kw: 15.0
    efficiency: 0.92
    gas_price_per_kwh: 0.06
    can_serve: ["dhw_tank", "thermal_buffer"]

# Thermal buffer configuration (required for space heating)
thermal_buffer_config:
  enabled: true
  capacity_kwh: 20
  max_charge_rate_kw: 8
  max_discharge_rate_kw: 6
  supplies: ["space_heating"]

# Thermal loads configuration
optim_conf:
  number_of_deferrable_loads: 2
  def_load_config:
    - thermal_config:
        type: space_heating
        heating_rate: 5.0
        cooling_constant: 0.1
        start_temperature: 20
        desired_temperatures: [21] * 48
        heat_source: "thermal_buffer"  # Space heating comes from buffer
    - thermal_config:
        type: dhw_tank
        tank_capacity_liters: 200
        target_temperature: 55
        minimum_temperature: 45
        start_temperature: 50
        heat_loss_coefficient: 0.002
        priority: 1
        heat_source: "direct"  # DHW heated directly by HP/GB
        demand_profile: [8, 15, 12, 5, 5, 8, 10, 8, 6, 4, 4, 4, 4, 4, 6, 8, 10, 12, 8, 6, 4, 4, 4, 4] * 2  # 48 timesteps
```

#### Advanced System (With Thermal Buffer)
```yaml
# Heat sources from hybrid_heating.md  
heat_sources_config:
  heat_pump:
    enabled: true
    heating_rate_kw: 12.0
    cop_curve: {outdoor_temp: [-15, 0, 15], cop: [2.5, 3.2, 4.1]}
    min_outdoor_temp: -15
    can_serve: ["dhw_tank", "thermal_buffer"]  # No direct space heating
  gas_boiler:
    enabled: true
    heating_rate_kw: 20.0
    efficiency: 0.92
    gas_price_per_kwh: 0.06
    can_serve: ["dhw_tank", "thermal_buffer"]  # No direct space heating

# Thermal system topology
thermal_system_config:
  enabled: true
  architecture: "buffer_based"  # Heat sources → Buffer → Space heating
  components:
    thermal_buffer:
      enabled: true
      capacity_kwh: 30
      max_charge_rate_kw: 8
      max_discharge_rate_kw: 6
      efficiency_charge: 0.95
      efficiency_discharge: 0.95
      supplies: ["space_heating"]  # Buffer is sole source for space heating
  heat_allocation:
    heat_pump:
      can_serve: ["dhw_tank", "thermal_buffer"]
      priority_order: ["dhw_tank", "thermal_buffer"]
    gas_boiler:
      can_serve: ["dhw_tank", "thermal_buffer"] 
      priority_order: ["dhw_tank", "thermal_buffer"]
      
# Thermal loads configuration
optim_conf:
  number_of_deferrable_loads: 2
  def_load_config:
    - thermal_config:
        type: space_heating
        heating_rate: 5.0
        cooling_constant: 0.1
        heat_source: "thermal_buffer"  # Space heating ONLY from buffer
        priority: 2
    - thermal_config:
        type: dhw_tank
        tank_capacity_liters: 300
        target_temperature: 55
        minimum_temperature: 45
        heat_loss_coefficient: 0.002
        heat_source: "direct"  # DHW heated directly by HP/GB
        priority: 1
```

## Implementation Benefits

### 1. Flexibility
- **Modular Design**: Each thermal component can be enabled/disabled independently
- **Configurable Priorities**: Water heating can take precedence during morning hours
- **Multiple Heat Sources**: Heat pumps, boilers, and solar thermal can all contribute

### 2. Optimization Improvements
- **Better Load Shifting**: Thermal buffers enable more flexible load scheduling
- **Efficiency Gains**: Heat sources can operate at optimal efficiency points
- **Cost Reduction**: Store thermal energy during low-cost periods

### 3. Real-World Applicability
- **DHW Modeling**: Accurately represents domestic hot water systems
- **Thermal Mass**: Properly accounts for thermal storage in tanks and buffers
- **System Integration**: Models realistic thermal system topologies

## Migration Path

### Phase 1: Water Heating Component
1. Extend `thermal_config` with water heating parameters
2. Add water heating thermal model to optimization.py
3. Update configuration validation in utils.py

### Phase 2: Thermal Buffer Integration
1. Add `thermal_system_config` configuration section
2. Implement thermal buffer constraints
3. Create component interconnection logic

### Phase 3: Advanced Features
1. Multi-zone thermal modeling
2. Thermal stratification in tanks
3. Solar thermal integration
4. Advanced control strategies

## Complete Mathematical Formulation

### Heat Source Power Allocation

The optimizer must decide how to allocate heat source power between different thermal loads:

**Heat Pump Power Allocation (No Direct Space Heating):**
$$
P_{HP,total}[k] = P_{HP\_to\_DHW}[k] + P_{HP\_to\_buffer}[k]
$$

**Gas Boiler Power Allocation (No Direct Space Heating):**
$$
P_{GB,total}[k] = P_{GB\_to\_DHW}[k] + P_{GB\_to\_buffer}[k]
$$

**Space Heating Supply (from Buffer Only):**
$$
P_{space\_heating}[k] = P_{buffer\_to\_space}[k]
$$

### Constraints

**Heat Source Capacity Limits:**
$$
P_{HP,total}[k] \leq HP_{max\_power} \cdot Activate_{HP}[k]
$$
$$
P_{GB,total}[k] \leq GB_{max\_power} \cdot Activate_{GB}[k]
$$

**Priority Constraints (DHW over Buffer Charging):**
$$
P_{HP\_to\_DHW}[k] + P_{GB\_to\_DHW}[k] \geq DHW_{minimum\_power}[k]
$$

**Buffer Energy Balance:**
$$
E_{buffer}[k+1] = E_{buffer}[k] \cdot (1 - loss_{rate} \cdot \Delta t) + (P_{HP\_to\_buffer}[k] \cdot COP[k] + P_{GB\_to\_buffer}[k] \cdot \eta_{GB}) \cdot \Delta t - P_{buffer\_to\_space}[k] \cdot \Delta t
$$

**Space Heating Constraint (Buffer Must Meet Demand):**
$$
P_{buffer\_to\_space}[k] \geq Space_{heating\_demand}[k]
$$

### Objective Function Enhancement

The total cost function from `hybrid_heating.md` is extended to include allocation decisions:

$$
\text{Total Cost} = \sum_k \left[
\begin{aligned}
&\frac{P_{HP,total}[k]}{COP[k]} \cdot \text{Electricity Price}[k] \cdot \Delta t \\
&+ \frac{P_{GB,total}[k]}{\eta_{GB}} \cdot \text{Gas Price} \cdot \Delta t \\
&+ \text{Comfort Penalties} + \text{Other EMHASS Costs}
\end{aligned}
\right]
$$

## Conclusion

These enhancements transform EMHASS from a simple space heating optimizer into a comprehensive thermal energy management system that integrates seamlessly with the hybrid heating approach described in `hybrid_heating.md`. 

**Key Benefits:**
- **Realistic Architecture**: Heat sources charge thermal buffer and DHW, buffer supplies space heating
- **Thermal Decoupling**: Heat sources can run at optimal efficiency independent of immediate space heating demand
- **Smart Storage**: Optimizer decides when to charge buffer based on energy prices and demand forecasts
- **Direct DHW Priority**: Domestic hot water gets direct heat source priority for rapid heating
- **Modular Design**: Components can be enabled/disabled independently while maintaining system coherence

The enhanced thermal model will enable more accurate optimization of complex thermal systems, leading to better energy efficiency and cost savings for users with domestic hot water systems and thermal storage. 