# Native Electric Vehicle (EV) Charging Optimization in EMHASS

This document outlines a proposal for a native Electric Vehicle (EV) charging component within EMHASS. This component would allow for more precise, intuitive, and optimized scheduling of EV charging loads.

## 1. Rationale and Benefits

EV charging represents a significant and often flexible electrical load in a household. Native support in EMHASS offers several advantages over treating it as a generic deferrable load:

*   **Simplified User Configuration:** Users can provide EV-specific parameters directly (e.g., battery capacity, target State of Charge (SoC), departure time, max charging rate), making setup easier and less error-prone.
*   **Accurate Modeling:**
    *   **State of Charge (SoC) Tracking:** Explicitly models and tracks the EV's SoC throughout the optimization horizon.
    *   **Departure Deadlines:** Handles the critical constraint of having the EV ready by a specific departure time.
    *   **Variable Charging Rates:** Can model chargers/EVs that support different power levels, allowing the optimizer to choose the most economical rate.
    *   **Charging Efficiency:** Accounts for energy losses inherent in the charging process.
*   **Tailored Optimization Strategies:** Enables strategies like cost minimization (time-of-use tariffs), maximizing PV self-consumption for charging, ensuring departure readiness, and potentially grid-friendly charging patterns.
*   **Clearer System Outputs:** Provides users with specific feedback on the EV charging schedule and expected outcomes.
*   **Foundation for Advanced Features:** Could support future integrations like real-time EV API data or dynamic schedule adjustments.

## 2. Proposed Configuration Parameters

A new configuration section for the EV component would be introduced, requiring parameters such as:

*   **Core EV Details:**
    *   `ev_battery_capacity_kwh`: Total capacity of the EV's battery in kWh.
    *   `ev_target_soc_percent`: Desired State of Charge (as a percentage) by the departure time.
    *   `ev_min_soc_percent` (Optional): A minimum SoC to maintain, acting as a safety buffer (e.g., 20%).
*   **Charger/Charging Capabilities:**
    *   `ev_max_charge_rate_kw`: Maximum charging power the EV or EVSE (charger) can handle in kW.
    *   `ev_min_charge_rate_kw` (Optional): Minimum charging power if the charger/EV supports modulation and has a lower bound other than zero (e.g., 1.4 kW for a 6A single-phase charge). Defaults to 0 or a small value if variable.
    *   `ev_charging_efficiency_percent`: The efficiency of the charging process (e.g., 90% means 10% loss).
*   **Sensor Inputs (from Home Assistant or other integrations):**
    *   `ev_current_soc_percent_sensor`: Entity ID of the sensor providing the EV's current SoC (%).
    *   `ev_plugged_in_status_sensor`: Entity ID of a binary sensor indicating if the EV is plugged in and ready to charge.
    *   `ev_departure_time_sensor`: Entity ID of a sensor (e.g., `input_datetime` in Home Assistant) specifying the next planned departure time.

## 3. Integration into the EMHASS Optimization Model

The native EV component would be integrated into the EMHASS optimization core as follows:

*   **Decision Variables (for each timestep `t`):**
    *   `EV_Charge_Power_kW[t]`: The electrical power (kW) to be drawn by the EV charger during timestep `t`. This can be a continuous variable or a selection from discrete power levels if the charger/EV supports it.
*   **State Variables (tracked across timesteps `t`):**
    *   `EV_SoC_kWh[t]`: The amount of energy stored in the EV battery (in kWh) at the end of timestep `t`.
*   **Key Constraints (for each timestep `t` where applicable):**
    *   **SoC Update Equation:** Links the SoC of the current timestep to the previous one and the charge power applied:
        `EV_SoC_kWh[t] = EV_SoC_kWh[t-1] + (EV_Charge_Power_kW[t-1] * (ev_charging_efficiency_percent / 100) * Timestep_Duration_hours)`
        This update only occurs if `ev_plugged_in_status_sensor` is true and `EV_SoC_kWh[t-1]` is below `ev_battery_capacity_kwh`.
    *   **Charging Power Limits:**
        *   `0 <= EV_Charge_Power_kW[t] <= ev_max_charge_rate_kw`
        *   If `ev_min_charge_rate_kw` is defined: `EV_Charge_Power_kW[t]` is either 0 or between `ev_min_charge_rate_kw` and `ev_max_charge_rate_kw`.
        *   `EV_Charge_Power_kW[t] = 0` if `ev_plugged_in_status_sensor` is false or `EV_SoC_kWh[t]` reaches `ev_battery_capacity_kwh`.
    *   **Battery Capacity Limits:**
        `(ev_min_soc_percent / 100) * ev_battery_capacity_kwh <= EV_SoC_kWh[t] <= ev_battery_capacity_kwh`
    *   **Departure Target Constraint:** This is a critical constraint.
        `EV_SoC_kWh[DepartureTimestep] >= (ev_target_soc_percent / 100) * ev_battery_capacity_kwh`
        (Where `DepartureTimestep` is the timestep corresponding to `ev_departure_time_sensor`).
