# Hybrid Heating Optimization in EMHASS

This document outlines how to configure EMHASS to optimize hybrid heating systems (heat pump + gas boiler) by treating each heat source as separate deferrable loads, allowing the optimizer to make intelligent economic decisions based on real-time energy prices.

## Executive Summary

**Goal**: Minimize total heating costs while maintaining comfort by allowing EMHASS to select the optimal heat source (heat pump vs gas boiler) for each time period based on:
- Real-time electricity and gas prices
- Heat pump efficiency at current outdoor temperatures  
- Technical system limitations
- Thermal storage opportunities

**Key Principle**: Let the EMHASS optimizer make all economic decisions. No fixed economic bivalence points - decisions adapt dynamically to market conditions.

## 1. Configuration Philosophy

### Heat Sources as Deferrable Loads

Each heat source and application combination is configured as a separate deferrable load:

1. **Heat Pump Space Heating** - `p_deferrable0`
2. **Gas Boiler Space Heating** - `p_deferrable1` 
3. **Heat Pump DHW** - `p_deferrable2`
4. **Gas Boiler DHW** - `p_deferrable3`

This allows EMHASS to independently schedule each heat source based on:
- Application-specific efficiency curves
- Real-time fuel costs
- Technical constraints
- Demand forecasts

### Economic Optimization Principles

**What EMHASS Considers:**
- Electricity price forecasts (including negative pricing periods)
- Gas price (static or dynamic)
- Heat pump COP curves vs outdoor temperature
- Technical capacity limitations
- Future energy planning requirements

**What EMHASS Decides:**
- Which heat source to use when
- How much thermal energy from each source
- Optimal timing for thermal storage charging
- Load shifting opportunities

## 2. EMHASS Configuration Structure

### Deferrable Load Setup

```json
{
  "optim_conf": {
    "number_of_deferrable_loads": 4,
    "nominal_power_of_deferrable_loads": [12, 24, 6, 6],
    "operating_hours_of_each_deferrable_load": [24, 24, 24, 24],
    "start_timesteps_of_each_deferrable_load": [0, 0, 0, 0],
    "end_timesteps_of_each_deferrable_load": [48, 48, 48, 48],
    "def_load_config": [
      {
        "load_name": "heat_pump_space_heating",
        "thermal_config": {
          "type": "heat_pump_heating",
          "applications": ["space_heating"],
          "efficiency_model": "temperature_dependent_cop",
          "capacity_curve": {
            "outdoor_temps": [-15, -10, -5, 0, 2, 7, 15],
            "max_capacities": [2.0, 3.0, 6.0, 8.0, 8.0, 10.0, 12.0]
          },
          "cop_curve": {
            "outdoor_temps": [-15, -10, -5, 0, 2, 7, 15], 
            "cop_values": [1.8, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
          },
          "min_outdoor_temp": -15,
          "flow_temp_space_heating": 40
        }
      },
      {
        "load_name": "gas_boiler_space_heating", 
        "thermal_config": {
          "type": "gas_boiler_heating",
          "applications": ["space_heating"],
          "efficiency": 0.9,
          "fuel_type": "natural_gas",
          "max_capacity": 24,
          "min_capacity": 4.8,
          "flow_temp_space_heating": 45
        }
      },
      {
        "load_name": "heat_pump_dhw",
        "thermal_config": {
          "type": "heat_pump_dhw",
          "applications": ["domestic_hot_water"],
          "efficiency_model": "temperature_dependent_cop", 
          "cop_curve": {
            "outdoor_temps": [-15, -10, -5, 0, 2, 7, 15],
            "cop_values": [1.5, 1.8, 2.2, 2.6, 3.0, 3.4, 3.8]
          },
          "max_capacity": 6,
          "flow_temp_dhw": 55
        }
      },
      {
        "load_name": "gas_boiler_dhw",
        "thermal_config": {
          "type": "gas_boiler_dhw", 
          "applications": ["domestic_hot_water"],
          "efficiency": 0.9,
          "fuel_type": "natural_gas",
          "max_capacity": 6,
          "min_capacity": 1.2,
          "flow_temp_dhw": 55,
          "priority_over_space_heating": true
        }
      }
    ]
  }
}
```

### Energy Cost Configuration

```json
{
  "retrieve_hass_conf": {
    "var_PV": "sensor.power_photovoltaics",
    "var_load": "sensor.power_load_no_var_loads", 
    "load_cost": "sensor.electricity_price_kwh",
    "prod_price": "sensor.electricity_sell_price_kwh",
    "gas_cost": "sensor.gas_price_kwh"
  }
}
```

### Thermal Demand Configuration

```json
{
  "optim_conf": {
    "thermal_config": {
      "house_thermal_mass_kwh_per_c": 5.0,
      "house_thermal_loss_w_per_c": 250,
      "initial_indoor_temp": "sensor.indoor_temperature",
      "comfort_temp_min": 19.0,
      "comfort_temp_max": 22.0,
      "outdoor_temp_forecast": "weather.home",
      "space_heating_demand": "sensor.thermal_demand_space_heating",
      "dhw_demand": "sensor.thermal_demand_dhw"
    }
  }
}
```

