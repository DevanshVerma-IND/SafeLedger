"""
Page 4: Banker's Algorithm
Demonstrates the real Banker's algorithm implementation from os_layer.py on both textbook and banking resource environments.
"""
import pandas as pd
import streamlit as st
from os_layer import Banker
from ui.styles import render_header, render_metric

def render_page(pred, model_path):
    render_header(
        "Banker's Algorithm — Deadlock Avoidance Lab",
        "Rigorous verification of system safety states, resource matrices, and safe sequence determination.",
        badge="Resource Allocation"
    )

    scenario_type = st.radio(
        "Select Resource Scenario",
        ["Textbook System (5 Processes, 3 Multi-Instance Resources)", "Banking Multi-Account (2 Transactions, 2 Accounts)"],
        horizontal=True
    )

    if scenario_type.startswith("Textbook"):
        # Initial matrices
        total_res = [10, 5, 7]
        max_demand = {
            "P0": [7, 5, 3],
            "P1": [3, 2, 2],
            "P2": [9, 0, 2],
            "P3": [2, 2, 2],
            "P4": [4, 3, 3]
        }
        allocation = {
            "P0": [0, 1, 0],
            "P1": [2, 0, 0],
            "P2": [3, 0, 2],
            "P3": [2, 1, 1],
            "P4": [0, 0, 2]
        }
        
        banker = Banker(total_res, max_demand, allocation)
        safe, seq = banker.is_safe()
        avail = banker.available()

        # Display System Matrix
        st.markdown("#### System Resource Matrices")
        
        # Build combined table
        rows = []
        for p in sorted(max_demand.keys()):
            rows.append({
                "Process": p,
                "Alloc R0": allocation[p][0], "Alloc R1": allocation[p][1], "Alloc R2": allocation[p][2],
                "Max R0": max_demand[p][0], "Max R1": max_demand[p][1], "Max R2": max_demand[p][2],
                "Need R0": banker.need(p)[0], "Need R1": banker.need(p)[1], "Need R2": banker.need(p)[2],
            })
        df_matrix = pd.DataFrame(rows).set_index("Process")
        st.dataframe(df_matrix, width='stretch')

        m1, m2, m3 = st.columns(3)
        m1.metric("Total System Resources", f"R0: {total_res[0]}, R1: {total_res[1]}, R2: {total_res[2]}")
        m2.metric("Available Vector", f"[{avail[0]}, {avail[1]}, {avail[2]}]", "Currently unallocated")
        m3.metric("System State", "SAFE" if safe else "UNSAFE", f"Sequence: {' -> '.join(seq) if safe else 'None'}")

        st.markdown("---")
        st.markdown("#### Interactive Resource Request Test")
        st.write("Submit a vector request for a process and test Banker's admittance check:")

        c1, c2, c3, c4 = st.columns(4)
        proc = c1.selectbox("Process", sorted(max_demand.keys()), index=1)
        r0 = c2.number_input("Request R0", min_value=0, max_value=10, value=1)
        r1 = c3.number_input("Request R1", min_value=0, max_value=10, value=0)
        r2 = c4.number_input("Request R2", min_value=0, max_value=10, value=2)

        if st.button("Submit Resource Request to Banker"):
            granted, reason = banker.request(proc, [int(r0), int(r1), int(r2)])
            if granted:
                st.success(f"**GRANTED**: Request was accepted. System maintains safety sequence: `{reason}`")
                st.write(f"Updated Available: `{banker.available()}`")
            else:
                st.error(f"**DENIED**: {reason}. The request was rejected to prevent entering an unsafe state.")

    else:
        st.markdown("#### Banking Case (Two Transfers Competing for Locks)")
        st.markdown("""
        In account transfers, locks on bank accounts act as single-instance resources (ACC_A and ACC_B).
        Here, **T1** already holds ACC_A and both **T1** and **T2** will eventually need ACC_A and ACC_B.
        """)

        # Banking scenario
        total_b = [1, 1]
        max_b = {"T1": [1, 1], "T2": [1, 1]}
        alloc_b = {"T1": [1, 0], "T2": [0, 0]}

        banker_b = Banker(total_b, max_b, alloc_b)
        avail_b = banker_b.available()

        st.write(f"**Active Allocation**: T1 holds ACC_A (`[1, 0]`), T2 holds nothing (`[0, 0]`). Available: `{avail_b}` (ACC_B is free).")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Test Case 1: T2 Requests ACC_B**")
            st.caption("If granted, T2 holds ACC_B while T1 holds ACC_A. Neither can finish without the other!")
            if st.button("T2 requests ACC_B ([0, 1])"):
                ok, why = banker_b.request("T2", [0, 1])
                if ok:
                    st.success(f"GRANTED: {why}")
                else:
                    st.error(f"DENIED: {why}. Banker prevents deadlock formation!")

        with col_b:
            st.markdown("**Test Case 2: T1 Requests ACC_B**")
            st.caption("If granted, T1 holds both accounts, finishes execution, and frees all resources.")
            if st.button("T1 requests ACC_B ([0, 1])"):
                ok, why = banker_b.request("T1", [0, 1])
                if ok:
                    st.success(f"GRANTED: {why}. T1 can safely execute and release resources for T2.")
                else:
                    st.error(f"DENIED: {why}")
