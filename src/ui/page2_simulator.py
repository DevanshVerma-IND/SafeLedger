"""
Page 2: Concurrent Transaction Simulator
Integrates engine.py to simulate high-concurrency bank workloads across different locking & admission modes.
"""
import time
import pandas as pd
import streamlit as st
from engine import make_specs, run_load
from ui.styles import render_header, render_metric

MODES = ["naive", "wfg", "ordered", "banker", "wfg+ml", "banker+ml"]
HELP = {
    "naive": "Business-order locks, timeout only (reactive baseline). Deadlock prone.",
    "wfg": "Wait-For-Graph detection, then aborts a selected victim transaction.",
    "ordered": "Locks acquired in strict ascending account ID order (avoids circular wait).",
    "banker": "Banker's Algorithm safe-state check before each lock is granted.",
    "wfg+ml": "ML admission risk gate + Wait-For-Graph detection.",
    "banker+ml": "ML admission risk gate + Banker's safe-state check (full SafeLedger)."
}

def render_page(pred, model_path):
    render_header(
        "Concurrent Transaction Simulator",
        "Executes multi-threaded workloads against the live database engine under competing concurrency control mechanisms.",
        badge="Engine Simulation"
    )

    with st.expander("Workload Configuration & Execution Parameters", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        n_txns = col1.slider("Transactions", min_value=50, max_value=600, value=200, step=50,
                             help="Total number of transfer specifications to submit")
        workers = col2.slider("Concurrent Worker Threads", min_value=2, max_value=32, value=8,
                              help="Parallel client threads executing transfers concurrently")
        hot_frac = col3.slider("Contention (Hot Share)", min_value=0.1, max_value=1.0, value=0.7, step=0.05,
                               help="Fraction of transfers targeting the 8 hot accounts")
        seed = col4.number_input("Workload Seed", min_value=1, max_value=9999, value=42, step=1)

        default_modes = ["naive", "wfg", "banker+ml"] if pred else ["naive", "wfg", "banker"]
        selected_modes = st.multiselect(
            "Concurrency Strategies to Compare",
            MODES,
            default=default_modes,
            format_func=lambda m: f"{m.upper()}: {HELP[m]}"
        )

    if st.button("Execute Concurrency Simulation", type="primary"):
        if not selected_modes:
            st.error("Please select at least one concurrency strategy.")
            return

        # Prepare specifications via engine
        specs = make_specs(n_txns, seed=int(seed), hot_frac=float(hot_frac), source="synthetic")
        
        results = []
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        for idx, mode in enumerate(selected_modes):
            if mode.endswith("+ml") and not pred:
                st.warning(f"Skipping '{mode}' because ML model is not available.")
                continue

            status_text.text(f"Running mode: {mode} ({idx+1}/{len(selected_modes)})...")
            t0 = time.perf_counter()
            res = run_load(specs, mode, workers=workers, predictor=pred, seed=int(seed))
            dur = time.perf_counter() - t0
            res["elapsed_s"] = round(dur, 2)
            results.append(res)
            progress_bar.progress((idx + 1) / len(selected_modes))

        status_text.empty()
        progress_bar.empty()

        if results:
            st.session_state["last_sim_results"] = results
            st.success(f"Simulation completed across {len(results)} configurations.")

    # Display results if available in session state
    if "last_sim_results" in st.session_state:
        res_list = st.session_state["last_sim_results"]
        df = pd.DataFrame(res_list).set_index("mode")

        st.markdown("#### Performance & Concurrency Telemetry")
        
        # Summary metrics from first or best
        c1, c2, c3, c4 = st.columns(4)
        best_tps = df["tps"].max()
        best_mode = df["tps"].idxmax()
        c1.metric("Highest Throughput", f"{best_tps:.1f} tx/s", f"Mode: {best_mode}")
        
        min_p95 = df["p95_ms"].min()
        min_p95_mode = df["p95_ms"].idxmin()
        c2.metric("Lowest P95 Latency", f"{min_p95:.1f} ms", f"Mode: {min_p95_mode}")
        
        tot_deadlocks = int(df["deadlocks"].sum())
        c3.metric("Total Deadlocks", f"{tot_deadlocks}", "Across all executed modes")
        
        all_conserved = all(df["money_conserved"])
        c4.metric("Money Conservation", "100% Conserved" if all_conserved else "VIOLATION",
                  "ACID integrity confirmed" if all_conserved else "Audit failed")

        display_cols = [
            "committed", "failed", "retries", "deadlocks", "timeouts", 
            "banker_waits", "ml_delays", "tps", "p50_ms", "p95_ms", 
            "cpu_ms_per_txn", "money_conserved"
        ]
        available_cols = [c for c in display_cols if c in df.columns]
        
        st.dataframe(df[available_cols], width='stretch')

        # Charts
        st.markdown("#### Comparative Analytics")
        ch1, ch2 = st.columns(2)
        with ch1:
            st.markdown("**Throughput (Transactions / Second) - Higher is Better**")
            st.bar_chart(df[["tps"]])
        with ch2:
            st.markdown("**P95 Tail Latency (Milliseconds) - Lower is Better**")
            st.bar_chart(df[["p95_ms"]])
            
        ch3, ch4 = st.columns(2)
        with ch3:
            st.markdown("**Aborted Retries & Deadlocks - Lower is Better**")
            ret_dl = df[["retries", "deadlocks"]]
            st.bar_chart(ret_dl)
        with ch4:
            st.markdown("**Banker Waits vs ML Delays**")
            waits_delays = df[["banker_waits", "ml_delays"]]
            st.bar_chart(waits_delays)
    else:
        st.info("Configure parameters and click 'Execute Concurrency Simulation' above to generate real-time execution telemetry.")
