"""
Page 8: DBMS Security & Recovery
Demonstrates the database security and recovery features from dbms.py:
- Authentication, PBKDF2 hashing, Lockout
- Role-based access control (RBAC) & ownership
- Transaction limits & idempotency
- Append-only hash-chained audit log & tamper verification
- Write-Ahead Logging (WAL), Checkpointing, Crash recovery (redo/undo)
- Backup & Point-in-time restore
"""
import os, tempfile, shutil
import pandas as pd
import streamlit as st
from dbms import Bank, WalStore, AuthError, Forbidden
import pg_store
from ui.styles import render_header, render_metric

def get_demo_bank():
    """Returns or creates a persistent demo Bank in session state."""
    if "demo_bank" not in st.session_state:
        bank_dir = tempfile.mkdtemp(prefix="safeledger_ui_demo_")
        b = Bank(bank_dir, n_accounts=20, sync=True)
        # Pre-seed users
        b.users.add("alice", "pass-alice", "customer", owns=[1, 2])
        b.users.add("bob", "pass-bob", "customer", owns=[3, 4])
        b.users.add("teller", "pass-teller", "teller")
        b.users.add("auditor", "pass-auditor", "auditor")
        b.users.add("admin", "pass-admin", "admin")
        st.session_state["demo_bank"] = b
        st.session_state["demo_bank_dir"] = bank_dir
    return st.session_state["demo_bank"]

