# EMHASS Heat Source Selection with Vaillant Control

This document explains how to configure EMHASS to make intelligent heat source selection decisions during optimization, and then translate those decisions into direct Vaillant system control via ebusd.

## Approach Overview

Instead of post-optimization steering, EMHASS makes heat source decisions during optimization based on:
- Real-time and forecasted energy prices (electricity vs gas)
- Heat pump capacity curves and COP at different outdoor temperatures
- Bivalence point constraints
- System efficiency characteristics
- Future energy planning requirements

## EMHASS Configuration for Heat Source Selection

### Enhanced Deferrable Load Configuration

Configure EMHASS to treat heat sources as separate deferrable loads:

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
            "outdoor_temps": [-10, -5, 0, 2, 7, 15],
            "max_capacities": [3.0, 6.0, 8.0, 8.0, 10.0, 12.0]
          },
          "cop_curve": {
            "outdoor_temps": [-10, -5, 0, 2, 7, 15], 
            "cop_values": [2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
          },
          "bivalence_point_technical": -5,
          "min_outdoor_temp": -15
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
          "min_capacity": 4.8
        }
      },
      {
        "load_name": "heat_pump_dhw",
        "thermal_config": {
          "type": "heat_pump_dhw",
          "applications": ["domestic_hot_water"],
          "efficiency_model": "temperature_dependent_cop", 
          "cop_curve": {
            "outdoor_temps": [-10, -5, 0, 2, 7, 15],
            "cop_values": [1.8, 2.2, 2.6, 3.0, 3.4, 3.8]
          },
          "max_capacity": 6
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
          "priority_over_space_heating": true
        }
      }
    ]
  }
}
```

### Energy Cost Configuration

Configure both electricity and gas pricing:

```json
{
  "retrieve_hass_conf": {
    "var_PV": "sensor.power_photovoltaics",
    "var_load": "sensor.power_load_no_var_loads", 
    "load_cost": "sensor.nordpool_kwh_price",
    "prod_price": "sensor.nordpool_kwh_sell_price",
    "gas_cost": "sensor.gas_price_kwh"
  }
}
```

### Constraint Configuration

Add thermal demand constraints and technical limitations:

```json
{
  "optim_conf": {
    "thermal_constraints": {
      "space_heating_demand": "sensor.thermal_demand_space_heating",
      "dhw_demand": "sensor.thermal_demand_dhw", 
      "technical_constraints": {
        "heat_pump_min_outdoor_temp": -15,
        "heat_pump_capacity_derating": true,
        "enable_parallel_operation": true
      }
    }
  }
}
```

## EMHASS Optimization Output

With this configuration, EMHASS will output separate schedules for each heat source:

- `sensor.p_deferrable0` → Heat pump space heating schedule
- `sensor.p_deferrable1` → Gas boiler space heating schedule  
- `sensor.p_deferrable2` → Heat pump DHW schedule
- `sensor.p_deferrable3` → Gas boiler DHW schedule

## Home Assistant Translation Logic

### Sensor Creation for Heat Source Schedules

```yaml
template:
  - sensor:
      - name: "EMHASS Heat Pump Space Schedule"
        state: "{{ states('sensor.p_deferrable0') | float(0) }}"
        unit_of_measurement: "kW"
        device_class: power
        
      - name: "EMHASS Gas Boiler Space Schedule" 
        state: "{{ states('sensor.p_deferrable1') | float(0) }}"
        unit_of_measurement: "kW"
        device_class: power
        
      - name: "EMHASS Heat Pump DHW Schedule"
        state: "{{ states('sensor.p_deferrable2') | float(0) }}"
        unit_of_measurement: "kW"
        device_class: power
        
      - name: "EMHASS Gas Boiler DHW Schedule"
        state: "{{ states('sensor.p_deferrable3') | float(0) }}"
        unit_of_measurement: "kW"
        device_class: power

      - name: "Total Heat Pump Schedule"
        state: |
          {{ (states('sensor.emhass_heat_pump_space_schedule') | float(0) + 
              states('sensor.emhass_heat_pump_dhw_schedule') | float(0)) | round(2) }}
        unit_of_measurement: "kW"
        
      - name: "Total Gas Boiler Schedule"
        state: |
          {{ (states('sensor.emhass_gas_boiler_space_schedule') | float(0) + 
              states('sensor.emhass_gas_boiler_dhw_schedule') | float(0)) | round(2) }}
        unit_of_measurement: "kW"
