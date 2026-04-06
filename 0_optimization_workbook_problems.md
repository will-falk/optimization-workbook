# optimization workbook: european electricity systems

*a progressive problem set using pyomo — from first lp to professional-grade energy system modelling.*

---

## how this workbook works

these ten problems tell a single story: you are an energy economics analyst at a european consultancy. a client — a coalition of central-western european transmission system operators — has asked you to build a series of models to inform investment and dispatch decisions across a simplified but realistic representation of the cwe region (germany, france, netherlands, belgium, poland).

each problem introduces one or two new optimisation concepts while teaching you something real about how european electricity markets work. the problems build on each other: data and model structures you create early on get reused and extended later. by the end, you'll have a working multi-zone, multi-period capacity expansion and dispatch model with storage, emissions policy, and uncertainty — the kind of thing an entry-level modeller at a tso, utility, or energy consultancy would actually build.

**how to check your work:** every problem includes a `## verification` section at the end with either (a) the expected numerical answer, (b) a short python script that checks your solution, or (c) qualitative checks you can perform to confirm correctness. some problems also include "sanity check" questions that test whether you understand the economic meaning of your results.

**solver note:** all problems can be solved with free solvers. problems 1–4 and 8 use glpk or highs (lp). problems 5–7 and 9–10 use cbc or highs (milp). no commercial solver is needed.

**data sources:** where possible, input data is drawn from or inspired by publicly available entso-e transparency platform data. links are provided so you can see where the numbers come from and explore further.

---

## notation conventions

throughout this workbook:

| symbol | meaning |
|--------|---------|
| $t \in t$ | time period (hour) |
| $g \in g$ | generator / technology |
| $z \in z$ | zone / bidding zone / country |
| $l \in l$ | transmission line / interconnector |
| $s \in s$ | scenario (for stochastic problems) |

---

## problem 1: the merit order — single-period economic dispatch

### concepts introduced
- linear programming fundamentals
- pyomo `concretemodel`, `set`, `param`, `var`, `objective`, `constraint`
- the merit order and marginal cost dispatch
- reading and interpreting solver output

### background

the **merit order** is the foundation of european electricity market design. generators are "stacked" in order of their short-run marginal cost (*srmc*) — the cost of producing one additional mwh. the cheapest generators run first. the most expensive generator needed to meet demand sets the **market clearing price** for everyone.

this is not just theory — it is literally how the euphemia algorithm clears the eu day-ahead market every day at noon. the algorithm is a large-scale optimisation problem. you are going to build a simplified version.

