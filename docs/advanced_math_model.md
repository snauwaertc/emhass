# An EMS based on Linear Programming

In this section, we present the basics of the Linear Programming (LP) approach for a household Energy Management System (EMS).

## Motivation

Home Assistant allows us to monitor solar production, power consumption, and batteries, but managing these devices efficiently is a complex challenge. While basic rules and fixed schedules are simple to implement, they rarely achieve true optimality.

EMHASS (Energy Management for Home Assistant) bridges this gap by implementing a Linear Programming (LP) optimization framework. Instead of relying on static heuristics, EMHASS uses weather and consumption forecasts to automatically schedule controllable loads (such as water heaters, pool pumps, and batteries).

Key highlights:

- Optimization vs. Rules: Real-world testing shows a 5-8% daily economic gain using EMHASS compared to standard rule-based systems.

- Dynamic Decision Making: The system automatically decides whether to run appliances during solar peaks or off-peak tariff hours based on the day's forecast.

- Practical Integration: While inspired by advanced tools like OMEGAlpes, EMHASS focuses on practical implementation, enabling users to deploy academic-grade optimization directly within their Home Assistant environment via configuration files.

## Linear programming

Linear programming is an optimization method that can be used to obtain the best solution from a given cost function using linear modelling of a problem. Typically we can also add linear constraints to the optimization problem.

This can be mathematically written as:

$$
  & \underset{x}{\text{Maximize  }} && \mathbf{c}^\mathrm{T} \mathbf{x}\\
  & \text{subject to  } && A \mathbf{x} \leq \mathbf{b} \\
  & \text{and  } && \mathbf{x} \ge \mathbf{0}
$$

with $\mathbf{x}$  the variable vector that we want to find, $\mathbf{c}$ and $\mathbf{b}$ are vectors with known coefficients and $\mathbf{A}$ is a matrix with known values. Here the cost function is defined by $\mathbf{c}^\mathrm{T} \mathbf{x}$. The inequalities $A \mathbf{x} \leq \mathbf{b}$ and $\mathbf{x} \ge \mathbf{0}$ represent the convex region of feasible solutions. 

We could find a mix of real and integer variables in $\mathbf{x}$, in this case the problem is referred as Mixed Integer Linear Programming (MILP). Typically this kind of problem uses 'branch and bound' type solvers, or similar.

The LP has, of course, its set of advantages and disadvantages. The main advantage is that if the problem is well posed and the region of feasible possible solutions is convex, then a solution is guaranteed and solving times are usually fast when compared to other optimization techniques (such as dynamic programming for example). However we can easily fall into memory issues, larger solving times and convergence problems if the size of the problem is too high (too many equations).

## Household EMS with LP

The LP problem for the household EMS is solved in EMHASS using different user-chosen cost functions.

Three main cost functions are proposed.

### Cost functions

#### 1) The _profit_ cost function

In this case, the cost function is posed to maximize the profit. The profit is defined by the revenues from selling PV power to the grid minus the cost of consumed energy from the grid. 
This can be represented with the following objective function:

$$
\sum_{i=1}^{\Delta_{opt}/\Delta_t} -0.001*\Delta_t*(unit_{LoadCost}[i]*P_{gridPos}[i] + prod_{SellPrice}*P_{gridNeg}[i])
$$

> For the special case of an energy contract where the totality of the PV-produced energy is injected into the grid this will be:

$$
\sum_{i=1}^{\Delta_{opt}/\Delta_t} -0.001*\Delta_t*(unit_{LoadCost}[i]*(P_{load}[i]+P_{defSum}[i]) + prod_{SellPrice}*P_{gridNeg}[i])
$$

where $\Delta_{opt}$ is the total period of optimization in hours, $\Delta_t$ is the optimization time step in hours, $unit_{LoadCost_i}$ is the cost of the energy from the utility in EUR/kWh, $P_{load}$ is the electricity load consumption (positive defined), $P_{defSum}$ is the sum of the deferrable loads defined, $prod_{SellPrice}$ is the price of the energy sold to the utility, $P_{gridNeg}$ is the negative component of the grid power, this is the power exported to the grid. All these power values are expressed in Watts.