```

### Vaillant Heat Pump Control

```yaml
automation:
  - alias: "Execute EMHASS Heat Pump Schedule"
    trigger:
      - platform: state
        entity_id: sensor.total_heat_pump_schedule
        not_from:
          - "unknown"
          - "unavailable"
    condition:
      - condition: state
        entity_id: binary_sensor.vaillant_system_fault
        state: 'off'
    action:
      - choose:
          # Heat pump should be active
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.total_heat_pump_schedule') | float > 0.1 }}"
            sequence:
              # Activate heat pump
              - service: mqtt.publish
                data:
                  topic: "ebusd/hp/ActiveMode/set" 
                  payload: "true"
                  
              # Set thermal output based on demand split
              - variables:
                  space_demand: "{{ states('sensor.emhass_heat_pump_space_schedule') | float(0) }}"
                  dhw_demand: "{{ states('sensor.emhass_heat_pump_dhw_schedule') | float(0) }}"
                  total_demand: "{{ space_demand + dhw_demand }}"
                  
              # Configure heat pump for primary application
              - if:
                  - condition: template
                    value_template: "{{ dhw_demand > space_demand }}"
                then:
                  # DHW priority mode
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/OperatingMode/set"
                      payload: "dhw_priority"
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/ThermalOutput/set"
                      payload: "{{ total_demand }}"
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/FlowTempSetpoint/set"
                      payload: "55"  # Higher temp for DHW
                else:
                  # Space heating priority mode
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/OperatingMode/set"
                      payload: "space_heating"
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/ThermalOutput/set"
                      payload: "{{ total_demand }}"
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/hp/FlowTempSetpoint/set"
                      payload: |
                        {% set outdoor_temp = states('sensor.vaillant_outdoor_temperature') | float %}
                        {% if outdoor_temp < 0 %}
                          45
                        {% elif outdoor_temp < 10 %}
                          40
                        {% else %}
                          35
                        {% endif %}
          
          # Heat pump should be inactive
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.total_heat_pump_schedule') | float <= 0.1 }}"
            sequence:
              - service: mqtt.publish
                data:
                  topic: "ebusd/hp/ActiveMode/set"
                  payload: "false"
```

### Vaillant Gas Boiler Control

```yaml
automation:
  - alias: "Execute EMHASS Gas Boiler Schedule"
    trigger:
      - platform: state
        entity_id: sensor.total_gas_boiler_schedule
        not_from:
          - "unknown" 
          - "unavailable"
    condition:
      - condition: state
        entity_id: binary_sensor.vaillant_system_fault
        state: 'off'
    action:
      - choose:
          # Gas boiler should be active
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.total_gas_boiler_schedule') | float > 0.1 }}"
            sequence:
              # Activate gas boiler
              - service: mqtt.publish
                data:
                  topic: "ebusd/bai/HeatingActive/set"
                  payload: "true"
                  
              - variables:
                  space_demand: "{{ states('sensor.emhass_gas_boiler_space_schedule') | float(0) }}"
                  dhw_demand: "{{ states('sensor.emhass_gas_boiler_dhw_schedule') | float(0) }}"
                  total_demand: "{{ space_demand + dhw_demand }}"
                  
              # Set operating mode based on demand split
              - if:
                  - condition: template
                    value_template: "{{ dhw_demand > 0 }}"
                then:
                  # DHW mode or combined mode
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/bai/OperatingMode/set"
                      payload: |
                        {% if space_demand > 0 %}
                          3  # Combined heating and DHW
                        {% else %}
                          2  # DHW only
                        {% endif %}
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/bai/DHWTempSetpoint/set"
                      payload: "55"
                else:
                  # Space heating only
                  - service: mqtt.publish
                    data:
                      topic: "ebusd/bai/OperatingMode/set"
                      payload: "1"  # Heating only
                      
              # Set thermal demand setpoint - let boiler control modulation
              - service: mqtt.publish
                data:
                  topic: "ebusd/bai/ThermalDemandSetpoint/set"
                  payload: "{{ total_demand }}"
                    
              # Set flow temperature based on outdoor temperature and demand
              - service: mqtt.publish
                data:
                  topic: "ebusd/bai/FlowTempSetpoint/set"
                  payload: |
                    {% set outdoor_temp = states('sensor.vaillant_outdoor_temperature') | float %}
                    {% if dhw_demand > 0 %}
                      55  # DHW requires higher temperature
                    {% elif outdoor_temp < -5 %}
                      55  # Very cold conditions
                    {% elif outdoor_temp < 0 %}
                      50  # Cold conditions  
                    {% elif outdoor_temp < 10 %}
                      45  # Mild cold
                    {% else %}
                      40  # Mild conditions
                    {% endif %}
          
          # Gas boiler should be inactive
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.total_gas_boiler_schedule') | float <= 0.1 }}"
            sequence:
              - service: mqtt.publish
                data:
                  topic: "ebusd/bai/HeatingActive/set"
                  payload: "false"
