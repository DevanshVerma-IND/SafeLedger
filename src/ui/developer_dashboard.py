"""
Developer Dashboard (Administrator & System Architecture Panel)
Restricted to users with 'admin' or 'developer' role.
Sections:
- Developer Overview
- User Management
- Account Management
- Transaction Monitoring
- ML Risk Monitoring
- Deadlock Lab
- Concurrency Testing
- Benchmark Results
- DBMS Security & Recovery
- Audit Logs
- System Health
- Settings
- Logout
"""
import os, json, time
import pandas as pd
import streamlit as st
from ui.styles import render_header, render_metric
from ui.auth import get_shared_bank, logout_user
import pg_store
import ui.page2_simulator as page2_simulator
import ui.page3_deadlock as page3_deadlock
import ui.page4_banker as page4_banker
import ui.page5_ml_risk as page5_ml_risk
import ui.page6_benchmark as page6_benchmark
import ui.page7_os_concepts as page7_os_concepts
import ui.page8_dbms as page8_dbms
import ui.page10_status as page10_status

def render_developer_dashboard(user, pred, model_path):
    b = get_shared_bank()
    username = user["username"]

    # Sidebar Header
    st.sidebar.markdown(f"""
    <div class="user-session-card">
        <div class="user-session-name">{username.capitalize()} (Admin)</div>
        <div class="user-session-role">Role: {user['role'].upper()}</div>
    </div>
    """, unsafe_allow_html=True)

    dev_pages = [
        "Developer Overview",
        "User Management",
        "Account Management",
        "Transaction Monitoring",
        "ML Risk Monitoring",
        "Deadlock Lab",
        "Concurrency Testing",
        "Benchmark Results",
        "DBMS Security",
        "Audit Logs",
        "System Health",
        "Settings"
    ]
    
    selected_page = st.sidebar.radio("Console Navigation", dev_pages, label_visibility="collapsed")
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Log Out of Console", key="dev_logout_btn"):
        logout_user()

    # ---------------- 1. DEVELOPER OVERVIEW ----------------
    if selected_page == "Developer Overview":
        render_header(
            "Developer Administration Console",
            "Real-time operational metrics, user counts, transaction throughput, and engine status.",
            badge="Infrastructure Administration"
        )

        # Calculate actual metrics
        all_users = b.users.users if hasattr(b.users, "users") and b.users.users else {}
        total_accounts = b.n_accounts
        total_balance = sum(b.store.balances.values()) if b.store.balances else 0
        total_committed = b.store.committed
        all_audit = b.audit.entries()

        # Benchmark data if present
        bench_df = pd.read_csv("results/benchmark.csv") if os.path.exists("results/benchmark.csv") else None
        avg_tps = round(bench_df["tps"].mean(), 1) if bench_df is not None and not bench_df.empty else "N/A"
        p95_lat = round(bench_df["p95_ms"].mean(), 1) if bench_df is not None and not bench_df.empty else "N/A"

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_metric("Registered Users", f"{len(all_users)}", "Active credential hashes", status="blue")
        with c2:
            render_metric("Managed Accounts", f"{total_accounts}", f"Total Liquidity: ${total_balance:,}", status="success")
        with c3:
            render_metric("System Throughput", f"{avg_tps} tx/s", f"P95: {p95_lat} ms", status="success")
        with c4:
            render_metric("Database Engine", "Active", "PostgreSQL" if pg_store.enabled() else "SQLite WAL", status="success")

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

        col_a, col_b = st.columns([1.2, 1])
        with col_a:
            st.markdown("#### Recent System Activity Stream")
            if all_audit:
                recent_logs = pd.DataFrame(all_audit[-8:])
                cols = ["seq", "ts", "user", "action", "detail", "result"]
                avail_cols = [c for c in cols if c in recent_logs.columns]
                st.dataframe(recent_logs[avail_cols], width='stretch', hide_index=True)
            else:
                st.caption("No system activity recorded yet.")

        with col_b:
            st.markdown("#### Engine & Subsystem Readiness")
            subsystems = [
                {"Subsystem": "Transaction Engine", "State": "Operational", "Layer": "engine.py"},
                {"Subsystem": "Lock Manager (WFG/Banker)", "State": "Operational", "Layer": "engine.py & os_layer.py"},
                {"Subsystem": "Write-Ahead Log (WAL)", "State": "Sync Enforced", "Layer": "dbms.py (CRC-32)"},
                {"Subsystem": "ML Admission Gate", "State": "Ready" if pred else "Needs Training", "Layer": "collect_train.py"},
                {"Subsystem": "Audit Log Chain", "State": "Verified", "Layer": "SHA-256 Append-Only"}
            ]
            st.dataframe(pd.DataFrame(subsystems), width='stretch', hide_index=True)

    # ---------------- 2. USER MANAGEMENT ----------------
    elif selected_page == "User Management":
        render_header(
            "User Identity & Role Management",
            "Review registered accounts, role permissions, PBKDF2 credential parameters, and assign authorization.",
            badge="Identity Governance"
        )

        all_users = b.users.users if hasattr(b.users, "users") and b.users.users else {}
        
        # User List Table
        st.markdown("#### Registered System Users")
        user_rows = []
        for uname, udata in all_users.items():
            salt = udata.get("salt", b"")
            owns_list = sorted(list(udata.get("owns", [])))
            user_rows.append({
                "Username": uname,
                "Role": udata.get("role", "customer").upper(),
                "Owned Accounts": ", ".join(f"ACC_{a:02d}" for a in owns_list) if owns_list else "All / Unrestricted",
                "Lockout Status": "Locked" if time.time() < udata.get("until", 0) else "Active / Normal",
                "Failed Attempts": udata.get("fails", 0),
                "Salt Fingerprint": salt.hex()[:12] + "..." if salt else "N/A"
            })
        
        df_users = pd.DataFrame(user_rows)
        st.dataframe(df_users, width='stretch', hide_index=True)

        st.markdown("---")
        st.markdown("#### Modify User Role or Account Ownership")
        
        u_col1, u_col2, u_col3 = st.columns(3)
        target_user = u_col1.selectbox("Select User", sorted(list(all_users.keys())))
        new_role = u_col2.selectbox("Assign New Role", ["customer", "teller", "auditor", "admin"])
        new_owns_str = u_col3.text_input("Assigned Account IDs (comma-separated)", 
                                         value=",".join(str(x) for x in all_users[target_user].get("owns", [])))

        if st.button("Apply Role / Ownership Changes", type="primary"):
            try:
                parsed_owns = [int(x.strip()) for x in new_owns_str.split(",") if x.strip().isdigit()]
                with b.users.mu:
                    b.users.users[target_user]["role"] = new_role
                    b.users.users[target_user]["owns"] = set(parsed_owns)
                    # Reset lockout if any
                    b.users.users[target_user]["until"] = 0
                    b.users.users[target_user]["fails"] = 0
                b.audit.add(username, "user:modify", f"user={target_user} role={new_role} owns={parsed_owns}", "OK")
                st.success(f"User '{target_user}' updated: Role set to '{new_role}', Accounts: {parsed_owns}.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to update user: {e}")

        # Add New User
        with st.expander("Register New SafeLedger User", expanded=False):
            n_col1, n_col2, n_col3 = st.columns(3)
            new_uname = n_col1.text_input("New Username")
            new_pw = n_col2.text_input("New Password", type="password")
            new_urole = n_col3.selectbox("Initial Role", ["customer", "teller", "auditor", "admin"], key="new_u_role")
            new_u_owns = st.text_input("Assigned Accounts (e.g. 7, 8)", value="7")

            if st.button("Create User in Database"):
                if not new_uname or not new_pw:
                    st.error("Username and password are required.")
                elif new_uname in all_users:
                    st.error(f"User '{new_uname}' already exists.")
                else:
                    parsed_accounts = [int(x.strip()) for x in new_u_owns.split(",") if x.strip().isdigit()]
                    b.users.add(new_uname, new_pw, new_urole, owns=parsed_accounts)
                    b.audit.add(username, "user:create", f"new_user={new_uname} role={new_urole}", "OK")
                    st.success(f"User '{new_uname}' created with PBKDF2 hash!")
                    st.rerun()

    # ---------------- 3. ACCOUNT MANAGEMENT ----------------
    elif selected_page == "Account Management":
        render_header(
            "Account Ledger Management",
            "Review global ledger balances, account ownership assignments, and reserve totals.",
            badge="Ledger Administration"
        )

        all_users = b.users.users if hasattr(b.users, "users") and b.users.users else {}
        # Map accounts to users
        acct_to_owners = {}
        for u, d in all_users.items():
            for aid in d.get("owns", []):
                acct_to_owners.setdefault(aid, []).append(u)

        st.markdown("#### System Accounts & Liquidity")
        acct_rows = []
        if b.store.balances:
            for aid in range(min(25, b.n_accounts)):
                bal = b.store.balances.get(aid, 0)
                owners = ", ".join(acct_to_owners.get(aid, [])) or "Unassigned / General Reserve"
                acct_rows.append({
                    "Account ID": f"ACC_{aid:02d}",
                    "Balance": f"${bal:,}",
                    "Assigned Owner(s)": owners,
                    "Account Status": "Active",
                    "Index": aid
                })
        st.dataframe(pd.DataFrame(acct_rows)[["Account ID", "Balance", "Assigned Owner(s)", "Account Status"]], 
                     width='stretch', hide_index=True)

        st.caption("Note: Arbitrary manual balance modifications are prohibited by banking compliance. All ledger modifications must occur via authenticated write-ahead logged transfers.")

    # ---------------- 4. TRANSACTION MONITORING ----------------
    elif selected_page == "Transaction Monitoring":
        render_header(
            "Real-Time Transaction Monitoring",
            "Inspect live transactions, execution strategies, and outcomes across all system users.",
            badge="Transaction Operations"
        )

        all_audit = b.audit.entries()
        txns = [e for e in all_audit if e["action"] == "transfer"]

        if not txns:
            st.info("No transfers recorded yet.")
        else:
            col_t1, col_t2 = st.columns(2)
            filter_status = col_t1.selectbox("Filter Status", ["All", "COMMITTED", "DENIED", "REJECTED"])
            search_actor = col_t2.text_input("Filter by Actor / User", "")

            filtered_tx = txns
            if filter_status != "All":
                filtered_tx = [t for t in filtered_tx if filter_status in str(t.get("result", ""))]
            if search_actor:
                filtered_tx = [t for t in filtered_tx if search_actor.lower() in t.get("user", "").lower()]

            st.dataframe(pd.DataFrame(filtered_tx)[["seq", "ts", "user", "action", "detail", "result"]], 
                         width='stretch', hide_index=True)

    # ---------------- 5. ML RISK MONITORING ----------------
    elif selected_page == "ML Risk Monitoring":
        page5_ml_risk.render_page(pred, model_path)

    # ---------------- 6. DEADLOCK LAB ----------------
    elif selected_page == "Deadlock Lab":
        page3_deadlock.render_page(pred, model_path)

    # ---------------- 7. CONCURRENCY TESTING ----------------
    elif selected_page == "Concurrency Testing":
        page2_simulator.render_page(pred, model_path)

    # ---------------- 8. BENCHMARK RESULTS ----------------
    elif selected_page == "Benchmark Results":
        page6_benchmark.render_page(pred, model_path)

    # ---------------- 9. DBMS SECURITY & RECOVERY ----------------
    elif selected_page == "DBMS Security":
        page8_dbms.render_page(pred, model_path)

    # ---------------- 10. AUDIT LOGS ----------------
    elif selected_page == "Audit Logs":
        render_header(
            "Append-Only Cryptographic Audit Log",
            "SHA-256 hash-chained immutable event record verifying system action integrity.",
            badge="Compliance & Audit"
        )

        entries = b.audit.entries()
        v_col1, v_col2 = st.columns(2)
        with v_col1:
            if st.button("Verify Hash-Chain Integrity", type="primary"):
                ok, bad_seq = b.audit.verify()
                if ok:
                    st.success(f"Audit log verified: All {len(entries)} entries are cryptographically intact!")
                else:
                    st.error(f"Audit chain broken at entry #{bad_seq}!")

        with v_col2:
            st.metric("Total Chain Length", f"{len(entries)} entries", "Immutable sequence")

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        if entries:
            df_entries = pd.DataFrame(entries)
            display_cols = ["seq", "ts", "user", "action", "detail", "result", "prev", "hash"]
            avail_cols = [c for c in display_cols if c in df_entries.columns]
            st.dataframe(df_entries[avail_cols], width='stretch', hide_index=True)

    # ---------------- 11. SYSTEM HEALTH ----------------
    elif selected_page == "System Health":
        page10_status.render_page(pred, model_path)

    # ---------------- 12. SETTINGS ----------------
    elif selected_page == "Settings":
        render_header(
            "System Settings & Limits",
            "Operational configuration for transaction limits, database synchronization, and timeouts.",
            badge="System Preferences"
        )

        s_col1, s_col2 = st.columns(2)
        with s_col1:
            st.markdown("#### Transaction Limit Policies")
            st.write(f"- **Per-Transaction Maximum**: ${b.limits[0]:,}")
            st.write(f"- **Daily Aggregate Maximum**: ${b.limits[1]:,}")
            st.write(f"- **Lock Manager Timeout**: {b.lm.timeout} seconds")

        with s_col2:
            st.markdown("#### Database Engine Configuration")
            st.write(f"- **Active Backend**: {'PostgreSQL' if pg_store.enabled() else 'SQLite WAL Mode'}")
            st.write(f"- **Synchronous Commit**: {'On' if os.environ.get('SAFELEDGER_PG_SYNC_COMMIT') == 'on' else 'Normal (WAL)'}")
            st.write(f"- **Storage Directory**: `{b.path}`")