#### 2) The energy from the grid _cost_

In this case, the cost function is computed as the cost of the energy coming from the grid. The PV power injected into the grid is not valorized.
This is:

$$
\sum_{i=1}^{\Delta_{opt}/\Delta_t} -0.001*\Delta_t*unit_{LoadCost}[i]*P_{gridPos}[i]
$$

> Again, for the special case of an energy contract where the totality of the PV-produced energy is injected into the grid this will be:

$$
\sum_{i=1}^{\Delta_{opt}/\Delta_t} -0.001*\Delta_t* unit_{LoadCost}[i]*(P_{load}[i]+P_{defSum}[i])
$$

#### 3) The _self-consumption_ cost function

This is a cost function designed to maximize the self-consumption of the PV plant. 
```{note}
EMHASS has two methods for defining a self-consumption cost function: **bigm** and **maxmin**. In the current version, only the **bigm** method is used, as the maxmin method has convergence issues.
```

##### bigM self-consumption method
In this case, the cost function is based on the profit cost function, but the energy offtake cost is weighted more heavily than the energy injection revenue. 
This can be represented with the following objective function:

$$
\sum_{i=1}^{\Delta_{opt}/\Delta_t} -0.001*\Delta_t*(bigM*unit_{LoadCost}[i]*P_{gridPos}[i] + prod_{SellPrice}*P_{gridNeg}[i])
$$

where bigM equals 1000.
Adding this bigM factor will give more weight to the cost of grid offtake, or formulated differently: avoiding offtake through self-consumption will have a strong influence on the calculated cost.

Please note that the bigM factor is not used in the calculated cost that comes out of the optimizer results. It is only used to drive the optimizer.

> ##### **Maxmin self-consumption method** (currently disabled)
>
> The cost function is computed as the revenues from selling PV power to the grid, plus the avoided cost of consuming PV power locally (the latter means: valorizing the self-consumed cost at the grid offtake price).
>
> The self-consumption is defined as:
> 
> $$
> SC = \min(P_{PV}, (P_{load}+P_{defSum}))
> $$
> 
> To convert this to a linear cost function, an additional continuous variable $SC$ is added. This is the so-called maximin problem.
> The cost function is defined as:
> 
> $$
> \sum_{i=1}^{\Delta_{opt}/\Delta_t} SC[i]
> $$
> 
> With the following set of constraints:
> 
> $$
> SC[i] \leq P_{PV}[i]
> $$
> 
> and
> 
> $$
> SC[i] \leq P_{load}[i]+P_{defSum}[i]
> $$

All these cost functions can be chosen by the user with the `--costfun` tag with the `emhass` command. The options are: `profit`, `cost`, and `self-consumption`.
They are all set in the LP formulation as cost a function to maximize.

The problem constraints are written as follows.

### The main constraint: power balance

$$
P_{PV_i}-P_{defSum_i}-P_{load_i}+P_{gridNeg_i}+P_{gridPos_i}+P_{stoPos_i}+P_{stoNeg_i}=0
$$

with $P_{PV}$ the PV power production, $P_{gridPos}$ the positive component of the grid power (from the grid to household), $P_{stoPos}$ and $P_{stoNeg}$ are the positive (discharge) and negative components of the battery power (charge).

Normally the PV power production and the electricity load consumption are considered known. In the case of a day-ahead optimization, these should be forecasted values. When the optimization problem is solved the others power defining the power flow are found as a result: the deferrable load power, the grid power and the battery power.

### Other constraints

Some other special linear constraints are defined. A constraint is introduced to avoid injecting and consuming from the grid at the same time, which is physically impossible. Other constraints are used to control the total time that a deferrable load will stay on and the number of start-ups. 

Constraints are also used to define semi-continuous variables. Semi-continuous variables are variables that must take a value between their minimum and maximum or zero.

A final set of constraints is used to define the behavior of the battery. Notably:
- Ensure that maximum charge and discharge powers are not exceeded.
- Minimum and maximum state of charge values are not exceeded.
- Force the final state of charge value to be equal to the initial state of charge.

