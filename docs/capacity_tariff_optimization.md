# Optimizing for Capacity Tariffs (Demand Charges) in EMHASS

This document outlines a proposed approach to enhance EMHASS to consider capacity tariffs (often referred to as demand charges) in its optimization process. These tariffs are typically based on the peak power consumption (e.g., highest average kW over a 15-minute interval) within a billing period (e.g., monthly).

## 1. Rationale and Benefits

Capacity tariffs can form a significant portion of an electricity bill. Optimizing for them involves not just reducing total energy consumption (kWh) but also managing and reducing the peak power demand (kW).

*   **Cost Reduction:** Directly targets a potentially large cost component of the electricity bill.
*   **Improved Load Shaping:** Encourages smoother load profiles by avoiding high, short-duration peaks.
*   **Enhanced Grid Friendliness:** Helps reduce stress on the electricity grid during peak times.

## 2. Understanding Capacity Tariffs

Typical characteristics:

*   **Peak Measurement:** Based on the highest average power demand over a specified interval (e.g., 15 minutes, 30 minutes, 1 hour) within a billing cycle (usually a month).
*   **Billing Cycle:** The peak for the current month sets the charge for that month.
*   **Tariff Rate:** A cost per unit of peak power (e.g., €/kW/month).
*   **Longer-Term Averaging (Optional):** Some tariffs might be based on an average of monthly peaks over a longer period (e.g., a year). This proposal primarily focuses on managing the current month's peak, which is the most direct control point.

## 3. Proposed Modeling Approach within EMHASS

This involves tracking the current month's peak demand and incorporating a cost for exceeding it into the optimization.

**3.1. Persistent State Tracking:**

EMHASS needs to store and retrieve the peak demand achieved so far within the current billing month.

*   **State Variable (Persistent):**
    *   `Current_Month_Peak_Power_kW`: The highest average power demand (over the defined tariff interval, e.g., 15 minutes) recorded in the current billing month up to the last optimization run. This value must be saved by EMHASS and reloaded for each new optimization.
    *   This variable is reset at the beginning of each new billing month.

**3.2. Optimization Horizon Variables and Constraints:**

Within each optimization run (e.g., for the next 24-48 hours):

*   **Input (Calculated per Tariff Interval `i`):**
    *   `Total_Load_kW[i]`: The sum of all forecasted and scheduled loads (grid import) for each tariff-relevant interval `i` (e.g., each 15-minute block) within the optimization window. This is derived from the optimizer's scheduling of individual appliances, EV, heating, battery, etc.
*   **Decision Variable (for the current optimization run):**
    *   `Prospective_Horizon_Peak_Power_kW`: A variable representing the maximum `Total_Load_kW[i]` that will occur across all intervals `i` *within the current optimization horizon*.
*   **Constraint Linking `Prospective_Horizon_Peak_Power_kW` to `Total_Load_kW[i]`:**
    *   `Prospective_Horizon_Peak_Power_kW >= Total_Load_kW[i]` for all relevant intervals `i`.
    (The optimizer, aiming to minimize costs, will effectively set `Prospective_Horizon_Peak_Power_kW` to the actual peak during the horizon if that peak influences costs.)

**3.3. Cost Calculation in Objective Function:**

The core of the capacity tariff optimization is adding a cost component that penalizes the creation of a new, higher monthly peak.

*   **Capacity Tariff Rate Parameter:**
    *   `Capacity_Tariff_Rate_per_kW_per_Month`: The cost per kW of peak demand for the month (e.g., €2.50 / kW / month).
*   **Objective Function Component for Incremental Capacity Cost:**
    Let `Peak_Increase_kW` be an auxiliary variable.
    The incremental cost term added to the objective function to be minimized is:
    `Incremental_Capacity_Cost_Term = Peak_Increase_kW * Capacity_Tariff_Rate_per_kW_per_Month`

    With the following constraints to define `Peak_Increase_kW` (linearizing the `max(0, ...)` logic):
    1.  `Peak_Increase_kW >= Prospective_Horizon_Peak_Power_kW - Current_Month_Peak_Power_kW`
    2.  `Peak_Increase_kW >= 0`

    This formulation ensures that a cost is only incurred if the `Prospective_Horizon_Peak_Power_kW` (the peak planned for the upcoming optimization window) exceeds the `Current_Month_Peak_Power_kW` (the peak already set for the month). The optimizer will try to keep `Peak_Increase_kW` at 0 if possible.

**3.4. Post-Optimization Update:**

*   After an optimization run, EMHASS determines the actual highest scheduled `Total_Load_kW[i]` from its plan.
*   The persistent `Current_Month_Peak_Power_kW` is updated:
    `Current_Month_Peak_Power_kW = max(Current_Month_Peak_Power_kW, Actual_Scheduled_Peak_this_Run_kW)`

**3.5. Handling Longer-Term (e.g., Yearly) Averaging:**

Directly optimizing a yearly average of monthly peaks in each short-term run is complex. Practical strategies include:

*   **Monthly Peak Targeting:** Users can define a `Target_Monthly_Peak_kW` parameter for EMHASS. The cost calculation would then penalize exceeding `max(Current_Month_Peak_Power_kW, Target_Monthly_Peak_kW)`. This allows users to work towards a yearly average by setting conservative monthly targets.
*   **Manual/External Adjustment:** Users can monitor their evolving yearly average and adjust their monthly targets or operational strategies accordingly.
*   **Focus on Current Month:** Often, minimizing the current month's peak provides the most significant and actionable savings.

## 4. Configuration Parameters Needed for EMHASS

*   `enable_capacity_tariff_optimization`: Boolean (e.g., `true`/`false`).
*   `capacity_tariff_rate_cost_per_kw`: The monetary rate for the tariff (e.g., `2.50` if currency is defined elsewhere or implied).
*   `capacity_tariff_interval_minutes`: The interval over which the peak is measured (e.g., `15`, `30`, `60`). EMHASS will need to aggregate its internal shorter timesteps to these intervals for peak calculation.
*   `capacity_tariff_billing_day_of_month`: (Optional, for automating reset) The day of the month when the billing cycle resets and `Current_Month_Peak_Power_kW` should be reset (e.g., `1`).
*   `persistent_state_path`: Path to a file where `Current_Month_Peak_Power_kW` and its last update timestamp/month can be stored.
*   `target_monthly_peak_kw` (Optional): A user-defined target monthly peak in kW.

## 5. Problem Type and Solver Impact

*   The addition of these variables and linearized constraints should keep the problem as a **Mixed-Integer Linear Program (MILP)** if the base EMHASS model is already MILP.
*   The increase in model size is relatively small, and performance impact on modern solvers should be manageable.
*   The main implementation complexity lies in the persistent state management and the logic for aggregating loads to the tariff interval.

## 6. Conclusion

Incorporating capacity tariff optimization into EMHASS would allow it to make more economically sound decisions by managing peak power demand alongside energy consumption. This feature is crucial for users in regions with demand charges, providing a more comprehensive approach to home energy cost minimization. Careful management of the persistent peak state and clear configuration options for the user will be key to a successful implementation. 