> **real-world reference:** the euphemia algorithm couples 27+ european bidding zones simultaneously. see [nemo committee — euphemia documentation](https://www.nemo-committee.eu/euphemia) and [entso-e transparency platform — day-ahead prices](https://transparency.entsoe.eu/transmission-domain/r2/dayaheadprices/show).

### setup

you are modelling a single hour of dispatch in a simplified representation of germany's de-lu bidding zone. germany phased out its last nuclear plant in april 2023, so the thermal fleet is lignite, hard coal, and gas. renewables (wind and solar) dominate installed capacity but their output depends on weather.

we use a **teaching-scale** system — proportionally representative of the real german fleet but small enough that you can verify every number by hand. marginal costs here are **fuel + variable o&m only, excluding the co₂ cost** — you'll add carbon pricing in problem 2, which is the whole point of that exercise.

**marginal cost derivations (2024–2025 fuel prices):**
- **lignite:** mined at pithead, ~€5/mwh_th fuel cost, ~35% efficiency → fuel component €14/mwh. add variable o&m → **€18/mwh**.
- **hard coal:** imported at ~$116/t (ara cif, feb 2025), ~6,000 kcal/kg → ~€12/mwh_th, ~38% efficiency → fuel €32/mwh. add o&m → **€36/mwh**.
- **gas ccgt:** ttf hub price ~€33/mwh_th (q1 2025 average), ~55% efficiency → fuel €60/mwh. add o&m → **€63/mwh**.
- **gas ccgt (older):** same fuel, ~50% efficiency → fuel €66/mwh. add o&m → **€70/mwh**.
- **gas ocgt:** ttf ~€33/mwh_th, ~38% efficiency → fuel €87/mwh. add o&m → **€92/mwh**.

> **fuel price sources:** ttf front-month averaged €29–36/mwh through q1 2025 ([trading economics](https://tradingeconomics.com/commodity/eu-natural-gas)). ara coal averaged $110–130/t ([trading economics](https://tradingeconomics.com/commodity/coal)). german lignite is essentially captive-mined at low cost.

| generator   | technology         | capacity (mw) | marginal cost (€/mwh) | cost basis                        |
| ----------- | ------------------ | ------------- | --------------------- | --------------------------------- |
| `lignite_1` | lignite            | 2,800         | 18                    | pithead fuel + o&m, excl. co₂     |
| `coal_1`    | hard coal          | 1,200         | 36                    | imported coal ara $116/t, 38% eff |
| `ccgt_1`    | gas ccgt           | 1,600         | 63                    | ttf €33/mwh_th, 55% eff           |
| `ccgt_2`    | gas ccgt (older)   | 1,000         | 70                    | ttf €33/mwh_th, 50% eff           |
| `ocgt_1`    | gas ocgt           | 600           | 92                    | ttf €33/mwh_th, 38% eff           |
| `wind`      | wind (on+offshore) | 4,000         | 0                     | zero marginal cost                |
| `solar`     | solar pv           | 3,000         | 0                     | zero marginal cost                |
|             |                    |               |                       |                                   |

> **fleet scale note:** germany's real installed capacity is ~64 gw onshore wind, ~9 gw offshore wind, ~99 gw solar, and ~20+ gw of thermal dispatchable (fraunhofer ise, 2024). we use a ~14 gw system that preserves the proportional mix and merit order structure while keeping the arithmetic manageable.

today's conditions (a moderately windy autumn afternoon):

- demand: **8,200 mw**
- wind availability factor: **0.28** → effective wind capacity = 4,000 × 0.28 = 1,120 mw
- solar availability factor: **0.15** → effective solar capacity = 3,000 × 0.15 = 450 mw
- total available supply: 1,120 + 450 + 2,800 + 1,200 + 1,600 + 1,000 + 600 = 8,770 mw (feasible with headroom)

> **where the capacity factors come from:** german onshore wind averaged ~25–35% cf depending on the year; 2024 was a below-average wind year per [copernicus esotc 2024](https://climate.copernicus.eu/esotc/2024/renewable-energy-resources). solar cf in germany averages ~10% annually but reaches 15–35% during afternoon hours in autumn. the 0.28 and 0.15 values represent a specific afternoon snapshot, not annual averages. see [entso-e actual generation per type](https://transparency.entsoe.eu/generation/r2/actualgenerationperproductiontype/show) for real hourly data.

### your task

**formulate and solve the following lp in pyomo:**

$$\min_{p_g} \sum_{g \in g} c_g \cdot p_g$$

subject to:

$$\sum_{g \in g} p_g = d \quad \text{(demand balance)}$$

$$0 \leq p_g \leq \bar{p}_g \quad \forall \, g \in g \quad \text{(capacity limits)}$$

where $c_g$ is marginal cost, $p_g$ is power output, $d$ is demand, and $\bar{p}_g$ is available capacity (for wind/solar, this is installed capacity × availability factor; for thermal, it's the nameplate capacity).

**specifically:**

1. build the pyomo model. define sets, parameters, variables, objective, and constraints.
2. solve with glpk (or highs).
3. print the dispatch schedule: how much does each generator produce?
4. print the total system cost.
5. enable dual suffixes and report the **shadow price of the demand constraint**. this is the system marginal price — what does it mean economically?

### hints

- remember to declare `model.dual = pyo.suffix(direction=pyo.suffix.import)` *before* solving if you want dual values.
- for wind and solar, the upper bound should be the *available* capacity (installed × availability factor), not the installed capacity.

### questions to answer
- which generators are dispatched and at what level?
	- cc gas turbine 1 = 1600
	- cc gas turbine 2 = 1000
	- coal 1 = 1200
	- lignite 1 = 2800
	- open cycle gas turbine = 30
	- solar = 450
	- wind = 1120
- what is the total system cost for this hour?
	- (the objective...) 267,160 EUR
- what is the shadow price of the demand constraint? which generator's marginal cost does it correspond to, and why?
	- to recap: the dual for a constraint is its shadow price; this refers to the change in the objective function by moving the constraint "out" by 1 unit
	- in this case, that means increasing the demand by 1 unit
	- the shadow price should be the cost of the marginal generator (assuming there is remaining capacity)
	- in our case, this would be the open cycle gas turbine (the only generator which is partially dispatched), whose cost is 92
	- this is indeed the output for `model.dual[model.demand_con]`
- if demand increased by 1 mw, how much would total cost increase? how do you know this without re-solving?
	- 92, see above
- what is the "merit order" you observe? does it match what you'd expect from the cost data?
	- the solver doesn't really solve them "in order", as a human would (?), but one could assemble this by simply ordering the model.generated values ascending by (marginal) cost

### verification

**expected results:**

the merit order dispatches cheapest first (fuel cost only, no carbon). with 8,200 mw demand:

1. wind: 1,120 mw (full available capacity, €0)
2. solar: 450 mw (full available capacity, €0)
3. lignite: 2,800 mw (full capacity, €18) — cheapest thermal without carbon pricing
4. coal: 1,200 mw (full capacity, €36)
5. remaining demand: 8,200 − (1,120 + 450 + 2,800 + 1,200) = **2,630 mw**
6. ccgt_1: 1,600 mw (full capacity, €63)
7. remaining: 2,630 − 1,600 = **1,030 mw**
8. ccgt_2: 1,030 mw of 1,000 mw capacity...

actually, 2,630 − 1,600 = 1,030. ccgt_2 has 1,000 mw capacity, so: ccgt_2: 1,000 mw (full capacity, €70). remaining: 30 mw. ocgt_1: 30 mw (€92, marginal unit).

**total cost:** (1,120 × 0) + (450 × 0) + (2,800 × 18) + (1,200 × 36) + (1,600 × 63) + (1,000 × 70) + (30 × 92) = 0 + 0 + 50,400 + 43,200 + 100,800 + 70,000 + 2,760 = **267,160 €**

**shadow price of demand constraint:** **92 €/mwh** (the marginal cost of ocgt_1, the marginal generator).

> **key insight:** without carbon pricing, lignite is the cheapest thermal fuel — it runs at full output. in problem 2, you'll see how adding a co₂ cost completely reshuffles this merit order, because lignite has the highest emissions intensity.

**verification script:**
```python
# after solving your model, run these checks:
assert abs(pyo.value(model.obj) - 267160) < 1, f"objective should be 267,160, got {pyo.value(model.obj)}"
assert abs(pyo.value(model.gen['ocgt_1']) - 30) < 1, f"ocgt_1 should produce 30 mw"
assert abs(model.dual[model.demand] - 92) < 0.01, f"shadow price should be 92 €/mwh"
print("✓ all checks passed!")
```

---

## problem 2: shadow prices and policy — adding an emissions cap

### concepts introduced
- adding constraints to an existing model
- interpreting shadow prices as policy signals (carbon price)
- sensitivity analysis: how the solution changes with constraint tightening
- emissions intensity data for european generation

### background

the eu emissions trading system (eu ets) caps total co₂ emissions. but in your model, you can impose an **emissions constraint** directly and read off the shadow price — this tells you what the *implicit carbon price* would need to be to achieve the same emissions reduction through a market mechanism. this is one of the most powerful applications of lp duality in energy policy analysis.

> **real-world reference:** eu ets allowance prices have ranged from €5 (2017) to €100+ (2023). the shadow price you compute in this problem has a direct analogue: it's the marginal abatement cost at a given emissions cap. see [eu ets data via ember](https://ember-climate.org/data/data-tools/carbon-price-viewer/).

### setup

use your problem 1 model as a starting point. add emissions intensity data. these values are derived from fuel carbon content and plant thermal efficiency using ipcc tier 1 emission factors:

| generator | technology | efficiency | emissions intensity (tco₂/mwh_e) | derivation |
|-----------|-----------|-----------|-------------------------------|--------|
| `lignite_1` | lignite | 35% | 1.08 | 0.378 tco₂/mwh_th ÷ 0.35 |
| `coal_1` | hard coal | 38% | 0.88 | 0.335 tco₂/mwh_th ÷ 0.38 |
| `ccgt_1` | gas ccgt | 55% | 0.37 | 0.202 tco₂/mwh_th ÷ 0.55 |
| `ccgt_2` | gas ccgt (older) | 50% | 0.40 | 0.202 tco₂/mwh_th ÷ 0.50 |
| `ocgt_1` | gas ocgt | 38% | 0.53 | 0.202 tco₂/mwh_th ÷ 0.38 |
| `wind` | wind | — | 0 | no direct emissions |
| `solar` | solar | — | 0 | no direct emissions |

> **where these numbers come from:** fuel-specific co₂ emission factors (tco₂/mwh_th): lignite 0.378, hard coal 0.335, natural gas 0.202 — from [ipcc 2006 guidelines](https://www.ipcc-nggip.iges.or.jp/public/2006gl/) and [eea emission intensity data](https://www.eea.europa.eu/data-and-maps/daviz/co2-emission-intensity-14). dividing by plant efficiency gives emissions per mwh of electricity produced.
>
> **why this matters now:** in problem 1, lignite was the cheapest thermal generator (€18/mwh). but lignite emits 1.08 tco₂/mwh — nearly 3× the rate of gas ccgt. at the current eu ets price of ~€68/tco₂ (2025 average, per [ember carbon price viewer](https://ember-climate.org/data/data-tools/carbon-price-viewer/)), lignite's true cost including carbon is 18 + (1.08 × 68) = **€91/mwh** — more expensive than both gas ccgts. this is the "fuel switch" that the ets is designed to drive.

### your task

**part a: add an emissions constraint**

add the following constraint to your problem 1 model:

$$\sum_{g \in g} e_g \cdot p_g \leq e_{max}$$

where $e_g$ is the emissions intensity (tco₂/mwh) and $e_{max}$ is the emissions cap.

set $e_{max} = 4{,}000$ tco₂ for this hour.

1. solve the model with the emissions cap.
2. report the new dispatch schedule.
3. report the new total cost.
4. report the shadow price of the emissions constraint. what does this number represent economically?

**part b: sensitivity analysis**

solve the model for a range of emissions caps: $e_{max} \in \{6000, 5000, 4000, 3000, 2000, 1500\}$ tco₂.

for each cap, record:
- total system cost
- shadow price of the emissions constraint
- shadow price of the demand constraint
- dispatch of each generator

plot (or tabulate):
1. total cost vs. emissions cap (this is the **system abatement cost curve**)
2. emissions shadow price vs. emissions cap (this is the **marginal abatement cost curve**)

**part c: interpretation**

1. at what emissions cap does the shadow price first become non-zero? what does this cap represent?
2. as the cap tightens, what happens to the dispatch order? which generators get displaced first?
3. at a very tight cap (1,500 tco₂), what is the shadow price? is the problem still feasible? if so, what does the high shadow price tell you about the cost of extreme decarbonisation with this fleet?
4. compare the emissions shadow price at $e_{max} = 4{,}000$ to the actual eu ets price (~€65–85/tco₂ in 2024). what does this tell you about whether the ets is "tight enough"?

### verification

**expected results for $e_{max} = 4{,}000$ tco₂:**

without the cap (problem 1), total emissions were: (2,800 × 1.08) + (1,200 × 0.88) + (1,600 × 0.37) + (1,000 × 0.40) + (30 × 0.53) = 3,024 + 1,056 + 592 + 400 + 15.9 = **5,087.9 tco₂**.

with a 4,000 tco₂ cap, the model needs to cut ~1,088 tco₂. the cheapest abatement option: replace lignite (1.08 tco₂/mwh, €18/mwh) with gas ccgt generation. but wait — ccgt_1 and ccgt_2 are already fully dispatched in problem 1. the ocgt has headroom (570 mw unused).

the model must shift lignite → ocgt or reduce lignite and redistribute. each mwh shifted from lignite (1.08 tco₂) to ocgt (0.53 tco₂) saves 0.55 tco₂ at a cost increase of (92 − 18) = €74/mwh → abatement cost ≈ **€134/tco₂**. but the model might also find it cheaper to shift lignite → increase ccgt_1 (if ccgt_1 was not fully dispatched — and indeed with the changed costs, the lp may dispatch differently under the emissions cap).

the key insight: the solver will find the cheapest re-dispatch to cut emissions. the shadow price of the emissions constraint gives you the **marginal abatement cost** at that cap level — effectively the carbon price that would achieve the same result via a market mechanism.

try several cap levels and observe how the shadow price rises as the cap tightens. compare to the actual eu ets price of ~€68/tco₂ — the cap level whose shadow price equals €68 is the emissions level the ets is effectively targeting.

**verification script:**
```python
# check that emissions constraint is satisfied
total_emissions = sum(emissions[g] * pyo.value(model.gen[g]) for g in model.g)
assert total_emissions <= 4000 + 0.1, f"emissions {total_emissions:.1f} exceed cap"

# check shadow price is positive (constraint is binding)
emissions_shadow = model.dual[model.emissions_cap]
assert emissions_shadow > 0, "emissions constraint should be binding"
print(f"emissions shadow price: {emissions_shadow:.1f} €/tco₂")
print(f"total emissions: {total_emissions:.1f} tco₂")
print(f"total cost: {pyo.value(model.obj):.0f} €")
print("✓ emissions constraint is binding with positive shadow price")

# bonus: verify the shadow price's economic meaning
# if you relax the cap by 1 tco₂ and re-solve, the cost should decrease
# by approximately the shadow price value
```

---

## problem 3: time moves — 24-hour dispatch with load and renewable profiles

### concepts introduced
- multi-period (time-indexed) optimisation
- hourly load profiles and renewable availability profiles
- ramp rate constraints
- total energy vs. instantaneous power
- working with time-series data in pyomo

### background

real electricity dispatch isn't a single snapshot — it's a continuous, rolling problem. demand fluctuates over the day (low at night, peaks in the morning and evening). wind and solar output change hour by hour. thermal generators can't instantly jump from 0 to full power — they have **ramp rate** limits that constrain how fast they can change output.

the day-ahead market clears all 24 hours simultaneously, optimising the full daily schedule subject to hourly demand, renewable profiles, and generator constraints.

> **real-world reference:** download actual hourly load and generation data from [entso-e transparency platform — total load](https://transparency.entsoe.eu/load-domain/r2/totalloadr2/show) and [actual generation per type](https://transparency.entsoe.eu/generation/r2/actualgenerationperproductiontype/show). compare your model's profiles to real german data for an autumn day.

### setup

use the same generator fleet from problems 1–2. now index everything over 24 hours.

**hourly demand profile (mw) — typical german autumn weekday:**

| hour | demand | hour | demand | hour | demand |
|------|--------|------|--------|------|--------|
| 0 | 5,800 | 8 | 8,000 | 16 | 8,100 |
| 1 | 5,500 | 9 | 8,200 | 17 | 8,400 |
| 2 | 5,300 | 10 | 8,300 | 18 | 8,500 |
| 3 | 5,200 | 11 | 8,200 | 19 | 8,200 |
| 4 | 5,300 | 12 | 8,000 | 20 | 7,800 |
| 5 | 5,600 | 13 | 7,800 | 21 | 7,200 |
| 6 | 6,200 | 14 | 7,900 | 22 | 6,600 |
| 7 | 7,200 | 15 | 8,000 | 23 | 6,100 |

**wind availability factor profile (fraction of installed capacity):**

| hour | wind cf | hour | wind cf | hour | wind cf |
|------|---------|------|---------|------|---------|
| 0 | 0.32 | 8 | 0.25 | 16 | 0.30 |
| 1 | 0.30 | 9 | 0.22 | 17 | 0.33 |
| 2 | 0.28 | 10 | 0.20 | 18 | 0.35 |
| 3 | 0.27 | 11 | 0.19 | 19 | 0.34 |
| 4 | 0.26 | 12 | 0.21 | 20 | 0.32 |
| 5 | 0.25 | 13 | 0.23 | 21 | 0.30 |
| 6 | 0.24 | 14 | 0.25 | 22 | 0.31 |
| 7 | 0.24 | 15 | 0.27 | 23 | 0.33 |

**solar availability factor profile:**

| hour | solar cf | hour | solar cf | hour | solar cf |
|------|----------|------|----------|------|----------|
| 0 | 0 | 8 | 0.08 | 16 | 0.05 |
| 1 | 0 | 9 | 0.18 | 17 | 0.01 |
| 2 | 0 | 10 | 0.28 | 18 | 0 |
| 3 | 0 | 11 | 0.33 | 19 | 0 |
| 4 | 0 | 12 | 0.35 | 20 | 0 |
| 5 | 0 | 13 | 0.33 | 21 | 0 |
| 6 | 0 | 14 | 0.28 | 22 | 0 |
| 7 | 0.02 | 15 | 0.18 | 23 | 0 |

**ramp rate limits (mw/hour) — thermal generators only:**

| generator | ramp up (mw/h) | ramp down (mw/h) | ramp rate (% of capacity/h) |
|-----------|---------------|-----------------|---------------------------|
| `lignite_1` | 420 | 420 | 15% |
| `coal_1` | 360 | 360 | 30% |
| `ccgt_1` | 800 | 800 | 50% |
| `ccgt_2` | 500 | 500 | 50% |
| `ocgt_1` | 600 | 600 | 100% |

> lignite ramps slowly (~10–20%/hour) due to thermal stress on large boilers. coal is moderately flexible at ~25–35%/hour. modern gas ccgts can ramp ~40–60%/hour, and ocgts are essentially instant-on peakers. these rates are representative of actual european plant capabilities. source: [diw berlin — open power system data](https://open-power-system-data.org/) and [danish energy agency technology catalogue](https://ens.dk/en/our-services/projections-and-models/technology-data).

### your task

**formulate the 24-hour dispatch lp:**

$$\min \sum_{t \in t} \sum_{g \in g} c_g \cdot p_{g,t}$$

subject to:

$$\sum_{g \in g} p_{g,t} = d_t \quad \forall \, t \in t \quad \text{(hourly demand balance)}$$

$$0 \leq p_{g,t} \leq \bar{p}_{g,t} \quad \forall \, g, t \quad \text{(hourly capacity limits)}$$

$$p_{g,t} - p_{g,t-1} \leq ru_g \quad \forall \, g \in g_{thermal}, \, t > 0 \quad \text{(ramp up)}$$

$$p_{g,t-1} - p_{g,t} \leq rd_g \quad \forall \, g \in g_{thermal}, \, t > 0 \quad \text{(ramp down)}$$

where $\bar{p}_{g,t}$ is the available capacity at hour $t$ (for renewables: installed × availability factor at $t$; for thermal: nameplate capacity).

**specifically:**

1. build and solve the 24-hour model in pyomo.
2. print a table showing each generator's output at each hour.
3. report total daily cost and total daily emissions (using problem 2's emissions data).
4. report the shadow price of the demand constraint at each hour — this gives you the **hourly marginal price**. plot it or tabulate it. this is your model's version of the day-ahead price curve.
5. at which hours is the marginal price highest? lowest? why?
6. do the ramp constraints bind at any hour? if so, what's the economic impact (shadow price of the ramp constraint)?

### questions to answer

1. how does the merit order "shift" over the day as renewable output changes?
2. during which hours does solar push down the marginal price (the "solar duck" effect)?
3. if you removed ramp rate constraints entirely, how much would total cost decrease? is the difference large or small?
4. what is the total daily co₂ emissions? how does it compare to 24 × (problem 1 emissions)?

### verification

**key checks:**

- total daily energy served = sum of hourly demand = 170,500 mwh (sum the demand column)
- at each hour, generation must exactly equal demand (check `sum(pyo.value(model.gen[g,t]) for g in model.g)` for each `t`)
- the hourly marginal price profile should be lowest around midday (solar peak) and highest during the evening peak (hours 17–19)
- lignite should run relatively flat (limited by its slow ramp rate of 15%/hour)
- ocgt should only run during a few peak hours, if at all

```python
# verification script
total_demand = sum(demand[t] for t in model.t)
total_gen = sum(pyo.value(model.gen[g,t]) for g in model.g for t in model.t)
assert abs(total_gen - total_demand) < 1, f"energy balance: gen={total_gen:.0f}, demand={total_demand:.0f}"

# check ramp constraints
for g in thermal_gens:
    for t in range(1, 24):
        ramp_up = pyo.value(model.gen[g,t]) - pyo.value(model.gen[g,t-1])
        assert ramp_up <= ramp_limits[g] + 0.1, f"ramp up violation: {g} at hour {t}"
        ramp_down = pyo.value(model.gen[g,t-1]) - pyo.value(model.gen[g,t])
        assert ramp_down <= ramp_limits[g] + 0.1, f"ramp down violation: {g} at hour {t}"

print(f"total daily cost: {pyo.value(model.obj):,.0f} €")
print(f"total daily energy: {total_demand:,.0f} mwh")
print("✓ energy balance and ramp constraints verified")
```

---

## problem 4: borders open — cross-border dispatch with interconnectors

### concepts introduced
- multi-zone / network modelling
- net transfer capacity (ntc) constraints
- price convergence and market coupling
- flow variables and energy balance by zone
- how interconnectors create cross-border welfare gains

### background

european electricity markets are **coupled**: the day-ahead market clears simultaneously across all bidding zones, respecting the transmission capacity between them. when an interconnector between two zones isn't congested, prices converge. when it hits its limit, prices diverge — creating **congestion rent** that flows to tsos.

this is the foundation of the eu internal energy market and the whole purpose of entso-e's market coupling. your model is about to become a proper multi-zone dispatch model.

> **real-world reference:** cross-border capacities are published by entso-e as [net transfer capacities](https://transparency.entsoe.eu/transmission-domain/ntcday/show) and by [jao (joint allocation office)](https://www.jao.eu/). the cwe flow-based market coupling region (de, fr, nl, be, at) is the most integrated in europe.

### setup

expand your model to **five bidding zones**: de (germany), fr (france), nl (netherlands), be (belgium), pl (poland).

**generation fleet by zone (teaching-scale — proportionally representative of real 2024 installed capacities):**

real installed capacities are scaled down by roughly 10–20× to keep the problem tractable while preserving the structural differences between countries. marginal costs are fuel + variable o&m only (no carbon price), consistent with problem 1.

| zone | generator | technology | capacity (mw) | marginal cost (€/mwh) | real-world basis |
|------|-----------|-----------|---------------|----------------------|------------------|
| de | de_lignite | lignite | 2,800 | 18 | ~18 gw real (2024), phasing out by 2038 |
| de | de_coal | hard coal | 1,200 | 36 | ~8 gw real, declining |
| de | de_ccgt | gas ccgt | 2,600 | 63 | ~15 gw real gas capacity |
| de | de_wind | wind | 4,000 | 0 | ~73 gw real (64 on + 9 offshore) |
| de | de_solar | solar | 3,000 | 0 | ~99 gw real (fraunhofer ise 2024) |
| fr | fr_nuclear | nuclear | 5,000 | 8 | 61.4 gw real (rte 2024), dominant fleet |
| fr | fr_hydro | hydro (run-of-river) | 1,500 | 5 | ~25 gw real hydro |
| fr | fr_ccgt | gas ccgt | 1,200 | 65 | small gas fleet, ~7 gw |
| fr | fr_wind | wind | 1,500 | 0 | ~23 gw real onshore |
| fr | fr_solar | solar | 1,000 | 0 | ~24 gw real |
| nl | nl_ccgt_1 | gas ccgt (efficient) | 1,800 | 60 | nl is 37% gas-fired (2024) |
| nl | nl_ccgt_2 | gas ccgt (older) | 1,200 | 68 | older fleet, lower efficiency |
| nl | nl_wind | wind (offshore) | 2,000 | 0 | 4.7 gw real offshore (2024) |
| be | be_nuclear | nuclear | 2,000 | 9 | doel 4 + tihange 3 extended to 2035 |
| be | be_ccgt | gas ccgt | 1,500 | 63 | new crm-contracted gas plants |
| be | be_wind | wind (offshore) | 800 | 0 | 2.3 gw real offshore |
| pl | pl_coal_1 | hard coal (newer) | 3,000 | 34 | coal is 51% of pl generation (2024) |
| pl | pl_coal_2 | hard coal (older) | 2,000 | 42 | older, less efficient units |
| pl | pl_ccgt | gas ccgt | 800 | 67 | growing gas fleet, ~8 gw real |
| pl | pl_wind | wind | 1,200 | 0 | ~10 gw real onshore |

> **country profiles (2024 data):**
> - **germany:** no nuclear since april 2023. largest renewable fleet in europe (99 gw solar, 73 gw wind). still reliant on lignite and gas for dispatchable power. source: [fraunhofer ise public electricity generation 2024](https://www.ise.fraunhofer.de/en/press-media/press-releases/2025/public-electricity-generation-2024.html).
> - **france:** nuclear-dominated (61.4 gw, ~65% of generation). cheap baseload exporter. source: [rte annual review 2024](https://analysesetdonnees.rte-france.com/en/annual-review-2024/keyfindings).
> - **netherlands:** gas-heavy (37% of generation), rapidly growing offshore wind (4.7 gw). source: [iea netherlands energy policy review 2024](https://www.iea.org/countries/the-netherlands).
> - **belgium:** extended two nuclear units to 2035, new gas capacity via capacity remuneration mechanism. source: [elia adequacy reports](https://www.elia.be/).
> - **poland:** most coal-dependent eu member (51% of generation). slow transition, growing wind. source: [ember poland data](https://ember-energy.org/countries-and-regions/poland/).
>
> these structural differences are what make cross-border trade valuable — french nuclear exports displace german lignite and polish coal.

**demand (mw, single hour — autumn afternoon):**

| zone | demand (mw) |
|------|-------------|
| de | 8,200 |
| fr | 6,500 |
| nl | 2,800 |
| be | 1,800 |
| pl | 3,500 |

**renewable availability factors (same hour):**

| zone | wind cf | solar cf |
|------|---------|----------|
| de | 0.28 | 0.15 |
| fr | 0.30 | 0.12 |
| nl | 0.45 | 0.10 |
| be | 0.40 | 0.10 |
| pl | 0.22 | 0.13 |

**interconnector ntc values (mw, one direction shown — assume same in both directions):**

| from | to | ntc (mw) | real-world basis |
|------|----|----------|-----------------|
| de | fr | 2,000 | cwe fbmc typically allows 2–4 gw; simplified to ntc |
| de | nl | 2,500 | tennet cross-border; ~3–5 gw typical available capacity |
| de | be | 1,000 | alegro hvdc (1 gw) commissioned 2020 |
| de | pl | 1,500 | several ac interconnectors; ~1–3 gw capacity |
| fr | be | 2,000 | ~3–4 gw real; reduced for teaching scale |
| nl | be | 1,400 | ~2 gw real capacity |

> **important note on cwe market coupling:** since 2015, the cwe region uses **flow-based market coupling (fbmc)** rather than simple ntc constraints. fbmc uses power transfer distribution factors (ptdfs) and critical network elements to define available capacity more accurately. our ntc-based model is a simplification. for the real methodology, see [entso-e flow-based documentation](https://www.entsoe.eu/network_codes/cacm/implementation/fbmc/) and [jao](https://www.jao.eu/). the ntc values here are inspired by typical available commercial capacities published on the [entso-e transparency platform — ntc day](https://transparency.entsoe.eu/transmission-domain/ntcday/show).

### your task

**formulate the multi-zone dispatch lp:**

decision variables: $p_{g,z}$ (generation), $f_{z,z'}$ (flow from zone $z$ to zone $z'$)

$$\min \sum_{z \in z} \sum_{g \in g_z} c_g \cdot p_g$$

subject to:

$$\sum_{g \in g_z} p_g + \sum_{z' : (z',z) \in l} f_{z',z} - \sum_{z' : (z,z') \in l} f_{z,z'} = d_z \quad \forall \, z \quad \text{(zonal balance)}$$

$$0 \leq p_g \leq \bar{p}_g \quad \forall \, g \quad \text{(capacity limits)}$$

$$-ntc_{z,z'} \leq f_{z,z'} \leq ntc_{z,z'} \quad \forall \, (z,z') \in l \quad \text{(transmission limits)}$$

note: flow can be negative (meaning flow in the opposite direction). define flow variables as free (not non-negative).

**specifically:**

1. build and solve the multi-zone model.
2. report generation dispatch for each zone.
3. report all cross-border flows (direction and magnitude).
4. report the zonal marginal price (shadow price of each zone's balance constraint).
5. where prices are equal between zones, what does that tell you about the interconnector?
6. where prices differ, compute the **congestion rent** on the interconnector: $(price_{import\_zone} - price_{export\_zone}) \times flow$.

**part b: what if there were no interconnectors?**

solve each zone in isolation (remove all flow variables or set ntc to 0). compare:
- zonal prices with and without trade
- total system cost with and without trade
- the difference is the **welfare gain from market coupling**

### questions to answer

1. which direction does power flow on each interconnector? is france exporting (as it typically does with its nuclear fleet)?
2. how much does cross-border trade reduce total system cost?
3. poland's coal-heavy fleet faces high costs — does trade help or hurt poland?
4. if the de→pl interconnector capacity doubled, what would happen to prices and flows? (solve this variant.)

### verification

**key checks:**

- in the uncoupled case, france should have the lowest price (cheap nuclear) and poland the highest (expensive coal)
- with coupling, flows should go from low-price to high-price zones
- france should be a net exporter; poland likely a net importer
- total coupled cost < sum of uncoupled costs (trade creates surplus)
- at each zone, total generation + net imports = demand (energy balance)

```python
# verify energy balance per zone
for z in model.z:
    gen = sum(pyo.value(model.gen[g]) for g in generators_in_zone[z])
    imports = sum(pyo.value(model.flow[z2, z]) for z2 in connected_to[z])
    exports = sum(pyo.value(model.flow[z, z2]) for z2 in connected_from[z])
    balance = gen + imports - exports
    assert abs(balance - demand[z]) < 1, f"zone {z}: balance {balance:.0f} ≠ demand {demand[z]}"

# verify flow limits
for (z1, z2) in model.l:
    flow = pyo.value(model.flow[z1, z2])
    assert abs(flow) <= ntc[z1, z2] + 0.1, f"flow {z1}→{z2} = {flow:.0f} exceeds ntc"

print("✓ all zonal balances and flow limits verified")
```

---

## problem 5: on or off — unit commitment with binary decisions

### concepts introduced
- mixed-integer linear programming (milp)
- binary variables for on/off decisions
- minimum stable generation levels
- startup and shutdown costs
- big-m formulation for linking binary and continuous variables
- minimum up-time and down-time constraints
- mip gap and solver performance

### background

in reality, power plants can't just produce any amount between 0 and their capacity. when a plant is "on," it has a **minimum stable load** — the lowest output it can sustain without shutting down. starting up a cold plant costs money (fuel to heat the boiler, material stress, etc.) and takes time. these characteristics make the **unit commitment** problem a milp: you need binary variables to decide which plants are "on" at each hour.

unit commitment is what tsos solve every day in the operational planning phase. it's one of the most important practical applications of milp in the energy sector.

> **real-world reference:** tsos publish [unavailability schedules](https://transparency.entsoe.eu/outage-domain/r2/unavailabilityofproductionandgenerationunits/show) and [actual generation data](https://transparency.entsoe.eu/generation/r2/actualgenerationperproductiontype/show) on the entso-e transparency platform, which implicitly reflects unit commitment decisions.

### setup

return to the single-zone (de) system from problems 1–3. this is a 24-hour unit commitment problem using the same demand and renewable profiles from problem 3.

**extended generator data with uc parameters:**

| generator | capacity (mw) | min stable (mw) | marginal cost (€/mwh) | startup cost (€) | min up (hrs) | min down (hrs) |
|-----------|--------------|-----------------|----------------------|------------------|-------------|---------------|
| `lignite_1` | 2,800 | 1,120 | 18 | 28,000 | 8 | 6 |
| `coal_1` | 1,200 | 360 | 36 | 12,000 | 6 | 4 |
| `ccgt_1` | 1,600 | 480 | 63 | 8,000 | 3 | 2 |
| `ccgt_2` | 1,000 | 300 | 70 | 6,000 | 3 | 2 |
| `ocgt_1` | 600 | 60 | 92 | 2,000 | 1 | 1 |

wind and solar have no uc constraints (they can freely curtail from 0 to their available output).

> **where these numbers come from:** minimum stable loads are typically 40–75% for coal/lignite, 70% for nuclear, 30% for ccgt, 10% for ocgt. startup costs depend on whether the start is hot (recent shutdown), warm, or cold — we use approximate cold-start values. these ranges come from [diw berlin power plant database](https://www.diw.de/de/diw_01.c.528169.de/forschung_beratung/nachhaltigkeit/umwelt/verkehr/energie/modellierung/strommarkt.html) and standard references.

### your task

**formulate the 24-hour unit commitment milp:**

new variables:
- $u_{g,t} \in \{0, 1\}$ — commitment status (1 = on, 0 = off)
- $v_{g,t} \in \{0, 1\}$ — startup indicator (1 = started up at hour $t$)
- $w_{g,t} \in \{0, 1\}$ — shutdown indicator

$$\min \sum_{t} \sum_{g} \left( c_g \cdot p_{g,t} + sc_g \cdot v_{g,t} \right)$$

subject to:

$$\sum_{g} p_{g,t} = d_t \quad \forall \, t \quad \text{(demand balance)}$$

$$u_{g,t} \cdot \underline{p}_g \leq p_{g,t} \leq u_{g,t} \cdot \bar{p}_g \quad \forall \, g \in g_{thermal}, \, t \quad \text{(output linked to commitment)}$$

$$v_{g,t} - w_{g,t} = u_{g,t} - u_{g,t-1} \quad \forall \, g, \, t > 0 \quad \text{(startup/shutdown logic)}$$

$$v_{g,t} + w_{g,t} \leq 1 \quad \forall \, g, \, t \quad \text{(can't start and stop same hour)}$$

$$\sum_{\tau=t-ut_g+1}^{t} v_{g,\tau} \leq u_{g,t} \quad \forall \, g, \, t \geq ut_g \quad \text{(minimum up-time)}$$

$$\sum_{\tau=t-dt_g+1}^{t} w_{g,\tau} \leq 1 - u_{g,t} \quad \forall \, g, \, t \geq dt_g \quad \text{(minimum down-time)}$$

plus ramp constraints from problem 3 (now only when the unit is on).

**initial conditions:** assume at $t=0$, lignite and coal are on, everything else is off.

**specifically:**

1. build and solve the uc model. use cbc or highs as the solver.
2. print the commitment schedule (which units are on/off at each hour).
3. print the dispatch schedule.
4. how many startups occur and what are the total startup costs?
5. compare total cost to problem 3 (lp dispatch without uc constraints). how much more expensive is the uc solution? why?
6. observe the mip gap during solving. set a gap tolerance of 0.5% (`solver.options['ratiogap'] = 0.005` for cbc). how quickly does the solver find a near-optimal solution?

### questions to answer

1. does lignite stay on the whole time? why? (consider startup cost vs. savings from shutting down.)
2. which generators cycle on and off? is this realistic?
3. during low-demand nighttime hours, what happens? is there a "must-run" problem where committed generation exceeds demand?
4. if you doubled the startup cost for coal, how would the commitment schedule change?

### verification

**key checks:**

- lignite should stay on all 24 hours (high startup cost, long min up-time, already on)
- coal should stay on most or all hours (moderate startup cost, already on)
- ocgt should start only for a few peak hours (low startup cost, very flexible)
- total uc cost > total lp cost from problem 3 (uc is always at least as expensive)
- wherever a unit is off, its output is exactly 0
- wherever a unit is on, its output is ≥ minimum stable load

```python
# verify linking constraints
for g in thermal_gens:
    for t in model.t:
        u = pyo.value(model.u[g,t])
        p = pyo.value(model.gen[g,t])
        if u < 0.5:  # off
            assert abs(p) < 0.1, f"{g} is off at hour {t} but producing {p:.0f} mw"
        else:  # on
            assert p >= min_stable[g] - 0.1, f"{g} is on at hour {t} but output {p:.0f} < min stable {min_stable[g]}"

# count startups
total_startups = sum(round(pyo.value(model.v[g,t])) for g in thermal_gens for t in model.t)
total_startup_cost = sum(startup_cost[g] * round(pyo.value(model.v[g,t])) for g in thermal_gens for t in model.t)
print(f"total startups: {total_startups}")
print(f"total startup cost: {total_startup_cost:,.0f} €")
print(f"total cost (uc): {pyo.value(model.obj):,.0f} €")
print("✓ uc constraints verified")
```

---

## problem 6: building the future — capacity expansion planning

### concepts introduced
- investment decisions (binary or continuous)
- annualised capital costs (capex → annual payments)
- planning over a long time horizon with representative periods
- greenfield vs. brownfield modelling
- the interplay between investment and operational costs

### background

capacity expansion planning (cep) answers the question: **what should we build?** given projected demand, fuel prices, technology costs, and policy targets, which generation technologies should be invested in, where, and how much? this is a core modelling exercise for governments, utilities, and tsos planning the energy transition.

the trick is that you can't model every hour of a 20-year horizon. instead, you pick **representative periods** — a few days or weeks that capture the range of conditions (high/low demand, high/low wind, etc.) — and weight them to approximate a full year.

> **real-world reference:** entso-e's [ten-year network development plan (tyndp)](https://tyndp.entsoe.eu/) uses capacity expansion and dispatch models to plan european infrastructure. technology cost assumptions come from the [danish energy agency technology catalogues](https://ens.dk/en/our-services/projections-and-models/technology-data) — the standard reference for european energy modelling.

### setup

you are planning the **2035 generation fleet for germany**. the existing fleet is partially decommissioned:

**existing fleet (already built, no further capex):**

| technology | existing capacity (mw) | marginal cost (€/mwh) | notes |
|-----------|----------------------|----------------------|-------|
| lignite | 1,500 | 90 | fuel €18 + co₂ (1.08 × €68) = €91; phasing out by 2038 under kohleausstieg |
| hard coal | 500 | 96 | fuel €36 + co₂ (0.88 × €68) = €96; most closing by 2030 |
| ccgt (existing) | 1,500 | 88 | fuel €63 + co₂ (0.37 × €68) = €88; some fleet retained for flexibility |

> **note:** for this capacity expansion problem, marginal costs include the co₂ price (assumed €68/tco₂, the 2025 eu ets average) because investment decisions must reflect full operating costs including carbon. this means lignite and coal are now very expensive to run — which is the whole economic rationale for the energy transition.

**new-build candidates:**

| technology | max new build (mw) | capex (€/kw) | fixed o&m (€/kw/yr) | marginal cost (€/mwh) | lifetime (yrs) | wacc |
|-----------|-------------------|-------------|--------------------|-----------------------|---------------|------|
| solar pv | 10,000 | 550 | 12 | 0 | 25 | 6% |
| onshore wind | 8,000 | 1,100 | 25 | 0 | 25 | 6% |
| offshore wind | 5,000 | 2,800 | 55 | 0 | 25 | 8% |
| gas ccgt (new) | 5,000 | 700 | 18 | 58 | 30 | 6% |
| gas ocgt (new) | 3,000 | 450 | 10 | 88 | 30 | 6% |
| battery (4h) | 3,000 | 165 (€/kwh) | 4 (€/kwh/yr) | 0 | 15 | 6% |

> **where these costs come from (2024–2025 vintage):**
> - **solar pv:** irena reports global weighted average of $599/kw (2024); european costs are ~20–30% higher due to labour and permitting → ~€550/kw. source: [irena renewable power generation costs 2024](https://www.irena.org/publications/2025/jun/renewable-power-generation-costs-in-2024).
> - **onshore wind:** global 5-year average ~$861/kw; european installed costs ~€1,000–1,200/kw. source: irena 2024.
> - **offshore wind:** costs have stabilised/risen due to supply chain pressures; european projects ~€2,500–3,000/kw. source: [danish energy agency technology catalogue](https://ens.dk/en/our-services/projections-and-models/technology-data).
> - **gas ccgt/ocgt:** relatively stable at €650–750/kw (ccgt) and €400–500/kw (ocgt). source: danish ea.
> - **battery (4h li-ion):** dramatic cost declines — turnkey system costs ~€165/kwh in europe (2025), down from €300+/kwh in 2022. source: [bnef global energy storage outlook 2025](https://about.bnef.com/) and [energy-storage.news](https://www.energy-storage.news/).
> - **wacc:** 6% for established technologies, 8% for offshore wind reflecting higher project risk. based on typical european project finance rates (see [aures ii auction database](http://aures2project.eu/)).
>
> new ccgt marginal cost is lower (€58/mwh) than the older units in problems 1–3 because new builds achieve ~58–60% thermal efficiency vs. 50–55% for existing fleet.

**annualised cost calculation:** convert capex to annual payments using the capital recovery factor:

$$crf = \frac{r(1+r)^n}{(1+r)^n - 1}$$

where $r$ is wacc and $n$ is lifetime. then annual capex per mw = capex × crf × 1000.

**representative periods:** use three representative days (72 hours total), each weighted to approximate a year:

| day type | weight (days/yr) | description |
|----------|-----------------|-------------|
| winter peak | 60 | high demand, low solar, moderate wind |
| summer shoulder | 200 | moderate demand, high solar, moderate wind |
| autumn low | 105 | low demand, low solar, low wind |

(you'll need to define hourly demand and renewable profiles for each day type. use scaled versions of problem 3's profiles, adjusting the levels.)

**policy constraint:** renewable generation must be ≥ 65% of annual energy. (germany's actual 2030 target is 80%.)

### your task

**formulate the capacity expansion milp:**

decision variables:
- $cap_g^{new}$ — new capacity to build (mw, continuous)
- $p_{g,d,t}$ — generation in day type $d$, hour $t$
- for battery: $charge_{d,t}$, $discharge_{d,t}$, $soc_{d,t}$ (state of charge)

$$\min \sum_{g \in g_{new}} anncapex_g \cdot cap_g^{new} + \sum_{g \in g_{new}} fom_g \cdot cap_g^{new} + \sum_{d} w_d \sum_{t} \sum_{g} c_g \cdot p_{g,d,t}$$

subject to: demand balance, capacity limits (existing + new), renewable target, and if you include battery, the storage constraints from problem 7 preview.

**note:** you can simplify by making capacity a continuous variable (no binary) if you want a pure lp. for a more realistic version, make investment binary (build or don't build in increments of, say, 500 mw blocks).

**specifically:**

1. define the representative periods with hourly data.
2. compute the annualised cost for each technology.
3. build and solve the model.
4. what portfolio gets built? how much of each technology?
5. what is the total annual system cost (investment + operations)?
6. what is the shadow price of the renewable target constraint? this is the implicit **cost of the renewable mandate** — what subsidy or premium is needed per mwh of renewable generation.
7. what happens to the portfolio if you tighten the renewable target to 80%?

### verification

**key checks and expected patterns:**

- solar and onshore wind should dominate new-build (cheapest lcoe in europe)
- some new ccgt or ocgt should be built for reliability (dispatchable capacity when renewables are low)
- battery may or may not be economic depending on the price spread between peak and off-peak
- total cost should be in a realistic range for a ~15 gw system
- the renewable target shadow price should be positive if the constraint is binding

```python
# compute annualised costs and verify
import numpy as np
def crf(r, n):
    return r * (1 + r)**n / ((1 + r)**n - 1)

# example: solar pv
solar_crf = crf(0.06, 25)  # ≈ 0.0782
solar_annual_capex = 550 * solar_crf * 1000  # €/mw/yr ≈ 43,020
print(f"solar annual capex: {solar_annual_capex:,.0f} €/mw/yr")

# verify renewable share
total_renewable = sum(
    weight[d] * pyo.value(model.gen[g,d,t])
    for g in renewable_gens for d in model.d for t in model.t
)
total_gen = sum(
    weight[d] * pyo.value(model.gen[g,d,t])
    for g in model.g for d in model.d for t in model.t
)
ren_share = total_renewable / total_gen
print(f"renewable share: {ren_share:.1%}")
assert ren_share >= 0.65 - 0.001, f"renewable target not met: {ren_share:.1%}"

print("✓ capacity expansion model verified")
```

---

## problem 7: storing the sun — battery and pumped hydro storage

### concepts introduced
- storage as a time-coupling constraint (state of charge links hours)
- charge/discharge efficiency (round-trip efficiency)
- energy vs. power capacity
- storage as both "generation" and "load"
- cycling constraints and degradation (optional extension)

### background

energy storage is becoming critical to the european electricity system as renewable penetration grows. storage earns money through **arbitrage** — charging when prices are low (high renewable output) and discharging when prices are high (evening peak). the value of storage is directly linked to the price spread in the market.

germany has ~10 gw of pumped hydro storage and rapidly growing battery deployment. understanding how to model storage is essential for any energy systems analyst.

> **real-world reference:** entso-e publishes [pumped hydro generation and consumption data](https://transparency.entsoe.eu/generation/r2/actualgenerationperproductiontype/show). for battery storage deployment, see [european battery alliance statistics](https://www.eba250.com/).

### setup

return to your problem 3 (24-hour dispatch, single zone de). add two storage assets:

| storage | power capacity (mw) | energy capacity (mwh) | charge eff. | discharge eff. | round-trip eff. | initial soc |
|---------|--------------------|-----------------------|-------------|----------------|----------------|-------------|
| pumped hydro | 500 | 4,000 | 0.90 | 0.90 | 0.81 | 2,000 mwh |
| li-ion battery | 200 | 800 | 0.95 | 0.95 | 0.90 | 400 mwh |

> **real-world context:** germany has ~6.3 gw / ~40 gwh of pumped hydro storage (e.g., goldisthal at 1,060 mw, markersbach at 1,050 mw). the country also deployed 12.1 gw / 17.7 gwh of battery storage by end of 2024 (mostly behind-the-meter residential, but grid-scale is growing rapidly). our teaching-scale values (~500 mw pumped hydro, 200 mw battery) are proportional to the reduced fleet size. sources: [clean energy wire — german pumped hydro](https://www.cleanenergywire.org/news/german-government-says-pumped-hydro-power-capacity-grow-14-gw-2030), [fraunhofer ise — battery storage statistics](https://www.ise.fraunhofer.de/).

### your task

**extend the problem 3 model with storage:**

new variables for each storage unit $s$:
- $ch_{s,t} \geq 0$ — charging power (mw)
- $dis_{s,t} \geq 0$ — discharging power (mw)
- $soc_{s,t} \geq 0$ — state of charge (mwh)

new constraints:

$$soc_{s,t} = soc_{s,t-1} + \eta_s^{ch} \cdot ch_{s,t} - \frac{dis_{s,t}}{\eta_s^{dis}} \quad \forall \, s, t \quad \text{(state of charge evolution)}$$

wait — convention matters here. the standard is:

$$soc_{s,t} = soc_{s,t-1} + \eta_s^{ch} \cdot ch_{s,t} - \frac{dis_{s,t}}{\eta_s^{dis}}$$

$$0 \leq ch_{s,t} \leq \bar{p}_s^{ch} \quad \text{(charge power limit)}$$

$$0 \leq dis_{s,t} \leq \bar{p}_s^{dis} \quad \text{(discharge power limit)}$$

$$0 \leq soc_{s,t} \leq \bar{e}_s \quad \text{(energy capacity limit)}$$

$$soc_{s,23} = soc_{s,0} \quad \text{(cyclical — end where you started)}$$

modify the demand balance:

$$\sum_{g} p_{g,t} + \sum_{s} dis_{s,t} - \sum_{s} ch_{s,t} = d_t \quad \forall \, t$$

**specifically:**

1. build and solve the storage-augmented model.
2. plot (or tabulate) the charge/discharge schedule and soc profile for each storage unit over 24 hours.
3. when does each storage unit charge? when does it discharge? relate this to the hourly marginal prices from problem 3.
4. how much does storage reduce total system cost compared to problem 3?
5. what is the **arbitrage revenue** for each storage unit? (sum of discharge × price − charge × price, using the hourly marginal prices from the solution.)
6. what is the value of an additional mwh of battery storage capacity? (shadow price of the energy capacity constraint, if binding.)

### questions to answer

1. does the battery "cycle" more than once in a day? does the pumped hydro?
2. at what price spread (€/mwh) does it become worth charging and discharging, given the round-trip efficiency losses?
3. how does storage affect the hourly price profile? does it flatten it?
4. if you doubled battery capacity, would the cost savings double? why or why not? (diminishing returns.)

### verification

**key checks:**

- soc at hour 23 = soc at hour 0 (cyclical constraint)
- soc never goes below 0 or above energy capacity
- storage should charge during low-price hours (nighttime, solar midday) and discharge during high-price hours (evening peak)
- total energy balance: sum of all generation + sum of all discharge − sum of all charge = sum of demand
- round-trip losses mean total discharge < total charge (in mwh terms)

```python
# verify soc evolution
for s in model.s:
    for t in range(1, 24):
        expected_soc = (pyo.value(model.soc[s, t-1])
                       + eff_ch[s] * pyo.value(model.ch[s, t])
                       - pyo.value(model.dis[s, t]) / eff_dis[s])
        actual_soc = pyo.value(model.soc[s, t])
        assert abs(expected_soc - actual_soc) < 0.1, f"soc mismatch for {s} at hour {t}"

# verify cyclical
for s in model.s:
    assert abs(pyo.value(model.soc[s, 23]) - initial_soc[s]) < 0.1, f"soc not cyclical for {s}"

# verify system energy balance
total_gen = sum(pyo.value(model.gen[g,t]) for g in model.g for t in model.t)
total_dis = sum(pyo.value(model.dis[s,t]) for s in model.s for t in model.t)
total_ch = sum(pyo.value(model.ch[s,t]) for s in model.s for t in model.t)
total_dem = sum(demand[t] for t in model.t)
assert abs(total_gen + total_dis - total_ch - total_dem) < 1, "system energy balance violated"

print("✓ storage model verified")
```

---

## problem 8: competing goals — cost vs. emissions pareto frontier

### concepts introduced
- multi-objective optimisation
- epsilon-constraint method
- pareto frontier / efficient frontier
- trade-off analysis for policy decisions
- visualising the cost of decarbonisation

### background

policymakers face a fundamental trade-off: lower emissions cost more money (at least with current technology). the question isn't just "what's the cheapest system?" or "what's the cleanest system?" — it's "what's the shape of the trade-off?" a **pareto frontier** maps this out: it shows the minimum cost achievable for each possible emissions level.

this is exactly the analysis that informs debates about eu ets cap levels, national climate targets, and the pace of the energy transition.

### setup

use your problem 3 model (24-hour dispatch, single zone de, without storage for simplicity — or with storage if you want to see how it affects the frontier).

you'll solve the model many times, each with a different emissions cap, and trace out the frontier.

### your task

**step 1: find the extremes**

solve two problems:
- **cost-only:** minimise cost with no emissions constraint. record total cost ($c_{min}$) and total emissions ($e_{max}$).
- **emissions-only:** minimise total emissions (change the objective). record total emissions ($e_{min}$) and total cost ($c_{max}$).

**step 2: trace the pareto frontier using the epsilon-constraint method**

for 20 evenly spaced emissions caps between $e_{min}$ and $e_{max}$:

$$\min \sum_{t} \sum_{g} c_g \cdot p_{g,t}$$

subject to all dispatch constraints plus:

$$\sum_{t} \sum_{g} e_g \cdot p_{g,t} \leq e_{cap}$$

record the total cost and total emissions for each solution.

**step 3: compute the marginal abatement cost curve**

for each step along the frontier, compute:

$$mac = \frac{\delta cost}{\delta emissions} = \frac{c_{k} - c_{k-1}}{e_{k-1} - e_{k}}$$

this is the cost (in €/tco₂) of reducing one additional tonne of co₂ at that point on the frontier.

**specifically:**

1. produce a table with columns: emissions cap, total cost, shadow price of emissions constraint.
2. plot (or describe) the pareto frontier (cost vs. emissions).
3. plot (or describe) the mac curve (marginal abatement cost vs. total emissions).
4. at what point does the mac curve "take off" (become very steep)? what does this inflection point represent physically?

### questions to answer

1. is the pareto frontier convex? (it should be, for an lp.) why does this matter for policy?
2. the shadow price at each emissions cap gives the mac directly. verify that it matches your computed $\delta cost / \delta emissions$.
3. at the current eu ets price (~€65–85/tco₂), where would the system sit on the frontier? is the ets price sufficient to drive maximum decarbonisation of this fleet?
4. if you add storage (problem 7), how does the pareto frontier shift? does storage make decarbonisation cheaper?

### verification

**key checks:**

- the pareto frontier should be monotonically decreasing (lower emissions → higher cost)
- the mac curve should be monotonically increasing (each additional tonne of reduction is more expensive)
- at $e_{max}$ (no cap), the shadow price should be 0
- at very tight caps near $e_{min}$, the mac should be very high
- the shadow price from the dual should match the numerically computed mac

```python
# verify pareto frontier properties
for k in range(1, len(results)):
    assert results[k]['cost'] >= results[k-1]['cost'], "cost should increase as emissions decrease"
    assert results[k]['emissions'] <= results[k-1]['emissions'], "emissions should decrease"

# verify shadow price ≈ numerical mac
for k in range(1, len(results)):
    numerical_mac = (results[k]['cost'] - results[k-1]['cost']) / (results[k-1]['emissions'] - results[k]['emissions'])
    shadow_mac = results[k]['shadow_price']
    assert abs(numerical_mac - shadow_mac) / shadow_mac < 0.05, f"mac mismatch at step {k}"

print("✓ pareto frontier verified")
```

---

## problem 9: uncertainty — stochastic dispatch with wind scenarios

### concepts introduced
- two-stage stochastic programming
- scenario-based uncertainty representation
- first-stage (here-and-now) vs. second-stage (wait-and-see) decisions
- expected value vs. stochastic solution (value of stochastic solution — vss)
- expected value of perfect information (evpi)

### background

everything so far has assumed perfect foresight — you know exactly what demand and wind output will be. in reality, wind forecasts have significant uncertainty, especially beyond a few hours ahead. a **stochastic** model accounts for this by considering multiple possible scenarios and optimising for the best decision *across all of them*.

this is increasingly important in european markets as wind penetration grows. balancing markets, reserve procurement, and investment planning all deal with uncertainty.

> **real-world reference:** entso-e publishes [wind and solar forecast data](https://transparency.entsoe.eu/generation/r2/dayaheadgenerationforecastwindandsolar/show) alongside actual generation. comparing forecasts to actuals gives you real-world uncertainty data.

### setup

use the problem 5 unit commitment model (24-hour, single zone de) but now introduce **wind uncertainty**.

**three wind scenarios** (each represents a possible realisation of wind output over 24 hours):

| hour | low wind (prob 0.25) | base wind (prob 0.50) | high wind (prob 0.25) |
|------|---------------------|----------------------|----------------------|
| 0 | 0.18 | 0.32 | 0.48 |
| 1 | 0.17 | 0.30 | 0.45 |
| 2 | 0.16 | 0.28 | 0.44 |
| 3 | 0.15 | 0.27 | 0.43 |
| 4 | 0.14 | 0.26 | 0.42 |
| 5 | 0.14 | 0.25 | 0.40 |
| 6 | 0.13 | 0.24 | 0.38 |
| 7 | 0.13 | 0.24 | 0.38 |
| 8 | 0.14 | 0.25 | 0.39 |
| 9 | 0.12 | 0.22 | 0.36 |
| 10 | 0.11 | 0.20 | 0.34 |
| 11 | 0.10 | 0.19 | 0.33 |
| 12 | 0.12 | 0.21 | 0.35 |
| 13 | 0.13 | 0.23 | 0.37 |
| 14 | 0.14 | 0.25 | 0.39 |
| 15 | 0.15 | 0.27 | 0.41 |
| 16 | 0.17 | 0.30 | 0.44 |
| 17 | 0.19 | 0.33 | 0.48 |
| 18 | 0.20 | 0.35 | 0.50 |
| 19 | 0.19 | 0.34 | 0.49 |
| 20 | 0.18 | 0.32 | 0.46 |
| 21 | 0.17 | 0.30 | 0.44 |
| 22 | 0.18 | 0.31 | 0.45 |
| 23 | 0.19 | 0.33 | 0.47 |

solar availability is the same across all scenarios (solar is more predictable day-ahead). demand is the same across scenarios.

### your task

**formulate the two-stage stochastic uc:**

**first stage (decided before uncertainty resolves):** unit commitment decisions $u_{g,t}$, $v_{g,t}$, $w_{g,t}$ — these are the same across all scenarios. you must commit generators before you know the wind.

**second stage (decided after uncertainty resolves):** dispatch $p_{g,t,s}$ — these can differ by scenario. each scenario gets its own dispatch, but all share the same commitment.

$$\min \sum_{s} \pi_s \left[ \sum_{t} \sum_{g} c_g \cdot p_{g,t,s} \right] + \sum_{t} \sum_{g} sc_g \cdot v_{g,t}$$

subject to: the same uc constraints as problem 5, but with dispatch indexed by scenario, and commitment decisions shared across scenarios.

**specifically:**

1. solve the stochastic uc.
2. compare the commitment schedule to problem 5 (deterministic with base-case wind).
3. compute the **expected value of perfect information (evpi):** solve each scenario independently (as if you knew the wind perfectly), weight the costs by probability. evpi = stochastic cost − wait-and-see cost.
4. compute the **value of the stochastic solution (vss):** solve deterministically with base-case wind, fix the commitment decisions, then evaluate them under each scenario. vss = expected cost of deterministic solution − stochastic cost.
5. a positive vss means the stochastic approach saves money. how large is the savings?

### questions to answer

1. does the stochastic model commit more generators than the deterministic model? why might it "hedge" by keeping extra capacity online?
2. in which scenario does the system struggle most? is it the low-wind scenario?
3. how would adding storage (problem 7) affect the evpi and vss? (storage provides flexibility to handle uncertainty.)
4. if you increased the number of scenarios (e.g., 10 instead of 3), how would solve time change? this illustrates the scalability challenge of stochastic programming.

### verification

**key checks:**

- commitment variables $u_{g,t}$ must be identical across all scenarios
- dispatch variables $p_{g,t,s}$ can differ by scenario
- demand is met in every scenario
- evpi ≥ 0 (perfect information can't make things worse)
- vss ≥ 0 (the stochastic solution can't be worse than using it)
- stochastic cost should be between wait-and-see cost and deterministic-evaluated cost

```python
# verify commitment is scenario-independent
for g in thermal_gens:
    for t in model.t:
        vals = [pyo.value(model.u[g, t, s]) for s in model.s]
        assert all(abs(v - vals[0]) < 0.01 for v in vals), f"commitment differs across scenarios for {g}, hour {t}"

# verify demand balance per scenario
for s in model.s:
    for t in model.t:
        gen = sum(pyo.value(model.gen[g, t, s]) for g in model.g)
        assert abs(gen - demand[t]) < 1, f"demand not met in scenario {s}, hour {t}"

# check evpi and vss
assert evpi >= -0.1, f"evpi should be non-negative, got {evpi:.0f}"
assert vss >= -0.1, f"vss should be non-negative, got {vss:.0f}"
print(f"evpi: {evpi:,.0f} €  |  vss: {vss:,.0f} €")
print("✓ stochastic model verified")
```

---

## problem 10: the full picture — integrated cwe system model

### concepts introduced
- combining all previous concepts into one model
- multi-zone, multi-period, milp with storage and emissions
- model scaling and computational considerations
- interpreting complex model outputs for policy briefs
- professional model documentation

### background

this is your capstone. you will build an integrated model that combines cross-border dispatch (problem 4), unit commitment (problem 5), storage (problem 7), and emissions policy (problem 2) into a single, multi-zone, multi-period model of the cwe region. this is the type of model that energy consultancies, tsos, and government agencies actually use — simplified, but structurally complete.

> **real-world models in this family:**
> - [pypsa](https://pypsa.org/) — open-source python power system model, widely used in european research
> - [plexos](https://www.energyexemplar.com/plexos) — commercial, used by tsos and utilities
> - [entso-e's eraa (european resource adequacy assessment)](https://www.entsoe.eu/outlooks/eraa/) — the official eu resource adequacy model
>
> your model is a teaching-scale version of these.

### setup

combine:
- **5 zones** from problem 4 (de, fr, nl, be, pl) with interconnectors
- **24-hour horizon** with demand and renewable profiles (problem 3, scaled per zone)
- **uc constraints** for thermal generators (problem 5)
- **battery storage** in de and nl (problem 7)
- **eu-wide emissions cap** (problem 2)

**system parameters:**

use the generation fleet from problem 4 with uc parameters from problem 5 (apply proportional values for non-de generators — e.g., french nuclear min stable = 70% of capacity).

**storage:**
- de: 500 mw / 2,000 mwh battery
- nl: 300 mw / 1,200 mwh battery

**emissions cap:** 100,000 tco₂ for the 24-hour period across all five zones.

**demand profiles:** scale problem 3's hourly profile by zone:
- de: as problem 3
- fr: problem 3 profile × 0.79
- nl: problem 3 profile × 0.34
- be: problem 3 profile × 0.22
- pl: problem 3 profile × 0.43

**renewable profiles:** use problem 3's wind/solar profiles with zone-specific capacity factors from problem 4.

### your task

1. **build the integrated model.** this is substantial — take it step by step:
   - start with the multi-zone dispatch (problem 4 structure)
   - add time indexing (problem 3)
   - add uc constraints (problem 5)
   - add storage (problem 7)
   - add the emissions cap (problem 2)

2. **solve it.** use cbc with a mip gap of 0.5%. report solve time. if it's slow, consider relaxing some uc constraints (e.g., remove min up/down times for smaller generators) or reducing the number of zones.

3. **produce a results summary** that includes:
   - total system cost breakdown: generation cost, startup cost, by zone
   - cross-border flow patterns: who exports, who imports, when?
   - hourly price by zone (from duals, if lp relaxation, or approximate from marginal generators)
   - emissions by zone and by fuel type
   - storage utilisation: when do de and nl batteries charge/discharge?
   - whether the emissions cap is binding and its shadow price

4. **write a one-page policy brief** summarising your findings. key questions to address:
   - which interconnectors are congested and when?
   - what is the implicit carbon price in the cwe region?
   - is the current generation fleet adequate for the emissions target?
   - where would additional renewable investment be most valuable?
   - does storage reduce costs significantly, and where is it most useful?

### questions to answer

1. how does the model's total cost compare to the sum of problems 3+4+5 solved separately? does integration change the picture?
2. what's the most congested interconnector? what would happen if you doubled its capacity?
3. how does poland's coal dependency affect the eu-wide emissions cap? what is poland's "share" of the total emissions?
4. if you removed all interconnectors, could each zone meet the emissions cap on its own?
5. what is the solve time? how would it scale if you added more zones or hours?

### verification

```python
# === comprehensive verification ===

# 1. energy balance per zone per hour
for z in model.z:
    for t in model.t:
        gen = sum(pyo.value(model.gen[g,t]) for g in gens_in[z])
        dis = sum(pyo.value(model.dis[s,t]) for s in storage_in[z])
        ch = sum(pyo.value(model.ch[s,t]) for s in storage_in[z])
        flow_in = sum(pyo.value(model.flow[z2,z,t]) for z2 in connected[z])
        flow_out = sum(pyo.value(model.flow[z,z2,t]) for z2 in connected[z])
        balance = gen + dis - ch + flow_in - flow_out
        assert abs(balance - demand[z][t]) < 1, f"balance error: {z}, hour {t}"

# 2. total emissions under cap
total_emissions = sum(
    emissions[g] * pyo.value(model.gen[g,t])
    for g in model.g for t in model.t
    if g in thermal_gens
)
assert total_emissions <= 100000 + 1, f"emissions {total_emissions:.0f} exceed cap"

# 3. storage soc cyclical
for s in model.storage:
    assert abs(pyo.value(model.soc[s,23]) - initial_soc[s]) < 1

# 4. uc constraints
for g in thermal_gens:
    for t in model.t:
        u = round(pyo.value(model.u[g,t]))
        p = pyo.value(model.gen[g,t])
        if u == 0:
            assert p < 0.1
        else:
            assert p >= min_stable[g] - 1

# 5. flow limits
for (z1,z2) in model.lines:
    for t in model.t:
        f = pyo.value(model.flow[z1,z2,t])
        assert abs(f) <= ntc[z1,z2] + 0.1

print(f"total cost: {pyo.value(model.obj):,.0f} €")
print(f"total emissions: {total_emissions:,.0f} tco₂")
print(f"solve time: check solver log")
print("✓ full integrated model verified")
```

---

## appendix a: pyomo installation and setup

```bash
# recommended: create a virtual environment
python -m venv energy-opt
source energy-opt/bin/activate  # linux/mac
# energy-opt\scripts\activate   # windows

# install pyomo
pip install pyomo

# install free solvers (pick one method):

# option 1: conda (recommended)
conda install -c conda-forge glpk coincbc ipopt highs

# option 2: pip (highs only)
pip install highspy

# option 3: manual install
# glpk: https://www.gnu.org/software/glpk/
# cbc: https://github.com/coin-or/cbc
# highs: https://highs.dev/

# verify installation
python -c "import pyomo.environ as pyo; print('pyomo version:', pyo.__version__)"
python -c "import pyomo.environ as pyo; pyo.solverfactory('glpk').available()"
```

## appendix b: key entso-e transparency platform links

| data | url |
|------|-----|
| day-ahead electricity prices | https://transparency.entsoe.eu/transmission-domain/r2/dayaheadprices/show |
| total load (demand) | https://transparency.entsoe.eu/load-domain/r2/totalloadr2/show |
| actual generation per type | https://transparency.entsoe.eu/generation/r2/actualgenerationperproductiontype/show |
| installed generation capacity | https://transparency.entsoe.eu/generation/r2/installedgenerationcapacityaggregation/show |
| cross-border physical flows | https://transparency.entsoe.eu/transmission-domain/physicalflow/show |
| net transfer capacities (ntc) | https://transparency.entsoe.eu/transmission-domain/ntcday/show |
| wind/solar forecasts | https://transparency.entsoe.eu/generation/r2/dayaheadgenerationforecastwindandsolar/show |
| outages / unavailability | https://transparency.entsoe.eu/outage-domain/r2/unavailabilityofproductionandgenerationunits/show |

**other useful references:**

| resource | url |
|----------|-----|
| euphemia algorithm (day-ahead coupling) | https://www.nemo-committee.eu/euphemia |
| jao (cross-border capacity allocation) | https://www.jao.eu/ |
| ember carbon price tracker | https://ember-climate.org/data/data-tools/carbon-price-viewer/ |
| danish energy agency technology catalogues | https://ens.dk/en/our-services/projections-and-models/technology-data |
| irena cost data | https://www.irena.org/costs |
| pypsa (open-source power system model) | https://pypsa.org/ |
| entso-e tyndp | https://tyndp.entsoe.eu/ |
| entso-e eraa (resource adequacy) | https://www.entsoe.eu/outlooks/eraa/ |

## appendix c: problem dependency map

```
problem 1: merit order lp (single hour, single zone)
    │
    ├── problem 2: + emissions constraint & shadow prices
    │       │
    │       └── problem 8: pareto frontier (cost vs. emissions)
    │
    ├── problem 3: + 24-hour time index & ramp rates
    │       │
    │       ├── problem 5: + uc binary decisions (milp)
    │       │       │
    │       │       └── problem 9: + wind uncertainty (stochastic)
    │       │
    │       └── problem 7: + storage (battery & pumped hydro)
    │
    └── problem 4: + multiple zones & interconnectors
            │
            └── problem 10: capstone — combines 2+3+4+5+7
                             (multi-zone, multi-period, uc,
                              storage, emissions cap)

problem 6: capacity expansion (standalone but uses concepts from 1-4)
```

---

*this workbook accompanies the optimization foundations briefing. refer back to that document for the theory behind each concept as you encounter it in the problems. good luck — and remember, the shadow prices are always the most interesting part of the answer.*
