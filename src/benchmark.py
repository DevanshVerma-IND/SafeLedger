"""Benchmark: 6 configurations x 5 workloads (seeds 1-5, held out from training), plus a concurrency sweep.
Writes results/benchmark.csv, results/sweep.csv and results/benchmark.png.
In Postgres mode (SAFELEDGER_PG_DSN set) the workloads of split 'benchmark' and 'sweep' are read from the database
and every run is also recorded in the `runs` table."""
import csv, statistics as st, sys
from engine import make_specs, run_load, Predictor
import pg_store

MODES = ["naive", "wfg", "ordered", "banker", "wfg+ml", "banker+ml"]
SEEDS = [1, 2, 3, 4, 5]
N_TXNS, WORKERS, THRESHOLD = 300, 16, 0.5     # fixed before the runs; no tuning on the results

def main(quick=False):
    pr = Predictor("results/model.joblib"); rows = []
    seeds, sweep_seeds = SEEDS, [11, 12, 13]
    if pg_store.enabled(): seeds, sweep_seeds = pg_store.workload_seeds("benchmark"), pg_store.workload_seeds("sweep")
    for seed in seeds[:2] if quick else seeds:
        specs = make_specs(N_TXNS, seed)
        for m in MODES:
            r = run_load(specs, m, workers=WORKERS, predictor=pr, threshold=THRESHOLD, seed=seed)
            r["seed"] = seed; rows.append(r); print(seed, m, r["tps"], r["p95_ms"], r["deadlocks"], flush=True)
    keys = list(rows[0]); w = csv.DictWriter(open("results/benchmark.csv", "w", newline=""), keys); w.writeheader(); w.writerows(rows)
    sweep = []
    for workers in [4, 8, 16, 32]:
        for seed in sweep_seeds:
            specs = make_specs(N_TXNS, seed)
            for m in ["naive", "wfg", "banker+ml"]:
                r = run_load(specs, m, workers=workers, predictor=pr, threshold=THRESHOLD, seed=seed)
                r["workers"], r["seed"] = workers, seed; sweep.append(r)
        print("sweep workers", workers, flush=True)
    keys = list(sweep[0]); w = csv.DictWriter(open("results/sweep.csv", "w", newline=""), keys); w.writeheader(); w.writerows(sweep)
    plot(rows, sweep)

def agg(rows, mode, key, **flt):
    v = [r[key] for r in rows if r["mode"] == mode and all(r[k] == x for k, x in flt.items())]
    return st.mean(v), (st.stdev(v) if len(v) > 1 else 0)

def plot(rows, sweep):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 4, figsize=(17, 3.8))
    for a, (k, t) in zip(ax[:3], [("tps", "Throughput (txn/s), higher is better"),
                                  ("p95_ms", "95th-percentile latency (ms), lower is better"),
                                  ("retries", "Aborted-and-retried attempts, lower is better")]):
        m = [agg(rows, x, k) for x in MODES]
        a.bar(MODES, [x[0] for x in m], yerr=[x[1] for x in m], color="#2E5B9A", capsize=3); a.set_title(t, fontsize=9)
        a.tick_params(axis="x", rotation=40, labelsize=8)
    for m, c in [("naive", "#B85450"), ("wfg", "#E0A030"), ("banker+ml", "#2E8B57")]:
        xs = [4, 8, 16, 32]; ax[3].plot(xs, [agg(sweep, m, "tps", workers=w)[0] for w in xs], marker="o", label=m, color=c)
    ax[3].set_title("Throughput vs concurrent clients", fontsize=9); ax[3].set_xlabel("clients"); ax[3].legend(fontsize=8)
    plt.tight_layout(); plt.savefig("results/benchmark.png", dpi=130)

if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