The minimum and maximum state of charge limitations can be expressed as follows:

$$
\sum_{i=1}^{k} \frac{P_{stoPos_i}}{\eta_{dis}} + \eta_{ch}P_{stoNeg_i} \leq \frac{E_{nom}}{\Delta_t}(SOC_{init}-SOC_{min})
$$

and

$$
-(\sum_{i=1}^{k} \frac{P_{stoPos_i}}{\eta_{dis}} + \eta_{ch}P_{stoNeg_i}) \leq \frac{E_{nom}}{\Delta_t}(SOC_{max}-SOC_{init})
$$

where $E_{nom}$ is the battery capacity in kWh, $\eta_{dis/ch}$ are the discharge and charge efficiencies and $SOC$ is the state of charge.

Forcing the final state of charge value to be equal to the initial state of charge can be expressed as follows:

$$
\sum_{i=1}^{k} \frac{P_{stoPos_i}}{\eta_{dis}} + \eta_{ch}P_{stoNeg_i} = \frac{E_{nom}}{\Delta_t}(SOC_{init}-SOC_{final})
$$

### Inverter Stress Cost (Smooth Operation)

There is the ability to apply a "Stress Cost" to your Hybrid Inverter. This feature adds a virtual cost to high-power operation, encouraging the system to run "low and slow" rather than jumping between 0% and 100% power for marginal gains.

Standard linear optimization often results in "bang-bang" control: the battery charges at maximum speed as soon as energy is cheap, and discharges at maximum speed as soon as it is profitable.

While mathematically optimal for profit, this can have downsides in the real world:

- Thermal Stress: Running at 100% generates significant heat.
- Fan Noise: High load triggers loud cooling fans.
- Efficiency Losses: Resistive losses ($I^2R$) increase quadratically with power.
- Battery Health: High C-rates can degrade battery chemistry faster.

The Inverter Stress Cost introduces a penalty that increases quadratically with power usage. The optimizer will now balance the "profit" from energy arbitrage against this "stress" penalty, preferring to spread the load over a longer time window if the price difference isn't massive.

The cost is modeled as a symmetric quadratic function of the inverter power ($Cost \propto Power^2$). Because EMHASS uses Linear Programming (LP), this quadratic curve is approximated using a Piecewise Linear function.

The penalty is calculated such that at Nominal Power (100% load), the stress cost equals your configured `inverter_stress_cost`.

- Low Power: Very low penalty.
- High Power: High penalty.

$$\text{Total Cost} = \text{Energy Cost} + \text{Stress Penalty}(P_{inverter})$$

To enable this, add the following parameters to your `config.json` (or `optim_conf` in `config_emhass.yaml`):

- `inverter_stress_cost` (float): The virtual penalty cost (in currency/kWh) applied if the inverter runs at its maximum nominal power (Recommended: 0.05 - 0.20).
- `inverter_stress_segments` (Integer): The number of linear segments used to approximate the quadratic curve. Higher values are more accurate but increase computation slightly (Recommended: 10).

Example usage using `runtimeparams`:
```bash
curl -i -H "Content-Type: application/json" -X POST -d '{
    "inverter_stress_cost": 0.5,
    "prediction_horizon": 24
}' http://localhost:5000/action/naive-mpc-optim
```

### Battery SOC Surplus Cost (high-SOC dwell penalty)

Standard cost optimization will charge the battery to 100% as soon as there is cheap or surplus energy, then leave it sitting full for hours. On a flat tariff there is no price signal to stop it. Sitting at a high state of charge for long periods accelerates calendar aging, and on sunny days it means the battery fills early and exports the rest of the midday peak to the grid instead of soaking it up gradually.

The SOC surplus cost adds a virtual penalty for every kWh the battery sits above a configured threshold, for every hour it stays there. The optimizer balances that penalty against the value of charging early, so it tends to delay and slow charging into the expected solar peak and spend less time near full charge. It is the mirror of the existing SOC deficit cost, which penalizes sitting below a low threshold.

Two parameters control it (both default to off):

