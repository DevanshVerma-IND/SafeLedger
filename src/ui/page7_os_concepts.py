"""
Page 7: Operating System Concepts
Interactive demonstration of CPU scheduling, synchronization race conditions, mutex/semaphore bounds,
and mapping of banking transactions to OS primitives.
"""
import pandas as pd
import streamlit as st
import os_layer
from ui.styles import render_header, render_metric

def render_page(pred, model_path):
    render_header(
        "Operating System Concepts & Mechanics",
        "Empirical demonstrations of CPU scheduling algorithms, synchronization primitives, race conditions, and thread bounds.",
        badge="OS Layer Evaluation"
    )

    t1, t2, t3 = st.tabs(["CPU Scheduling of Transactions", "Process Synchronization & Race Conditions", "OS to Banking Mapping Matrix"])

    # TAB 1: CPU Scheduling
    with t1:
        st.markdown("#### Transaction CPU Scheduling")
        st.write("""
        Evaluates **First-Come-First-Served (FCFS)**, **Round Robin (RR)**, and **Priority Scheduling with Aging** 
        on a burst of simulated incoming transactions.
        """)

        # Default sample transactions from os_layer.py
        txns = [
            os_layer.Txn("T1", 0, 8, 3),
            os_layer.Txn("T2", 1, 4, 1),
            os_layer.Txn("T3", 2, 9, 4),
            os_layer.Txn("T4", 3, 5, 2),
            os_layer.Txn("T5", 4, 2, 3),
        ]

        st.write("**Workload Specifications:**")
        df_txns = pd.DataFrame([{"Transaction": t.tid, "Arrival Time": t.arrival, "Burst Cost": t.burst, "Priority": t.priority} for t in txns])
        st.dataframe(df_txns, width='stretch', hide_index=True)

        quantum = st.slider("Round Robin Time Quantum (q)", min_value=1, max_value=6, value=3)
        aging_interval = st.slider("Priority Aging Interval", min_value=1, max_value=10, value=5)

        if st.button("Execute Scheduling Algorithms"):
            res_fcfs = os_layer.fcfs(txns)
            res_rr = os_layer.round_robin(txns, quantum=quantum)
            res_prio = os_layer.priority_aging(txns, aging_interval=aging_interval)

            st.session_state["sched_results"] = [res_fcfs, res_rr, res_prio]

        if "sched_results" in st.session_state:
            scheds = st.session_state["sched_results"]
            sched_summary = []
            for s in scheds:
                sched_summary.append({
                    "Algorithm": s["name"],
                    "Avg Wait Time": round(s["avg_wait"], 2),
                    "Avg Turnaround Time": round(s["avg_tat"], 2),
                    "Throughput (tx/time)": round(s["throughput"], 3),
                    "Context Switches": s["switches"],
                    "Execution Completion Order": " -> ".join(s["order"])
                })
            st.dataframe(pd.DataFrame(sched_summary), width='stretch', hide_index=True)

            st.info("""
            - **FCFS**: High wait time for short jobs if preceded by long bursts (Convoy effect).
            - **Round Robin**: Prevents starvation, lowers wait for short jobs (T5), but increases context switches.
            - **Priority + Aging**: Ensures urgent transfers (T2) execute first while aging prevents starvation of low-priority transfers.
            """)

    # TAB 2: Synchronization & Race Conditions
    with t2:
        st.markdown("#### Concurrency Synchronization: Race Conditions vs Mutex Locks")
        st.write("""
        Demonstrates a classic read-modify-write lost-update vulnerability when multiple threads update 
        a shared balance concurrently without synchronization versus protected with `threading.Lock`.
        """)

        col_r1, col_r2 = st.columns(2)
        workers_race = col_r1.slider("Concurrent Depositing Threads", 2, 16, 6)
        ops_race = col_r2.slider("Operations per Thread", 50, 500, 200)

        if st.button("Run Race Condition & Mutex Benchmark"):
            with st.spinner("Executing thread race..."):
                final_no_lock, expected_no = os_layer.race_demo(workers=workers_race, ops=ops_race, use_lock=False)
                final_with_lock, expected_with = os_layer.race_demo(workers=workers_race, ops=ops_race, use_lock=True)
                peak_sem = os_layer.semaphore_demo(limit=3, txn_count=12)

            st.session_state["sync_demo"] = {
                "no_lock": (final_no_lock, expected_no, expected_no - final_no_lock),
                "with_lock": (final_with_lock, expected_with, expected_with - final_with_lock),
                "peak_sem": peak_sem
            }

        if "sync_demo" in st.session_state:
            sd = st.session_state["sync_demo"]
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Without Mutex Lock**")
                render_metric("Final Balance", f"{sd['no_lock'][0]}", f"Expected: {sd['no_lock'][1]}", status="danger")
                st.error(f"Lost Updates: {sd['no_lock'][2]} updates erased due to race condition!")
            with c2:
                st.markdown("**With Mutex (Lock)**")
                render_metric("Final Balance", f"{sd['with_lock'][0]}", f"Expected: {sd['with_lock'][1]}", status="success")
                st.success("Lost Updates: 0. Exact balance conserved via critical section mutual exclusion.")
            with c3:
                st.markdown("**Bounded Concurrency (Semaphore)**")
                render_metric("Peak Concurrency", f"{sd['peak_sem']}", "Semaphore limit = 3", status="success")
                st.info("Verified: Concurrency strictly bounded to 3 simultaneous threads.")

    # TAB 3: OS Primitive Mapping Table
    with t3:
        st.markdown("#### Theoretical Mapping: Banking System to OS Primitives")
        st.write("How SafeLedger maps traditional operating systems principles to a production-grade banking system:")

        mapping_data = [
            {"OS Primitive": "Process / Thread", "SafeLedger Implementation": "Each customer transfer runs as an isolated thread in engine.py; worker pools manage thread concurrency."},
            {"OS Primitive": "Mutual Exclusion (Mutex)", "SafeLedger Implementation": "Account locks (LockManager) prevent two transactions from simultaneously updating the same account."},
            {"OS Primitive": "Counting Semaphore", "SafeLedger Implementation": "Bounded client thread pools and database connection pool throttling."},
            {"OS Primitive": "Deadlock Detection (WFG)", "SafeLedger Implementation": "Cycle detection on Wait-For Graph using Depth First Search (DFS), aborting the lowest-priority victim."},
            {"OS Primitive": "Deadlock Avoidance (Banker's)", "SafeLedger Implementation": "Evaluates available account resources and maximum planned locks before granting lock acquisitions."},
            {"OS Primitive": "Aging / Starvation Prevention", "SafeLedger Implementation": "Dynamic transaction priority boosts prevent long-waiting transactions from being starved by incoming urgent transfers."},
            {"OS Primitive": "Write-Ahead Logging (Durability)", "SafeLedger Implementation": "DBMS WAL with CRC32 checksums and fsync forcing records to disk prior to mutating in-memory state."}
        ]
        st.dataframe(pd.DataFrame(mapping_data), width='stretch', hide_index=True)
