"""Collect lock telemetry from the running engine, train the Random Forest, test on a held-out workload.
Training workloads use seeds 101-106; the held-out test workload uses seed 201; benchmark.py uses other seeds.

With SAFELEDGER_PG_DSN set (Postgres mode): the transfer requests are read from the `workloads` of split 'train' /
'test', every lock attempt is logged to `lock_events`, the Random Forest is fitted on the v_train_set / v_test_set
views, and the metrics are stored in `model_registry`. Without it, the original in-memory synthetic path runs.

    python collect_train.py             # replay the workloads, REPLACE the stored lock_events, train, test
    python collect_train.py --from-db   # no simulation: train and test on the lock_events already stored in Postgres"""
import json, sys, time
import numpy as np, joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix
from engine import FEATURES, make_specs, run_load
import pg_store

def gather(seeds, n=300):                      # original path: synthetic, in memory
    rows = []
    for s in seeds:
        run_load(make_specs(n, s, source="synthetic"), "naive", collect=rows, seed=s)
    X = np.array([[r[k] for k in FEATURES] for r in rows], float); y = np.array([r["label"] for r in rows])
    return X, y

def gather_pg(split, n=300):                   # Postgres path: replay stored workloads, log, read back with SQL
    pg_store.reset_split(split)                # a re-run replaces the old dataset instead of mixing with it
    for seed in pg_store.workload_seeds(split):
        rows = []
        res = run_load(make_specs(n, seed), "naive", collect=rows, seed=seed)
        pg_store.save_events(res["run_id"], rows)
        print(f"  {split} workload seed {seed}: {len(rows)} lock attempts logged (run {res['run_id']})")
    return pg_store.load_events(split)

if __name__ == "__main__":
    print("collecting training telemetry (naive-lock runs)...")
    if "--from-db" in sys.argv:
        if not pg_store.enabled(): sys.exit("--from-db needs SAFELEDGER_PG_DSN to be set")
        print("--from-db: using the lock_events already stored in Postgres (no simulation)")
        Xtr, ytr = pg_store.load_events("train"); Xte, yte = pg_store.load_events("test")
    elif pg_store.enabled(): Xtr, ytr = gather_pg("train"); Xte, yte = gather_pg("test")
    else: Xtr, ytr = gather(range(101, 107)); Xte, yte = gather([201])
    print(f"train rows {len(ytr)} (deadlock/timeout share {ytr.mean():.2%}); test rows {len(yte)} ({yte.mean():.2%})")
    model = RandomForestClassifier(n_estimators=40, max_depth=8, min_samples_leaf=3,
                                   class_weight="balanced_subsample", random_state=42, n_jobs=1).fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]; pred = (p >= 0.5).astype(int)
    t0 = time.perf_counter()
    for _ in range(200): model.predict_proba(Xte[:1])
    lat = (time.perf_counter() - t0) / 200 * 1000
    m = {"train_rows": int(len(ytr)), "test_rows": int(len(yte)), "positive_share_test": float(yte.mean()),
         "precision": float(precision_score(yte, pred, zero_division=0)), "recall": float(recall_score(yte, pred)),
         "f1": float(f1_score(yte, pred)), "roc_auc": float(roc_auc_score(yte, p)),
         "false_positive_rate": float(((pred == 1) & (yte == 0)).sum() / max((yte == 0).sum(), 1)),
         "confusion_matrix": confusion_matrix(yte, pred).tolist(), "predict_ms_per_call": round(lat, 2),
         "feature_importance": dict(zip(FEATURES, map(float, model.feature_importances_)))}
    joblib.dump(model, "results/model.joblib"); json.dump(m, open("results/model_metrics.json", "w"), indent=1)
    if pg_store.enabled(): pg_store.save_model(m, "results/model.joblib")
    print(json.dumps(m, indent=1))