def render_page(pred, model_path):
    render_header(
        "DBMS Security, Integrity & Durability Lab",
        "Demonstrates ACID crash recovery, Write-Ahead Logging (WAL), RBAC security, PBKDF2 authentication, and tamper-evident audit chains.",
        badge="DBMS Engine"
    )

    b = get_demo_bank()

    t_sec, t_rec, t_audit = st.tabs(["Security & Access Control (RBAC)", "WAL Durability & Crash Recovery", "Tamper-Evident Audit Hash Chain"])

    # ---------------- TAB 1: SECURITY & RBAC ----------------
    with t_sec:
        st.markdown("#### Authentication & Cryptographic Credential Storage")
        st.write("""
        Passwords are never stored in plaintext. They are salted with 16 random bytes and hashed using 
        **PBKDF2-HMAC-SHA256 (100,000 iterations)**. Session tokens are digitally signed with HMAC-SHA256.
        """)

        col_cred1, col_cred2 = st.columns([1, 1])
        with col_cred1:
            inspect_user = st.selectbox("Inspect User Account", ["alice", "bob", "teller", "auditor", "admin"])
            salt, pwhash = b.users.credential(inspect_user)
            u_info = b.users.get(inspect_user)
            
            st.code(f"""
User: {inspect_user}
Role: {u_info['role']}
Owned Accounts: {sorted(list(u_info['owns'])) if u_info['owns'] else 'None (All perms apply)'}
Salt (hex): {salt.hex()[:32]}...
PBKDF2 Hash (hex): {pwhash.hex()[:48]}...
Iterations: {b.users.iters:,}
            """, language="text")

        with col_cred2:
            st.markdown("**Test Login & Lockout Protection**")
            test_pw = st.text_input("Enter Password to Test Authentication", type="password", key="login_test_pw")
            if st.button("Authenticate User"):
                try:
                    token = b.login(inspect_user, test_pw)
                    st.success(f"Authentication Successful! Signed Token Generated:\n`{token[:35]}...`")
                except AuthError as e:
                    st.error(f"Authentication Failed: {e}")
            st.caption("Protection: 5 consecutive invalid attempts trigger a temporary account lockout.")

        st.markdown("---")
        st.markdown("#### Role-Based Access Control (RBAC) Enforcement")
        st.write("Current Role Permissions Matrix:")
        rbac_rows = []
        for role_name, perms in b.roles.items():
            rbac_rows.append({"Role": role_name, "Assigned Permissions": ", ".join(sorted(perms))})
        st.dataframe(pd.DataFrame(rbac_rows), width='stretch', hide_index=True)

    # ---------------- TAB 2: RECOVERY & WAL ----------------
    with t_rec:
        st.markdown("#### Write-Ahead Logging (WAL) & ARIES Crash Recovery")
        st.write("""
        Durability is enforced via the Write-Ahead rule: log records (`BEGIN`, `UPD` with before/after images, `COMMIT`, `ABORT`) 
        are forced to disk using `os.fsync()` before memory state is updated. 
        Recovery performs: **Analysis Pass**, **Redo Pass (Repeating History)**, and **Undo Pass (Rolling back active losers)**.
        """)

        # Execute transfers through the store to build a log
        c_act1, c_act2, c_act3 = st.columns(3)
        with c_act1:
            if st.button("Execute Sample Transfer (LSN Advance)"):
                try:
                    token = b.login("teller", "pass-teller")
                    res = b.transfer(token, 1, 2, 50)
                    st.success(f"Transfer executed: LSN is now {b.store.lsn}")
                except Exception as e:
                    st.error(str(e))

        with c_act2:
            if st.button("Create Checkpoint (Snapshot)"):
                ckpt_lsn = b.store.checkpoint()
                st.success(f"Checkpoint flushed to disk at LSN {ckpt_lsn}")

        with c_act3:
            if st.button("Simulate System Crash (Dirty Pages Steal)"):
                # Simulate crash during active uncommitted transaction 9999
                b.store.simulate_crash(9999, [(1, -500), (2, 500)], steal=True)
                st.warning("SYSTEM CRASH SIMULATED! Memory balances erased. Dirty half-done writes forced to disk.")
                st.session_state["crashed"] = True

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        
        status_crashed = st.session_state.get("crashed", False)
        if status_crashed:
            st.error("Store Status: CRASHED (In-Memory balances = None). Database is currently down.")
            if st.button("Initiate Crash Recovery Routine", type="primary"):
                report = b.store.recover()
                st.session_state["crashed"] = False
                st.session_state["last_recovery_report"] = report
                st.success("Crash recovery routine completed successfully!")
                st.rerun()

        if "last_recovery_report" in st.session_state:
            rep = st.session_state["last_recovery_report"]
            st.markdown("##### Recovery Diagnostic Report")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Log Records Analyzed", f"{rep['log_records']}")
            r2.metric("Redone Records", f"{rep['redone']}")
            r3.metric("Undone Records (Losers)", f"{rep['undone']}")
            r4.metric("Torn Tail Detected", "Yes (Truncated)" if rep['torn_tail_removed'] else "No (Clean)")
            st.write(f"Rolled back loser transactions: `{rep['rolled_back_txns']}`")
            st.write(f"Recovery Execution Time: `{rep['seconds']} seconds`")

        st.markdown("---")
        st.markdown("#### Point-in-Time Recovery (PITR) & Backups")
        bk_col1, bk_col2 = st.columns(2)
        with bk_col1:
            if st.button("Create Valid System Backup"):
                backup_dir = tempfile.mkdtemp(prefix="safeledger_backup_")
                b.store.backup(backup_dir)
                st.session_state["last_backup_dir"] = backup_dir
                st.success(f"Backup manifest and SHA256 checksums written to:\n`{backup_dir}`")

        with bk_col2:
            if "last_backup_dir" in st.session_state:
                bk_dir = st.session_state["last_backup_dir"]
                st.write(f"Active Backup Ready: `{os.path.basename(bk_dir)}`")
                if st.button("Restore from Backup to New Store"):
                    restored_dir = tempfile.mkdtemp(prefix="safeledger_restored_")
                    rst = WalStore.restore(bk_dir, restored_dir, sync=False)
                    st.success(f"Restored successfully! Restored initial total: ${rst.total():,} across {rst.committed} txns.")

    # ---------------- TAB 3: AUDIT LOG HASH CHAIN ----------------
    with t_audit:
        st.markdown("#### Append-Only Tamper-Evident Audit Hash Chain")
        st.write("""
        Every security-sensitive event (login, transfer, denied action, admin command) is recorded in a cryptographic 
        hash chain. Each entry includes: `seq`, `ts`, `user`, `action`, `detail`, `result`, and `prev_hash`.
        Any unauthorized alteration or deletion in historical entries invalidates the entire subsequent chain.
        """)

        entries = b.audit.entries()
        st.markdown(f"**Total Audit Entries:** `{len(entries)}`")

        col_v1, col_v2 = st.columns(2)
        with col_v1:
            if st.button("Verify Audit Chain Integrity"):
                valid, bad_seq = b.audit.verify()
                if valid:
                    st.success("AUDIT INTEGRITY VERIFIED: All SHA256 hash chains match perfectly.")
                else:
                    st.error(f"CORRUPTION DETECTED: Chain broken at sequence #{bad_seq}!")

        with col_v2:
            if st.button("Simulate Tampering (Malicious DB Modification)"):
                if len(entries) >= 2:
                    b.audit._tamper(min(len(entries), 2), result="MODIFIED_BY_ATTACKER")
                    st.warning(f"Tampered with record #2 behind the system's back. Now run verification!")
                else:
                    st.info("Execute a few actions first to generate audit log records.")

        if entries:
            # Show recent entries in table
            st.markdown("##### Recent Audit Log Entries")
            df_audit = pd.DataFrame(entries[-15:])
            display_cols = ["seq", "user", "action", "detail", "result", "prev", "hash"]
            avail_cols = [c for c in display_cols if c in df_audit.columns]
            st.dataframe(df_audit[avail_cols], width='stretch', hide_index=True)