## 3. Technical Constraints (Not Economic)

The optimizer respects technical limitations but makes all economic decisions:

### Heat Pump Technical Limits
- **Minimum outdoor temperature**: Below which heat pump cannot operate safely
- **Capacity derating**: Heat pump capacity decreases at lower outdoor temperatures
- **COP variation**: Efficiency changes with outdoor temperature and application

### Gas Boiler Technical Limits  
- **Minimum capacity**: Lowest thermal output for stable operation
- **Maximum capacity**: Peak thermal output
- **Modulation range**: Operational range between min and max

### System Coordination
- **Parallel operation**: Both systems can run simultaneously if beneficial
- **Application priority**: DHW typically takes priority over space heating
- **Safety interlocks**: Prevent unsafe operating conditions

## 4. Real-World Example Scenarios

### Scenario 1: Negative Electricity Pricing
**Conditions**: Outdoor temp -5°C, electricity price -€0.03/kWh, gas €0.08/kWh

**Traditional Fixed Bivalence**: Would use gas boiler (below economic bivalence point)

**EMHASS Dynamic Decision**:
- Heat pump COP at -5°C: 2.5
- Heat pump thermal cost: -€0.03/2.5 = -€0.012/kWh thermal
- Gas boiler thermal cost: €0.08/0.9 = €0.089/kWh thermal
- **Result**: EMHASS chooses heat pump, getting paid to heat the house

### Scenario 2: Gas Price Spike
**Conditions**: Outdoor temp 5°C, electricity €0.25/kWh, gas €0.15/kWh (spike)

**Traditional Logic**: Might still prefer gas at this temperature

**EMHASS Analysis**:
- Heat pump COP at 5°C: 3.8
- Heat pump thermal cost: €0.25/3.8 = €0.066/kWh thermal  
- Gas boiler thermal cost: €0.15/0.9 = €0.167/kWh thermal
- **Result**: EMHASS chooses heat pump despite moderate outdoor temp

### Scenario 3: High Demand Period
**Conditions**: Very cold day (-12°C), high heating demand

**EMHASS Strategy**:
- Heat pump at capacity limit: 3kW thermal
- Remaining demand: Gas boiler supplements
- **Parallel operation** for optimal coverage
- DHW prioritized to gas boiler (higher flow temp efficiency)

## 5. Implementation with Real Systems

### Home Assistant Sensor Creation

```yaml
template:
  - sensor:
      # Convert EMHASS outputs to heat source schedules
      - name: "Heat Pump Space Heating Schedule"
        state: "{{ states('sensor.p_deferrable0') | float(0) }}"
        unit_of_measurement: "kW"
        
      - name: "Gas Boiler Space Heating Schedule"
        state: "{{ states('sensor.p_deferrable1') | float(0) }}"
        unit_of_measurement: "kW"
        
      - name: "Heat Pump DHW Schedule"
        state: "{{ states('sensor.p_deferrable2') | float(0) }}"
        unit_of_measurement: "kW"
        
      - name: "Gas Boiler DHW Schedule"
        state: "{{ states('sensor.p_deferrable3') | float(0) }}"
        unit_of_measurement: "kW"

      # Aggregate schedules
      - name: "Total Heat Pump Demand"
        state: |
          {{ (states('sensor.heat_pump_space_heating_schedule') | float(0) + 
              states('sensor.heat_pump_dhw_schedule') | float(0)) | round(2) }}
        unit_of_measurement: "kW"
        
      - name: "Total Gas Boiler Demand"
        state: |
          {{ (states('sensor.gas_boiler_space_heating_schedule') | float(0) + 
              states('sensor.gas_boiler_dhw_schedule') | float(0)) | round(2) }}
        unit_of_measurement: "kW"
```

### Vaillant System Control (via ebusd)

#### Heat Pump Control Automation

```yaml
automation:
  - alias: "EMHASS Heat Pump Control"
    trigger:
      - platform: state
        entity_id: sensor.total_heat_pump_demand
    condition:
      - condition: state
        entity_id: binary_sensor.vaillant_system_fault
        state: 'off'
    action:
      - choose:
          # Activate heat pump
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.total_heat_pump_demand') | float > 0.1 }}"
            sequence:
              - service: mqtt.publish
                data:
                  topic: "ebusd/hp/ActiveMode/set"
                  payload: "true"
                  
              # Set thermal demand setpoint (not modulation)
              - service: mqtt.publish
                data:
                  topic: "ebusd/hp/ThermalDemandSetpoint/set"
                  payload: "{{ states('sensor.total_heat_pump_demand') | float }}"
                  
              # Configure operating mode based on application split
              - variables:
                  space_demand: "{{ states('sensor.heat_pump_space_heating_schedule') | float(0) }}"
                  dhw_demand: "{{ states('sensor.heat_pump_dhw_schedule') | float(0) }}"
                  
              - if:
                  - condition: template
                    value_template: "{{ dhw_demand > space_demand }}"
                then:
                  # DHW priority
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/OperatingMode/set"
                      payload: "dhw_priority"
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/FlowTempSetpoint/set"
                      payload: "55"
                else:
                  # Space heating priority
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/OperatingMode/set"
                      payload: "space_heating"
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/FlowTempSetpoint/set"
                      payload: "40"
          
          # Deactivate heat pump
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.total_heat_pump_demand') | float <= 0.1 }}"
            sequence:
              - service: mqtt.publish
                data:
                  topic: "ebusd/hp/ActiveMode/set"
                  payload: "false"
```

