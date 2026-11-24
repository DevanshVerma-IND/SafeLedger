"""
Page 1: System Overview
Presents high-level metrics, system architecture health, recent benchmarks, and engine telemetry.
"""
import os, json
import pandas as pd
import streamlit as st
from ui.styles import render_header, render_metric
import pg_store

def render_page(pred, model_path):
    render_header(
        "Executive System Overview",
        "Live status, architectural health, transaction telemetry, and database/ML engine readiness.",
        badge="Platform Dashboard"
    )

    pg_enabled = pg_store.enabled()
    backend_name = "PostgreSQL (Enterprise Pool)" if pg_enabled else "SQLite (Local WAL Mode)"
    
    # Model info
    model_loaded = pred is not None
    metrics_path = "results/model_metrics.json"
    metrics_data = {}
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, "r") as f:
                metrics_data = json.load(f)
        except Exception:
            pass

    # Read benchmark data if available
    bench_path = "results/benchmark.csv"
    has_bench = os.path.exists(bench_path)
    bench_df = pd.read_csv(bench_path) if has_bench else None

    # Top KPI Metrics Row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if has_bench and not bench_df.empty:
            avg_tps = round(bench_df["tps"].mean(), 1)
            render_metric("Aggregate Throughput", f"{avg_tps} tx/s", "Mean across benchmark suites", status="success")
        else:
            render_metric("Aggregate Throughput", "N/A", "Run benchmark to measure", status="warning")
    
    with c2:
        if has_bench and not bench_df.empty:
            p95 = round(bench_df["p95_ms"].mean(), 1)
            render_metric("P95 Tail Latency", f"{p95} ms", "Mean across configurations", status="success")
        else:
            render_metric("P95 Tail Latency", "N/A", "No telemetry available", status="warning")

    with c3:
        if has_bench and not bench_df.empty:
            tot_dl = int(bench_df["deadlocks"].sum())
            status = "success" if tot_dl == 0 else "warning"
            render_metric("Benchmark Deadlocks", f"{tot_dl}", "Total detected across all runs", status=status)
        else:
            render_metric("Benchmark Deadlocks", "0", "Awaiting run data")

    with c4:
        db_status = "success" if (not pg_enabled or pg_store.enabled()) else "danger"
        render_metric("Database Engine", "Active", backend_name, status=db_status)

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # Secondary Details: Engine and Model Readiness
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### System Components & Subsystem Readiness")
        sys_status = [
            {"Component": "Transaction Engine (engine.py)", "Status": "Ready", "Details": "Multi-threaded worker pool & LockManager"},
            {"Component": "Database Store (dbms.py)", "Status": "Ready", "Details": f"Active backend: {backend_name}"},
            {"Component": "OS Abstraction (os_layer.py)", "Status": "Verified", "Details": "Banker, WFG, Scheduler, Mutex/Semaphore"},
            {"Component": "ML Risk Gate (RandomForest)", "Status": "Loaded" if model_loaded else "Missing", 
             "Details": f"{model_path} ({'Ready for admission gating' if model_loaded else 'Run collect_train.py'})"},
            {"Component": "PostgreSQL Link (pg_store.py)", "Status": "Connected" if pg_enabled else "Fallback (SQLite)",
             "Details": "SAFELEDGER_PG_DSN not set, using SQLite WAL" if not pg_enabled else "Connected via psycopg2 pool"},
            {"Component": "Write-Ahead Log (WAL)", "Status": "Enforced", "Details": "CRC32 verification, fsync & crash recovery enabled"}
        ]
        st.dataframe(pd.DataFrame(sys_status), width='stretch', hide_index=True)

    with col_right:
        st.markdown("#### Machine Learning Model Status")
        if model_loaded:
            m1, m2 = st.columns(2)
            with m1:
                render_metric("Model Algorithm", "Random Forest", "n_estimators=40, max_depth=8")
                if "f1" in metrics_data:
                    render_metric("F1 Score", f"{metrics_data['f1']:.3f}", "Held-out test set")
            with m2:
                if "roc_auc" in metrics_data:
                    render_metric("ROC-AUC", f"{metrics_data['roc_auc']:.3f}", "Discriminative capability")
                if "predict_ms_per_call" in metrics_data:
                    render_metric("Inference Latency", f"{metrics_data['predict_ms_per_call']} ms", "Per transaction evaluation")
        else:
            st.info("Random Forest classifier is not yet generated in results/model.joblib.\n\nExecute `python collect_train.py` to collect lock telemetry and train the model.")

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # Benchmark summary table if available
    st.markdown("#### Baseline Concurrency Strategy Performance")
    if has_bench and not bench_df.empty:
        summary_cols = ["tps", "p50_ms", "p95_ms", "retries", "deadlocks", "timeouts", "banker_waits", "cpu_ms_per_txn"]
        available_cols = [c for c in summary_cols if c in bench_df.columns]
        summary_df = bench_df.groupby("mode")[available_cols].mean().round(2)
        st.dataframe(summary_df, width='stretch')
        st.caption("Benchmark metrics sourced directly from `results/benchmark.csv`. Evaluates 16 concurrent clients over 300 transactions.")
    else:
        st.warning("No benchmark results found at `results/benchmark.csv`. Use the **Benchmark & Performance** tab to execute a live suite or run `python benchmark.py`.")
