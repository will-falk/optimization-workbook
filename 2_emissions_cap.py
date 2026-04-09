import pyomo.environ as pyo

model = pyo.ConcreteModel()

# --- scalars/constants ---
model.DEMAND = 8200
model.EMISSIONS_CAP = 4774.4

# --- sets ---
model.PLANTS = pyo.Set(initialize= ['wind', 'solar', 'lignite_1', 'coal_1', 'ccgt_1', 'ccgt_2', 'ocgt_1'])

# --- parameters (like columns in a dataframe, indexed by PLANTS) ---
model.cost     = pyo.Param(model.PLANTS, initialize={'wind': 0, 'solar': 0, 'lignite_1': 18, 'coal_1': 36, 'ccgt_1': 63, 'ccgt_2': 70, 'ocgt_1': 92})
model.capacity = pyo.Param(model.PLANTS, initialize={'wind': 1120, 'solar': 450, 'lignite_1': 2800, 'coal_1': 1200, 'ccgt_1': 1600, 'ccgt_2': 1000, 'ocgt_1': 600})
model.emissions = pyo.Param(model.PLANTS,initialize= {'lignite_1': 1.08, 'coal_1': 0.88, 'ccgt_1': 0.37, 'ccgt_2': 0.40, 'ocgt_1': 0.53, 'wind': 0.00, 'solar': 0.00})

# --- duals ---
model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

# --- decision variables ---
#power generated
model.generated = pyo.Var(model.PLANTS, domain=pyo.NonNegativeReals)

# --- objective ---
def total_cost_rule(model):
    return sum(model.cost[plant] * model.generated[plant] for plant in model.PLANTS)
model.obj = pyo.Objective(rule=total_cost_rule, sense=pyo.minimize)

# --- constraints ---

# one constraint per plant: can't exceed capacity
# note that the var generated has a 0 bound already so not necc here
def capacity_rule(model, plant):
    return model.generated[plant] <= model.capacity[plant]
model.capacity_con = pyo.Constraint(model.PLANTS, rule=capacity_rule)

# demand constraint has no index — it's one rule about all plants together, so no set is passed to pyo.Constraint and the rule only takes m
def demand_rule(model):
    return sum(model.generated[plant] for plant in model.PLANTS) >= model.DEMAND
model.demand_con = pyo.Constraint(rule=demand_rule)

# a second constraint over the entire mix
def emissions_rule(model):
    return sum(model.generated[plant] * model.emissions[plant] for plant in model.PLANTS) <= model.EMISSIONS_CAP
model.emissions_con = pyo.Constraint(rule=emissions_rule)

# --- solving ---

solver = pyo.SolverFactory('glpk') 

result = solver.solve(model, tee=True) #verbose...

model.display() #print model for reference

print(result.solver.status) # looking for ok

print(result.solver.termination_condition) # looking for optimal

# --- duals ---
print("\nDual values (shadow prices):")
print(f"  demand_con: {model.dual[model.demand_con]:.2f}  ← marginal cost of energy (market price)")
print(f"  emissions_con: {model.dual[model.emissions_con]:.2f}  ← cost of abatement \n")

print("  marginal cost per plant")
for plant in model.PLANTS:
    print(f"  capacity_con[{plant}]: {model.dual[model.capacity_con[plant]]:.2f}")


# ---- checks ---
# assert abs(pyo.value(model.obj) - 267160) < 1, f"objective should be 267,160, got {pyo.value(model.obj)}"
# assert abs(pyo.value(model.generated['ocgt_1']) - 30) < 1, f"ocgt_1 should produce 30 mw"
# assert abs(model.dual[model.demand_con] - 92) < 0.01, f"shadow price should be 92 €/mwh"
# print("✓ all checks passed!")