```

### Advanced Coordination Logic

For systems where both heat sources might be active simultaneously:

```yaml
automation:
  - alias: "Coordinate Parallel Heat Source Operation"
    trigger:
      - platform: state
        entity_id:
          - sensor.total_heat_pump_schedule
          - sensor.total_gas_boiler_schedule
    condition:
      - condition: template
        value_template: |
          {{ states('sensor.total_heat_pump_schedule') | float > 0.1 and 
             states('sensor.total_gas_boiler_schedule') | float > 0.1 }}
    action:
      # Coordinate parallel operation
      - service: mqtt.publish
        data:
          topic: "ebusd/system/ParallelMode/set"
          payload: "true"
          
      # Set priority based on application
      - if:
          - condition: template
            value_template: "{{ states('sensor.emhass_gas_boiler_dhw_schedule') | float > 0 }}"
        then:
          # GB handles DHW, HP handles space heating
          - service: mqtt.publish
            data:
              topic: "ebusd/bai/Priority/set"
              payload: "dhw"
          - service: mqtt.publish
            data:
              topic: "ebusd/hp/Priority/set"
              payload: "space_heating"
        else:
          # Both handle space heating - load sharing
          - service: mqtt.publish
            data:
              topic: "ebusd/system/LoadSharing/set"
              payload: "true"
```

## Benefits of This Approach

### 1. **Optimization-Driven Decisions**
- EMHASS has complete visibility of energy prices, forecasts, and constraints
- Decisions are made with full knowledge of the optimization horizon
- Accounts for thermal storage and load shifting opportunities

### 2. **Economic Intelligence**
- Real-time cost optimization based on actual electricity vs gas prices
- No fixed economic bivalence point - decisions adapt to market conditions
- Heat source selection based on total cost including efficiency considerations

### 3. **Precise Vaillant Control**
- Direct translation of optimization results to ebusd commands
- Real-time system coordination via MQTT
- Optimal setpoints for temperatures, modulation, and operating modes

### 4. **System Intelligence**
- Considers heat pump capacity limitations at different temperatures
- Optimizes for both efficiency and cost
- Handles parallel operation when beneficial

This approach leverages EMHASS's sophisticated optimization capabilities while providing precise, real-time control of your Vaillant heating system through ebusd integration.

## Why This Approach Is Superior

### Economic Optimization vs Fixed Bivalence Points

Traditional hybrid heating systems use fixed economic bivalence points (e.g., "use gas boiler below 2°C"). This approach is flawed because:

- **Static Decision Making**: Fixed temperature thresholds can't adapt to changing energy prices
- **Missed Opportunities**: When electricity is cheap/free (high renewable generation), heat pumps should run even at low efficiency
- **Suboptimal Economics**: Gas might be expensive relative to electricity regardless of outdoor temperature

**EMHASS Dynamic Approach**: 
- Considers real-time energy prices every optimization cycle
- Automatically switches to heat pump when electricity becomes cheap, even at -10°C
- Factors in efficiency curves AND fuel costs simultaneously
- Adapts to market conditions (negative electricity prices, gas price spikes, etc.)

### Setpoint Control vs Direct Modulation

**Why Setpoint Control Is Better:**

1. **Manufacturer Optimization**: Boiler manufacturers spend years optimizing internal control algorithms
2. **Safety**: Respects built-in safety systems and control logic
3. **Stability**: Less prone to oscillations and control conflicts
4. **Adaptive**: Boiler adjusts modulation dynamically based on actual vs target performance
5. **Future-Proof**: Works with firmware updates and advanced boiler features

**Example Scenarios:**
```yaml
# Good: Set thermal demand, let boiler optimize
topic: "ebusd/bai/ThermalDemandSetpoint/set"
payload: "15.5"  # kW thermal demand

# Good: Set flow temperature target
topic: "ebusd/bai/FlowTempSetpoint/set"
payload: "45"  # °C target temperature

# Avoid: Direct modulation override
# topic: "ebusd/bai/ModulationLevel/set"  
# payload: "65"  # % - bypasses boiler intelligence
```

### Real-World Example

**Scenario**: Outdoor temperature -3°C, high wind generation causing negative electricity prices

**Traditional Bivalence Logic**: 
- Economic bivalence point = 2°C
- System activates gas boiler (outdoor temp < 2°C)
- Misses opportunity to use free electricity

**EMHASS Dynamic Logic**:
- Sees electricity price = -0.05 €/kWh, gas = 0.08 €/kWh  
- Calculates: Heat pump @ COP 2.5 = -0.02 €/kWh thermal
- Activates heat pump despite low outdoor temperature
- **Result**: Gets paid to heat the house while saving on gas 