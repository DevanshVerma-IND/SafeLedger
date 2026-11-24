"""
Page 3: Deadlock Detection Lab
Interactive deadlock demonstration running deadlock_scenario() from engine.py and WFG inspection from os_layer.py.
"""
import time
import pandas as pd
import streamlit as st
from engine import deadlock_scenario
import os_layer
from ui.styles import render_header, render_metric

HELP_STRATEGIES = {
    "naive": "Business-order locking without detection: both threads hold one lock and wait indefinitely until timeout kicks in.",
    "wfg": "Wait-For Graph detector identifies circular dependency graph immediately and aborts the lower priority victim.",
    "banker": "Deadlock avoidance: Banker evaluates allocation safety before grant and avoids entering the circular wait state entirely.",
    "banker+ml": "Combined Banker's algorithm and machine learning risk score admission gate."
}

def render_page(pred, model_path):
    render_header(
        "Deadlock Detection & Resolution Lab",
        "Empirical analysis of Coffman conditions, Wait-For Graph (WFG) cycle detection, and victim selection.",
        badge="Concurrency Lab"
    )

    st.markdown("""
    When two concurrent transactions attempt transfers in opposing directions (e.g., Transfer 1: `Account A -> Account B` 
    and Transfer 2: `Account B -> Account A`), they hold one lock each and request the other. This scenario triggers all 
    four Coffman conditions (**Mutual Exclusion, Hold and Wait, No Preemption, Circular Wait**).
    """)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### Scenario Configuration")
        strat = st.selectbox(
            "Concurrency Control Strategy",
            ["naive", "wfg", "banker", "banker+ml"],
            format_func=lambda s: f"{s.upper()}: {HELP_STRATEGIES[s]}"
        )
        
        sim_ml_failure = False
        if strat == "banker+ml":
            sim_ml_failure = st.checkbox("Simulate ML Service Outage (Trigger Fallback)", value=False)

        run_btn = st.button("Execute Deadlock Scenario", type="primary")

    with col2:
        st.markdown("#### Strategy Architectural Rule")
        st.info(HELP_STRATEGIES[strat])
        if strat == "naive":
            st.warning("Expected Outcome: Stalls until the 100ms lock timeout deadline is reached.")
        elif strat == "wfg":
            st.success("Expected Outcome: Zero timeouts. Cycle detected via DFS; victim aborted and retried.")
        elif strat in ("banker", "banker+ml"):
            st.success("Expected Outcome: Zero deadlocks. Grants only when a safe execution sequence exists.")

    if run_btn:
        predictor_to_use = None
        if strat == "banker+ml":
            if sim_ml_failure:
                predictor_to_use = os_layer.HttpPredictor("http://localhost:5999/predict")
            else:
                predictor_to_use = pred

        with st.spinner(f"Executing real opposite-transfer scenario under '{strat}'..."):
            t0 = time.perf_counter()
            result = deadlock_scenario(strat, predictor=predictor_to_use)
            elapsed = time.perf_counter() - t0

        st.session_state["deadlock_result"] = result
        st.session_state["deadlock_strat"] = strat

    if "deadlock_result" in st.session_state:
        res = st.session_state["deadlock_result"]
        cur_strat = st.session_state["deadlock_strat"]

        st.markdown(f"#### Execution Telemetry ({cur_strat.upper()})")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Wall Clock Time", f"{res['wall_s']:.3f} s", "Total elapsed")
        m2.metric("Committed Transfers", f"{res['committed']}/2", "Both succeed eventually")
        m3.metric("Deadlocks Detected", f"{res['deadlocks']}", "WFG cycles found")
        m4.metric("Timeouts Triggered", f"{res['timeouts']}", "Unresolved stalls")
        m5.metric("Aborted Retries", f"{res['retries']}", "Victim restarts")

        # Telemetry table
        st.dataframe(pd.DataFrame([res]), width='stretch')

    st.markdown("---")
    st.markdown("#### Standalone Wait-For Graph (WFG) Interactive Demonstration")
    st.markdown("""
    Below is the deterministic OS-layer lock manager demonstrating the cycle detection algorithm 
    (from `os_layer.LockManager`) with priority-based victim selection.
    """)

    w1, w2 = st.columns([1, 1])
    with w1:
        st.markdown("**Process & Request Setup**")
        prio_t1 = st.number_input("Transaction T1 Priority (Lower = Higher Priority)", min_value=1, max_value=10, value=1)
        prio_t2 = st.number_input("Transaction T2 Priority (Lower = Higher Priority)", min_value=1, max_value=10, value=3)
        st.caption("T1 requests Account A then B; T2 requests Account B then A.")
        
        if st.button("Run WFG Cycle Detection & Recovery"):
            lm = os_layer.LockManager()
            lm.register("T1", prio_t1)
            lm.register("T2", prio_t2)
            lm.request("T1", "ACC_A")
            lm.request("T2", "ACC_B")
            r1 = lm.request("T1", "ACC_B")  # T1 waits on T2
            r2 = lm.request("T2", "ACC_A")  # T2 waits on T1 -> cycle!

            graph = {k: sorted(v) for k, v in lm.wait_for_graph().items()}
            cycle = lm.find_cycle()
            victims = lm.resolve_deadlocks()
            remaining_cycle = lm.find_cycle()

            st.session_state["wfg_demo"] = {
                "graph": graph,
                "cycle": cycle,
                "victims": victims,
                "remaining_cycle": remaining_cycle,
                "log": lm.log,
                "owners": dict(lm.holder)
            }

    with w2:
        if "wfg_demo" in st.session_state:
            demo = st.session_state["wfg_demo"]
            st.markdown("**Graph State & Cycle Detection**")
            st.code(f"Wait-For Graph adjacency list:\n{demo['graph']}", language="python")
            
            if demo["cycle"]:
                st.error(f"Cycle detected: {' -> '.join(demo['cycle'])}")
            else:
                st.success("No cycles detected.")

            st.markdown("**Victim Selection & Resolution**")
            st.info(f"Selected victim(s) aborted: {demo['victims']}")
            st.write(f"Active lock holders post-resolution: `{demo['owners']}`")
            st.write(f"Remaining cycles: `{demo['remaining_cycle']}` (None means clean recovery)")
            
            with st.expander("Lock Manager Internal Log", expanded=False):
                for entry in demo["log"]:
                    st.text(entry)