- `battery_soc_surplus_threshold` (float): the SOC above which the penalty applies, for example `0.90` for 90%.
- `battery_soc_surplus_cost` (float): the virtual cost in currency/kWh/h applied for each kWh above the threshold per hour. The default of `0.0` leaves today's behaviour unchanged.

The penalty is linear in the energy held above the threshold:

$$\text{Surplus penalty} = \sum_{i} c_{surplus} \cdot \Delta_t \cdot \max\left(0,\; (SOC_i - SOC_{thr})\,E_{nom}\right)$$

where $c_{surplus}$ is `battery_soc_surplus_cost`, $SOC_{thr}$ is `battery_soc_surplus_threshold` and $E_{nom}$ is the battery capacity.

Example usage using `runtimeparams`:
```bash
curl -i -H "Content-Type: application/json" -X POST -d '{
    "battery_soc_surplus_threshold": 0.85,
    "battery_soc_surplus_cost": 0.1,
    "prediction_horizon": 24
}' http://localhost:5000/action/naive-mpc-optim
```

## Thermal storage and heat pumps

EMHASS optimizes heat alongside electricity. A thermal store - a hot-water tank, a
space-heating buffer, a pool, or the thermal mass of the house - is modelled as a
**temperature state** the optimizer steers through the horizon, the thermal
equivalent of a battery's state of charge. This section describes how those stores
enter the linear program, how non-electric sources are priced, and how the
temperature-dependent COP of a heat pump - which breaks linearity - is handled by a
dynamic-programming refinement.

For the user-facing configuration of these features see the
[Thermal Integration](section_thermal.md) section.

### Thermal store dynamics

Each store carries a temperature $T[i]$ that evolves by a first-order energy
balance:

$$
T[i+1] = T[i] + \frac{\Delta_t}{C}\Big(Q_{in}[i] + Q_{xfer}[i] - D[i] - L[i]\Big)
$$

where $C$ is the store's heat capacity in kWh/K (from a water `volume` or a
building `thermal_mass`), $Q_{in}$ is the heat delivered by its sources, $Q_{xfer}$
the net heat exchanged with other stores, $D$ the demand drawn from it (hot-water
draw-off and/or building heat loss), and $L$ the standing loss. The loss is either a
flat hot-water standing loss or, for a building zone, a **state-dependent** term
$L[i] = UA\,(T[i]-T_{out}[i])\,\Delta_t$ - so a warmer zone loses faster, which is
what lets the optimizer pre-heat the mass on cheap power and coast through a peak.

The heat a source contributes depends on its type. An electric resistive element
delivers $Q = \eta\,P_{elec}$; a gas or oil boiler delivers $Q = \eta\,P_{input}$; a
heat pump delivers $Q = \text{COP}\cdot P_{elec}$.

**Comfort bounds.** Each store has hard per-step minimum and maximum temperatures,
and an optional soft `desired_temperature` band whose shortfall is priced as a
penalty (so the optimizer pulls toward comfort when it is cheap, without rendering
the problem infeasible when it is not). Index 0 is pinned to the live measured
temperature, so every re-plan starts from the real sensor value.

**Start-temperature recovery.** If the live temperature starts *below* the hard
floor (a momentary out-of-band reading on a cold morning), demanding the full floor
from the next step would be infeasible - a high-mass store cannot jump back into
band in one step. EMHASS instead ramps the floor up from the measured start at a
conservative rate, so the store is only required to recover at a feasible pace; the
configured floor reapplies in full once it has caught up.

**Tank-to-tank transfers.** A store can feed another through an emitter conductance
(for example a buffer supplying a room or a pool). The transferred heat
$Q_{xfer}=k\,(T_{from}-T_{to})$ is bounded by a maximum delivered power, and leaves
the source store while entering the sink store in the same balance.

### Non-electric sources and the capacity tariff

A gas boiler, oil burner, or district-heat source produces heat without drawing
electricity. Such a source is flagged `is_electric_load = False`: its power is kept
**out of the electrical power balance** $P_{defSum}$, so firing the boiler creates no
phantom grid draw, and it is priced directly at its own commodity tariff (via its
`cost_track`) rather than the retail electricity price:

$$
\text{cost}_{k} = \sum_i \Delta_t \cdot c_k[i]\cdot P_{k}[i] \qquad (\text{non-electric load } k)
$$

For an electric load the per-load cost is instead applied as an *adjustment*
$\big(c_k[i]-unit_{LoadCost}[i]\big)P_k[i]$ on top of the shared tariff, so a load
with its own price ends up charged at exactly that price. Because non-electric
sources never enter the grid-import term, they are also **excluded from the
capacity (peak-power) tariff** - only electrical import counts toward the billed
peak.

### The temperature-dependent COP and why it is non-convex

A heat pump's coefficient of performance falls as it has to push the store hotter.
EMHASS uses a Carnot-fraction model:

$$
\text{COP}(T) = \eta_{Carnot}\cdot\frac{T_{supply}+273.15}{T_{supply}-T_{out}},
\qquad T_{supply}=T+\delta_{approach}
$$

clipped to a physical range (default $[1, 8]$), where $\delta_{approach}$ is the
heat-exchanger approach between the store and the condenser. The delivered heat is
then

$$
Q = \text{COP}(T)\cdot P_{elec}
$$

a **bilinear product** of the (chosen) temperature and the electric power - a
non-convex coupling a single linear program cannot represent. The MILP therefore
plans against a COP *linearized at an assumed temperature*. That is fine as long as
the store ends up near that temperature, but if super-heating is profitable - for
instance to bank surplus PV into the buffer - the MILP would happily super-heat at
the optimistic assumed COP, even though the real condenser must run hotter and the
true COP is lower.

### Dynamic-programming COP refinement

To recover the true optimum without abandoning the fast LP, EMHASS adds a post-solve
**dynamic-programming (DP) refinement**:

1. **Consistency check (auto-trigger).** For each heat-pump store, compare the COP
   the solve *used* against $\text{COP}(T)$ evaluated at the temperature the solve
   actually *reached*. If they agree within a tolerance the plan is already
   self-consistent and nothing happens - the DP is a no-op exactly when it is not
   needed. It engages only when the discrepancy exceeds the tolerance.
2. **Exact DP.** When engaged, EMHASS discretizes the store temperature into a grid
   and solves the store's trajectory by backward induction, evaluating the *true*
   COP at every state. Dynamic programming handles the non-convexity directly: no
   linearization, and a single backward pass yields the globally optimal temperature
   schedule and heat-pump/backup dispatch.
3. **Coupled store.** A buffer that feeds a larger banking store (such as a pool)
   can be refined *jointly* - a second state in the DP - so the decision to
   super-heat accounts for what the coupled store can absorb. The coupled grid is
   bounded to keep the state space tractable.
4. **Re-solve.** The DP's COP, and a ceiling at the DP-optimal peak temperature, are
   fed back as a corrected parameter and an extra constraint, and the LP is solved
   once more. The ceiling prevents the re-solve from exploiting the now-fixed
   favourable COP by super-heating past the true optimum.

If the refinement fails for any reason it degrades safely to the original LP plan.

**Marginal price - super-heating into PV.** The DP is driven not by the raw import
tariff but by the **marginal** cost of running the heat pump at each step. Where the
system is importing, that is the import tariff; where PV is in surplus and the system
is exporting, running the heat pump instead *forgoes the export revenue*, so its true
marginal cost is the (lower) export price:

$$
p_{marg}[i] = \begin{cases}
prod_{SellPrice}[i] & \text{if exporting (PV surplus)}\\
unit_{LoadCost}[i] & \text{otherwise}
\end{cases}
$$

Feeding this to the DP is what makes it super-heat the store into otherwise-exported
solar rather than only chasing the cheapest tariff hour.

**Per-step COP.** The COP grid the DP optimizes against is two-dimensional,
$\text{COP}[i, T]$, indexed by both the timestep and the store temperature, so the
intraday swing in outdoor temperature - a cold dawn, a mild PV-rich midday - is
reflected in the true COP at each hour instead of being averaged away.

### The `cop_solver` setting

