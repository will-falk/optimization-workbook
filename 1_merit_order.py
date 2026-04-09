import pyomo.environ as pyo

model = pyo.ConcreteModel()

# --- scalars/constants ---
model.DEMAND = 8200

# --- sets ---
model.PLANTS = pyo.Set(initialize= ['wind', 'solar', 'lignite_1', 'coal_1', 'ccgt_1', 'ccgt_2', 'ocgt_1'])

# --- parameters (like columns in a dataframe, indexed by PLANTS) ---
model.cost     = pyo.Param(model.PLANTS, initialize={'wind': 0, 'solar': 0, 'lignite_1': 18, 'coal_1': 36, 'ccgt_1': 63, 'ccgt_2': 70, 'ocgt_1': 92})
model.capacity = pyo.Param(model.PLANTS, initialize={'wind': 1120, 'solar': 450, 'lignite_1': 2800, 'coal_1': 1200, 'ccgt_1': 1600, 'ccgt_2': 1000, 'ocgt_1': 600})

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
model.cap_con = pyo.Constraint(model.PLANTS, rule=capacity_rule)

# demand constraint has no index — it's one rule about all plants together, so no set is passed to pyo.Constraint and the rule only takes m
def demand_rule(model):
    return sum(model.generated[plant] for plant in model.PLANTS) >= model.DEMAND
model.demand_con = pyo.Constraint(rule=demand_rule)

# --- solving ---

solver = pyo.SolverFactory('glpk') 

result = solver.solve(model, tee=True) #verbose...

model.display() #print model for reference

print(result.solver.status) # looking for ok

print(result.solver.termination_condition) # looking for optimal

# --- duals ---
print("\nDual values (shadow prices):")
print(f"  demand_con: {model.dual[model.demand_con]:.2f}  ← marginal cost of energy (market price)")
for plant in model.PLANTS:
    print(f"  cap_con[{plant}]: {model.dual[model.cap_con[plant]]:.2f}")


# ---- checks ---
assert abs(pyo.value(model.obj) - 267160) < 1, f"objective should be 267,160, got {pyo.value(model.obj)}"
assert abs(pyo.value(model.generated['ocgt_1']) - 30) < 1, f"ocgt_1 should produce 30 mw"
assert abs(model.dual[model.demand_con] - 92) < 0.01, f"shadow price should be 92 €/mwh"
print("✓ all checks passed!")