#### Gas Boiler Control Automation

```yaml
automation:
  - alias: "EMHASS Gas Boiler Control"
    trigger:
      - platform: state
        entity_id: sensor.total_gas_boiler_demand
    condition:
      - condition: state
        entity_id: binary_sensor.vaillant_system_fault
        state: 'off'
    action:
      - choose:
          # Activate gas boiler
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.total_gas_boiler_demand') | float > 0.1 }}"
            sequence:
              - service: mqtt.publish
                data:
                  topic: "ebusd/bai/HeatingActive/set"
                  payload: "true"
                  
              # Set thermal demand setpoint (let boiler control modulation)
              - service: mqtt.publish
                data:
                  topic: "ebusd/bai/ThermalDemandSetpoint/set"
                  payload: "{{ states('sensor.total_gas_boiler_demand') | float }}"
                  
              # Configure operating mode
              - variables:
                  space_demand: "{{ states('sensor.gas_boiler_space_heating_schedule') | float(0) }}"
                  dhw_demand: "{{ states('sensor.gas_boiler_dhw_schedule') | float(0) }}"
                  
              - if:
                  - condition: template
                    value_template: "{{ dhw_demand > 0 and space_demand > 0 }}"
                then:
                  # Combined mode
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/bai/OperatingMode/set"
                      payload: "3"  # Combined heating and DHW
                elif:
                  - condition: template
                    value_template: "{{ dhw_demand > 0 }}"
                then:
                  # DHW only
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/bai/OperatingMode/set"
                      payload: "2"  # DHW only
                else:
                  # Space heating only
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/bai/OperatingMode/set"
                      payload: "1"  # Heating only
                      
              # Set flow temperature based on application
              - service: mqtt.publish
                data:
                  topic: "ebusd/bai/FlowTempSetpoint/set"
                  payload: |
                    {% if dhw_demand > 0 %}
                      55  # DHW requires higher temperature
                    {% else %}
                      45  # Space heating
                    {% endif %}
          
          # Deactivate gas boiler
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.total_gas_boiler_demand') | float <= 0.1 }}"
            sequence:
              - service: mqtt.publish
                data:
                  topic: "ebusd/bai/HeatingActive/set"
                  payload: "false"
```

## 6. Advanced Features

### Parallel Operation Coordination

When both heat sources are active simultaneously:

```yaml
automation:
  - alias: "Coordinate Parallel Heat Source Operation"
    trigger:
      - platform: state
        entity_id:
          - sensor.total_heat_pump_demand
          - sensor.total_gas_boiler_demand
    condition:
      - condition: template
        value_template: |
          {{ states('sensor.total_heat_pump_demand') | float > 0.1 and 
             states('sensor.total_gas_boiler_demand') | float > 0.1 }}
    action:
      # Enable parallel operation mode
      - service: mqtt.publish
        data:
          topic: "ebusd/system/ParallelMode/set"
          payload: "true"
          
      # Coordinate applications to avoid conflicts
      - if:
          - condition: template
            value_template: "{{ states('sensor.gas_boiler_dhw_schedule') | float > 0 }}"
        then:
          # Gas boiler handles DHW, heat pump handles space heating
          - service: mqtt.publish
            data:
              topic: "ebusd/bai/Priority/set"
              payload: "dhw"
          - service: mqtt.publish
            data:
              topic: "ebusd/hp/Priority/set"
              payload: "space_heating"
```

### Thermal Buffer Integration

If a thermal buffer is present, add it as an additional deferrable load:

```json
{
  "load_name": "thermal_buffer_charging",
  "thermal_config": {
    "type": "thermal_storage",
    "capacity_kwh": 20,
    "max_charge_rate_kw": 8,
    "max_discharge_rate_kw": 6,
    "efficiency": 0.95,
    "self_discharge_rate": 0.02
  }
}
```

## 7. Benefits of This Approach

### 1. **True Economic Optimization**
- No arbitrary economic bivalence points
- Adapts to real-time energy market conditions
- Captures opportunities from negative electricity pricing
- Responds dynamically to gas price volatility

### 2. **Intelligent System Control**
- Uses setpoints instead of forcing modulation levels
- Respects manufacturer control algorithms
- Maintains system stability and safety
- Allows for optimal equipment coordination

### 3. **Future-Proof Design**
- Easily adapts to new energy tariff structures
- Handles time-of-use electricity pricing
- Scales with additional heat sources or storage
- Compatible with smart grid integration

### 4. **Comprehensive Integration**
- Works with existing EMHASS PV and battery optimization
- Integrates with real heating system control (ebusd)
- Provides detailed monitoring and feedback
- Supports complex multi-zone systems

This approach transforms hybrid heating from rule-based operation to true optimization-driven energy management, maximizing both economic efficiency and system performance. 