*   **Objective Function Integration:**
    The cost associated with `EV_Charge_Power_kW[t]` (i.e., `EV_Charge_Power_kW[t] * Electricity_Price_Forecast[t] * Timestep_Duration_hours`) is added to EMHASS's main objective function, which seeks to minimize overall electricity costs while respecting all system constraints.

## 4. Problem Type

This formulation, with appropriate handling of any discrete charging levels, would typically result in a **Mixed-Integer Linear Program (MILP)**. This is consistent with EMHASS's likely optimization approach.

## 5. Example Optimization Goals Achievable

*   Charge EV to 80% by 7:00 AM using the cheapest possible grid electricity overnight.
*   Prioritize charging the EV using excess solar PV during the day, then top up from the grid if needed to meet the departure target.
*   Avoid charging the EV during peak tariff hours (e.g., 4 PM - 7 PM) unless absolutely necessary to meet the departure SoC.

## 6. Conclusion

A native EV charging component would be a significant and logical enhancement for EMHASS. It simplifies configuration, improves modeling accuracy, and allows for more sophisticated optimization strategies tailored to the unique characteristics of EV loads. This would provide users with greater control over their energy consumption and costs related to electric vehicle charging. 

## 7. Future Considerations and Advanced Scenarios

While the core proposal addresses typical EV charging needs, several advanced scenarios and potential enhancements could be considered for future development:

*   **Multi-Day Look-Ahead / Adaptive Target SoC:**
    *   **Challenge:** The standard optimization horizon (e.g., 24-48 hours) might not capture significantly different charging conditions further in the future (e.g., a very sunny day followed by several cloudy/expensive days).
    *   **Potential Solution:** Introduce a mechanism for EMHASS to dynamically adjust the `ev_target_soc_percent` for the immediate departure based on a longer-range forecast (e.g., 3-5 days). If conditions for charging are predicted to be poor *after* the next departure but *before a subsequent likely departure*, the system could aim to "overcharge" the EV using current favorable conditions (e.g., excess solar) to a higher SoC (e.g., 95-100% instead of a typical 80%) to buffer against future expensive charging. This could be managed by:
        *   External logic (e.g., a Home Assistant automation) that modifies the `ev_target_soc_percent` input to EMHASS.
        *   Native EMHASS functionality requiring access to longer-range (but less certain) forecasts and new configuration parameters to define this adaptive behavior (e.g., `ev_lookahead_days`, `ev_adaptive_soc_increment_percent`).

*   **Variable Utility Tariffs with Complex Structures:**
    *   Handling tariffs with more than just peak/off-peak, such as tiered rates, demand charges tied to EV charging, or real-time dynamic pricing beyond simple forecasts.

*   **Vehicle-to-Grid (V2G) or Vehicle-to-Home (V2H):**
    *   **Challenge:** This involves allowing the EV to discharge power back to the grid or home, turning the EV into a controllable battery storage system.
    *   **Complexity:** Adds significant complexity, requiring modeling of discharge capabilities, efficiency, battery degradation from discharging, and utility/regulatory approval. The decision variables would need to include `EV_Discharge_Power_kW[t]`.

*   **Battery Health Considerations:**
    *   Incorporating charging strategies that may prolong battery life, such as preferring slower charging rates when time allows or avoiding prolonged periods at very high or very low SoC, if these can be quantified into the optimization.

*   **Integration with Dynamic Departure Times / User Overrides:**
    *   More seamless handling of unexpected changes to the `ev_departure_time_sensor` or manual overrides by the user, potentially triggering re-optimization.

*   **Multiple EVs:**
    *   Supporting households with more than one EV, each with its own parameters and charging schedule, potentially sharing a single charger or having dedicated chargers. This would involve replicating the EV component's variables and constraints for each vehicle.

These advanced features can be built upon the foundational native EV charging component, progressively enhancing EMHASS's capabilities. 