"""
Page 9: Banking Transaction Demo
Interactive banking interface using the real Bank instance from dbms.py.
Supports account viewing, authenticated transfer execution, validation rules,
ownership restrictions, and transaction limits.
"""
import streamlit as st
import pandas as pd
from ui.page8_dbms import get_demo_bank
from dbms import AuthError, Forbidden
from ui.styles import render_header, render_metric

def render_page(pred, model_path):
    render_header(
        "Banking Transaction Service (Demo)",
        "End-user banking portal backed by real Bank transaction engine, enforcing RBAC, ownership, limits, and idempotency.",
        badge="Fintech Interface"
    )

    st.caption("Notice: Academic PBL simulation for demonstrating concurrency control and DBMS security. Not a real financial institution.")

    b = get_demo_bank()

    # User Selection & Authentication
    st.markdown("#### User Authentication & Role Context")
    u_col1, u_col2 = st.columns([1, 1])
    
    with u_col1:
        selected_user = st.selectbox(
            "Select Demo Account Profile",
            ["alice", "bob", "teller", "auditor", "admin"],
            format_func=lambda u: {
                "alice": "Alice (Customer - Owns Accounts 1 & 2)",
                "bob": "Bob (Customer - Owns Accounts 3 & 4)",
                "teller": "Bank Teller (Staff - Can Transfer Any Account)",
                "auditor": "Auditor (Read-Only Compliance Access)",
                "admin": "System Administrator (Privileged Operations)"
            }[u]
        )
    
    with u_col2:
        default_pws = {
            "alice": "pass-alice",
            "bob": "pass-bob",
            "teller": "pass-teller",
            "auditor": "pass-auditor",
            "admin": "pass-admin"
        }
        pw = st.text_input("Enter Password", value=default_pws[selected_user], type="password")

    # Current Balances Overview
    st.markdown("#### Live Account Ledger Balances")
    user_info = b.users.get(selected_user)
    owned_accounts = user_info["owns"] if user_info else set()

    # Display first 10 accounts
    acct_rows = []
    if b.store.balances:
        for aid in range(min(12, b.n_accounts)):
            bal = b.store.balances.get(aid, 0)
            is_owned = aid in owned_accounts
            acct_rows.append({
                "Account ID": f"ACC_{aid:02d}",
                "Balance": f"${bal:,}",
                "Ownership Status": "Owned by Current User" if is_owned else "External / Other Customer",
                "Raw ID": aid
            })
    df_accts = pd.DataFrame(acct_rows)
    st.dataframe(df_accts[["Account ID", "Balance", "Ownership Status"]], width='stretch', hide_index=True)

    st.markdown("---")
    st.markdown("#### Initiate Account Transfer")

    col_tx1, col_tx2, col_tx3 = st.columns(3)
    src_acct = col_tx1.number_input("Source Account ID", min_value=0, max_value=b.n_accounts - 1, value=1)
    dst_acct = col_tx2.number_input("Destination Account ID", min_value=0, max_value=b.n_accounts - 1, value=3)
    amount = col_tx3.number_input("Transfer Amount ($)", min_value=1, max_value=100_000, value=50, step=10)

    col_opt1, col_opt2 = st.columns(2)
    idem_key = col_opt1.text_input("Idempotency Key (Optional)", value="", help="Unique client transaction identifier to prevent duplicate charges")
    prio = col_opt2.selectbox("Transaction Priority", [1, 2, 3, 4, 5], index=1, format_func=lambda p: f"Priority {p} ({'Urgent' if p==1 else 'Normal' if p==2 else 'Low'})")

    if st.button("Authorize & Execute Transfer", type="primary"):
        # 1. Authenticate user
        try:
            token = b.login(selected_user, pw)
        except AuthError as e:
            st.error(f"Authentication Failed: {e}")
            return

        # 2. Execute transfer via real Bank
        key = idem_key.strip() if idem_key.strip() else None
        with st.spinner("Processing through admission control, lock manager, and WAL..."):
            res = b.transfer(token, int(src_acct), int(dst_acct), int(amount), idem=key, prio=int(prio))

        if res.get("ok"):
            st.success(f"**TRANSFER COMMITTED**: Successfully moved ${amount} from Account {src_acct} to Account {dst_acct}.")
            st.write(f"System Status: `{res.get('status')}`")
            st.rerun()
        else:
            st.error(f"**TRANSFER REJECTED**: {res.get('status')}")
            st.info("""
            **Common Rejection Rules Enforced by Backend:**
            - **Ownership Check**: Customers can only initiate transfers from accounts they legally own.
            - **Role Permissions**: Auditors cannot initiate transfers (`transfer:any` or `transfer:own` required).
            - **Idempotency Protection**: Re-submitting the same key ignores duplicate requests.
            - **Transaction Limits**: Transfers exceeding $50,000 per transaction are rejected.
            - **Insufficient Funds**: Transfers cannot reduce account balance below zero.
            """)

    # Transaction audit history for this session
    st.markdown("---")
    st.markdown("#### Bank Ledger Audit Log (Live Tail)")
    entries = b.audit.entries()
    if entries:
        recent = [e for e in entries if e["action"] in ("transfer", "login")][-10:]
        df_hist = pd.DataFrame(recent)
        avail = [c for c in ["seq", "ts", "user", "action", "detail", "result"] if c in df_hist.columns]
        st.dataframe(df_hist[avail], width='stretch', hide_index=True)