The refinement is controlled by two `optim_conf` options:

- `cop_solver` (`auto` | `dp` | `static`): `auto` runs the consistency check and
  engages the DP only when the static COP is inconsistent (the default); `dp` always
  runs it; `static` disables it and keeps the pure-LP plan.
- `cop_solver_tolerance` (float, °C-equivalent COP error): how large a COP
  discrepancy `auto` tolerates before engaging the DP.

## The EMHASS optimizations

There are 3 different optimization types that are implemented in EMHASS.

- A perfect forecast optimization.

- A day-ahead optimization.

- A Model Predictive Control optimization.

The following example diagram may help us understand the time frames of these optimizations:

![](./images/optimization_graphics.png)

### Perfect forecast optimization

This is the first type of optimization task that is proposed with this package. In this case, the main inputs, the PV power production and the house power consumption are fixed using historical values from the past. This means that in some way we are optimizing a system with a perfect knowledge of the future. This optimization is of course non-practical in real life. However, this can give us the best possible solution to the optimization problem that can be later used as a reference for comparison purposes. In the example diagram presented before, the perfect optimization is defined on a 5-day period. These historical values will be retrieved from the Home Assistant database.

### Day-ahead optimization

In this second type of optimization task, the PV power production and the house power consumption are forecasted values. This is the action that should be performed in a real case scenario and is the case that should be launched from Home Assistant to obtain an optimized energy management plan for future actions. This optimization is defined in the time frame of the next 24 hours.

As the optimization is bounded to forecasted values, it will also be bounded to uncertainty. The quality and accuracy of the optimization results will be inevitably linked to the quality of the forecast used for these values. The better the forecast error, the better the accuracy of the optimization result.

### Model Predictive Control (MPC) optimization

An MPC controller was introduced in v0.3.0. This is an informal/naive representation of a MPC controller. 

This type of controller performs the following actions:

- Set the prediction horizon: a fixed value for a receding horizon or a variable value for a shrinking horizon approach.
- Perform an optimization on the prediction horizon.
- Apply the first element of the obtained optimized control variables.
- Repeat at a relatively high frequency, ex: 5 min.

In the example diagram presented before, the MPC is performed at 6h intervals at 6h, 12h and 18h. The prediction horizon is progressively reduced during the day to keep the one-day energy optimization notion (it should not just be a fixed rolling window as, for example, you would like to know when you want to reach the desired `soc_final`). This type of optimization is used to take advantage of actualized forecast values during throughout the day. The user can of course choose higher/lower implementation intervals, keeping in mind the constraints below on the `prediction_horizon`.

When applying this controller, the following `runtimeparams` should be defined:

- `prediction_horizon` for the MPC prediction horizon. Fix this at least 5 times the optimization time step.

- `soc_init` for the initial value of the battery SOC for the current iteration of the MPC. 

- `soc_final` for the final value of the battery SOC for the current iteration of the MPC. 

- `operating_hours_of_each_deferrable_load` for the list of deferrable loads functioning hours. These values can decrease as the day advances to take into account the shrinking horizon daily energy objectives for each deferrable load.

