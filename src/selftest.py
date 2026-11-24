"""Fast correctness checks (about 15 s). Run: python selftest.py"""
import numpy as np
from engine import *
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("[PASS] " if cond else "[FAIL] ") + name)

specs = make_specs(120, seed=99)
pr = Predictor("results/model.joblib")
for m in ["naive", "wfg", "ordered", "banker", "wfg+ml", "banker+ml"]:
    r = run_load(specs, m, predictor=pr)
    check(f"{m}: money conserved and no lost transfer ({r['committed']}/{len(specs)} committed)",
          r["money_conserved"] and r["committed"] + r["failed"] == len(specs))
    if m in ("banker", "banker+ml", "ordered"): check(f"{m}: zero deadlocks", r["deadlocks"] == 0)
check("naive deadlocks on opposite transfers and stalls to the timeout", deadlock_scenario("naive")["timeouts"] >= 1)
check("wfg detects it immediately (no timeout)", deadlock_scenario("wfg")["deadlocks"] >= 1 and deadlock_scenario("wfg")["timeouts"] == 0)
check("banker avoids it (zero deadlocks, zero retries)", deadlock_scenario("banker")["retries"] == 0)
bad = HttpPredictor("http://localhost:5999/predict")
r = deadlock_scenario("banker+ml", bad)
check("ML service down: fallback used, both transfers still commit", r["ml_fallbacks"] >= 1 and r["committed"] == 2)
X = np.array([[2, 3, 2, 120, 2], [0, 0, 0, 5, 1], [3, 8, 5, 400, 3]], float)
mine = [pr(dict(zip(FEATURES, x))) for x in X]
check("fast predictor equals scikit-learn", np.allclose(mine, pr.model.predict_proba(X)[:, 1]))
print("ALL PASSED" if ok else "SOME FAILED"); raise SystemExit(0 if ok else 1)