- `start_timesteps_of_each_deferrable_load` for the timestep as from which each deferrable load is allowed to operate (if you don't want the deferrable load to use the whole optimization timewindow). If you specify a value of 0 (or negative), the deferrable load will be optimized as from the beginning of the complete prediction horizon window.

- `end_timesteps_of_each_deferrable_load` for the timestep before which each deferrable load should operate (if you don't want the deferrable load to use the whole optimization timewindow). If you specify a value of 0 (or negative), the deferrable load will be optimized over the complete prediction horizon window.

In a practical use case, the values for `soc_init` and `soc_final` for each MPC optimization can be taken from the initial day-ahead optimization performed at the beginning of each day.

A correct call for an MPC optimization should look like this:

```bash
curl -i -H 'Content-Type:application/json' -X POST -d '{"pv_power_forecast":[0, 70, 141.22, 246.18, 513.5, 753.27, 1049.89, 1797.93, 1697.3, 3078.93], "prediction_horizon":10, "soc_init":0.5,"soc_final":0.6}' http://192.168.3.159:5000/action/naive-mpc-optim
```
*Example with :`operating_hours_of_each_deferrable_load`, `start_timesteps_of_each_deferrable_load`, `end_timesteps_of_each_deferrable_load`.*
```bash
curl -i -H 'Content-Type:application/json' -X POST -d '{"pv_power_forecast":[0, 70, 141.22, 246.18, 513.5, 753.27, 1049.89, 1797.93, 1697.3, 3078.93], "prediction_horizon":10, "soc_init":0.5,"soc_final":0.6,"operating_hours_of_each_deferrable_load":[1,3],"start_timesteps_of_each_deferrable_load":[0,3],"end_timesteps_of_each_deferrable_load":[0,6]}' http://localhost:5000/action/naive-mpc-optim
```

For a more readable option we can use the `rest_command` integration:
```yaml
rest_command:
  url: http://127.0.0.1:5000/action/naive-mpc-optim
  method: POST
  headers:
    content-type: application/json
  payload: >-
    {
      "pv_power_forecast": [0, 70, 141.22, 246.18, 513.5, 753.27, 1049.89, 1797.93, 1697.3, 3078.93],
      "prediction_horizon":10,
      "soc_init":0.5,
      "soc_final":0.6,
      "operating_hours_of_each_deferrable_load":[1,3],
      "start_timesteps_of_each_deferrable_load":[0,3],
      "end_timesteps_of_each_deferrable_load":[0,6]
    }
```

## Time windows for deferrable loads
Since v0.7.0, the user has the possibility to limit the operation of each deferrable load to a specific timewindow, which can be smaller than the prediction horizon. This is done by means of the `start_timesteps_of_each_deferrable_load` and `end_timesteps_of_each_deferrable_load` parameters. These parameters can either be set in the configuration screen of the Home Assistant EMHASS add-on, or in the config_emhass.yaml file, or provided as runtime parameters.

Take the example of two electric vehicles that need to charge, but which are not available during the whole prediction horizon:
![image](./images/deferrable_timewindow_evexample.png)

For this example, the settings could look like this:
Either in the Home Assistant add-on config screen:
![image](./images/deferrable_timewindow_addon_config.png)

Either as runtime parameter:
```
curl -i -H 'Content-Type:application/json' -X POST -d '{"prediction_horizon":30, 'operating_hours_of_each_deferrable_load':[4,2],'start_timesteps_of_each_deferrable_load':[4,0],'end_timesteps_of_each_deferrable_load':[27,23]}' http://localhost:5000/action/naive-mpc-optim
```

Please note that the proposed deferrable load time windows will be submitted to a validation step & can be automatically corrected.
Possible cases are depicted below:
![image](./images/deferrable_timewindow_edge_cases.png)


## References

- Camille Pajot, Lou Morriet, Sacha Hodencq, Vincent Reinbold, Benoit Delinchant, Frédéric Wurtz, Yves Maréchal, Omegalpes: An Optimization Modeler as an EfficientTool for Design and Operation for City Energy Stakeholders and Decision Makers, BS'15, Building Simulation Conference, Roma in September 24, 2019.

- Gabriele Comodi, Andrea Giantomassi, Marco Severini, Stefano Squartini, Francesco Ferracuti, Alessandro Fonti, Davide Nardi Cesarini, Matteo Morodo,
and Fabio Polonara. Multi-apartment residential microgrid with electrical and thermal storage devices: Experimental analysis and simulation of energy management strategies. Applied Energy, 137:854–866, January 2015.

- Pedro P. Vergara, Juan Camilo López, Luiz C.P. da Silva, and Marcos J. Rider. Security-constrained optimal energy management system for threephase
residential microgrids. Electric Power Systems Research, 146:371–382, May 2017.

- R. Bourbon, S.U. Ngueveu, X. Roboam, B. Sareni, C. Turpin, and D. Hernandez-Torres. Energy management optimization of a smart wind power plant comparing heuristic and linear programming methods. Mathematics and Computers in Simulation, 158:418–431, April 2019.
