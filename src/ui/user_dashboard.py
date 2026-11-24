"""
User Dashboard (Customer Portal)
Clean, minimalist banking SaaS interface for customer accounts, transfers,
transaction history, security and profile.
"""
import time
import pandas as pd
import streamlit as st
from ui.styles import render_header, render_metric
from ui.auth import get_shared_bank, logout_user

def mask_account(acct_id):
    """Masks account ID for customer view (e.g. ACC-••02)."""
    return f"ACC-••{acct_id:02d}"

def render_user_dashboard(user):
    b = get_shared_bank()
    username = user["username"]
    owns = sorted(list(user["owns"]))

    # Sidebar Navigation for User
    st.sidebar.markdown(f"""
    <div class="user-session-card">
        <div class="user-session-name">{username.capitalize()}</div>
        <div class="user-session-role">Role: {user['role']}</div>
    </div>
    """, unsafe_allow_html=True)

    user_pages = [
        "Overview",
        "My Accounts",
        "Transfer Money",
        "Transaction History",
        "Security",
        "My Profile"
    ]
    
    selected_page = st.sidebar.radio("Navigation", user_pages, label_visibility="collapsed")
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Log Out", key="user_logout_btn"):
        logout_user()

    # Calculate Total Balance across owned accounts
    total_balance = sum(b.store.balances.get(aid, 0) for aid in owns) if b.store.balances else 0

    # ---------------- 1. OVERVIEW ----------------
    if selected_page == "Overview":
        render_header(
            f"Welcome back, {username.capitalize()}",
            "Here is a summary of your accounts, balance liquidity, and recent activity.",
            badge="Customer Banking Portal"
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            render_metric("Total Liquid Balance", f"${total_balance:,.2f}", f"Across {len(owns)} authorized accounts", status="blue")
        with c2:
            render_metric("Active Accounts", f"{len(owns)}", "Checking & Savings", status="success")
        with c3:
            render_metric("Account Security", "Protected", "PBKDF2-HMAC-SHA256 & WAL Durability", status="success")

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

        col_left, col_right = st.columns([1.2, 1])
        with col_left:
            st.markdown("#### Primary Accounts")
            if owns and b.store.balances:
                acct_data = []
                for aid in owns:
                    bal = b.store.balances.get(aid, 0)
                    acct_data.append({
                        "Account": mask_account(aid),
                        "Type": "Standard Checking" if aid % 2 == 1 else "Interest Savings",
                        "Available Balance": f"${bal:,.2f}",
                        "Status": "Active"
                    })
                st.dataframe(pd.DataFrame(acct_data), width='stretch', hide_index=True)
            else:
                st.info("No authorized accounts currently assigned to this profile.")

        with col_right:
            st.markdown("#### Recent Activity")
            all_entries = b.audit.entries()
            my_entries = [e for e in all_entries if e["user"] == username][-5:]
            if my_entries:
                df_act = pd.DataFrame(my_entries)
                display_cols = ["ts", "action", "detail", "result"]
                avail_cols = [c for c in display_cols if c in df_act.columns]
                st.dataframe(df_act[avail_cols], width='stretch', hide_index=True)
            else:
                st.caption("No recent transactions recorded.")

    # ---------------- 2. MY ACCOUNTS ----------------
    elif selected_page == "My Accounts":
        render_header(
            "My Bank Accounts",
            "Review your authorized account balances, account numbers, and status.",
            badge="Account Portfolio"
        )

        if not owns:
            st.info("No accounts are registered to your profile. Please contact customer support.")
            return

        rows = []
        for aid in owns:
            bal = b.store.balances.get(aid, 0) if b.store.balances else 0
            rows.append({
                "Account Identifier": mask_account(aid),
                "Category": "Checking" if aid % 2 == 1 else "Savings",
                "Currency": "USD ($)",
                "Available Balance": f"${bal:,.2f}",
                "Lock Status": "Unlocked / Normal",
                "Internal Index": aid
            })
        st.dataframe(pd.DataFrame(rows)[["Account Identifier", "Category", "Currency", "Available Balance", "Lock Status"]], 
                     width='stretch', hide_index=True)

    # ---------------- 3. TRANSFER MONEY ----------------
    elif selected_page == "Transfer Money":
        render_header(
            "Transfer Funds",
            "Initiate a secure transfer between accounts backed by concurrency control and write-ahead logging.",
            badge="Payment Gateway"
        )

        if not owns:
            st.error("You do not own any accounts to transfer from.")
            return

        col1, col2 = st.columns(2)
        with col1:
            src_acct = st.selectbox(
                "From Account (Source)", 
                owns, 
                format_func=lambda a: f"{mask_account(a)} — Balance: ${b.store.balances.get(a, 0):,}"
            )
            dst_acct = st.number_input(
                "To Account ID (Destination)", 
                min_value=0, 
                max_value=b.n_accounts - 1, 
                value=2 if src_acct != 2 else 3,
                help="Destination bank account identifier"
            )
        with col2:
            amt = st.number_input("Transfer Amount ($ USD)", min_value=1, max_value=50_000, value=50, step=10)
            desc = st.text_input("Payment Description (Optional)", value="Invoice payment / Personal transfer")

        # Confirmation workflow
        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        confirmed = st.checkbox("I confirm that the destination and amount details are correct.")

        if st.button("Submit Secure Transfer", type="primary"):
            if not confirmed:
                st.warning("Please confirm the transaction details before submitting.")
                return

            if src_acct == dst_acct:
                st.error("Source and destination accounts must be different.")
                return

            current_bal = b.store.balances.get(src_acct, 0)
            if amt > current_bal:
                st.error(f"Insufficient funds: Your account holds ${current_bal:,}, but you requested ${amt:,}.")
                return

            # Execute real backend transfer
            with st.spinner("Authorizing through admission control, lock manager, and WAL..."):
                t0 = time.time()
                res = b.transfer(user["token"], int(src_acct), int(dst_acct), int(amt))
                dur = round((time.time() - t0) * 1000, 1)

            if res.get("ok"):
                st.success(f"**Transfer Successful!** Transferred ${amt:,} to Account {dst_acct}. Latency: {dur} ms.")
                st.caption(f"Transaction Reference: TXN-{res.get('tid'):05d} | Status: {res.get('status')}")
                st.rerun()
            else:
                st.error(f"**Transfer Rejected**: {res.get('status')}")

    # ---------------- 4. TRANSACTION HISTORY ----------------
    elif selected_page == "Transaction History":
        render_header(
            "Transaction History",
            "Audited ledger history of all payments, transfers, and security events for your accounts.",
            badge="Ledger History"
        )

        all_entries = b.audit.entries()
        my_history = [e for e in all_entries if e["user"] == username]

        if not my_history:
            st.info("No transaction history found for your account.")
            return

        # Filtering controls
        col_f1, col_f2 = st.columns(2)
        action_filter = col_f1.selectbox("Filter by Action Type", ["All Actions"] + list(set(e["action"] for e in my_history)))
        search_query = col_f2.text_input("Search details", placeholder="Account or keyword...")

        filtered = my_history
        if action_filter != "All Actions":
            filtered = [e for e in filtered if e["action"] == action_filter]
        if search_query:
            filtered = [e for e in filtered if search_query.lower() in str(e).lower()]

        df_h = pd.DataFrame(filtered)
        if not df_h.empty:
            df_h["Reference"] = df_h["seq"].apply(lambda s: f"REF-{s:05d}")
            display_cols = ["Reference", "ts", "action", "detail", "result"]
            avail_cols = [c for c in display_cols if c in df_h.columns]
            st.dataframe(df_h[avail_cols], width='stretch', hide_index=True)
            st.caption(f"Displaying {len(df_h)} authenticated audit records.")
        else:
            st.caption("No matching records found.")

    # ---------------- 5. SECURITY ----------------
    elif selected_page == "Security":
        render_header(
            "Account Security & Protection",
            "Review authentication factors, credential encryption, and session security status.",
            badge="Security Center"
        )

        s1, s2, s3 = st.columns(3)
        with s1:
            render_metric("Password Hashing", "PBKDF2-SHA256", "100,000 Key Derivation Iterations", status="success")
        with s2:
            render_metric("Salt Protection", "16-Byte Cryptographic", "Cryptographically Random Salt", status="success")
        with s3:
            render_metric("Session Security", "HMAC Signed", "Time-to-Live Expiring Token", status="blue")

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
        st.markdown("#### Security Policies Enforced")
        sec_policies = [
            {"Policy": "Brute-Force Lockout", "Description": "Accounts automatically lock for 60 seconds after 5 consecutive failed login attempts."},
            {"Policy": "Ownership Validation", "Description": "All fund transfers require strict cryptographic ownership verification before lock acquisition."},
            {"Policy": "Per-Transaction Limit", "Description": "Transfers are capped at a maximum of $50,000 per individual transaction."},
            {"Policy": "Daily Aggregate Limit", "Description": "Total daily volume is capped at $200,000 per user."},
            {"Policy": "Immutable Audit Log", "Description": "Every action generates an append-only, SHA256 hash-chained audit record."}
        ]
        st.dataframe(pd.DataFrame(sec_policies), width='stretch', hide_index=True)

    # ---------------- 6. MY PROFILE ----------------
    elif selected_page == "My Profile":
        render_header(
            "Account Profile & Identity",
            "Review your verified user details and authorization roles.",
            badge="Identity & Roles"
        )

        profile_data = [
            {"Field": "Username", "Value": username},
            {"Field": "Authorized Role", "Value": user["role"].capitalize()},
            {"Field": "Owned Account IDs", "Value": ", ".join(mask_account(a) for a in owns) if owns else "None"},
            {"Field": "Authentication Type", "Value": "PBKDF2-HMAC-SHA256 with Per-User Salt"},
            {"Field": "Session Token", "Value": f"{user['token'][:24]}... (Digitally Signed)"}
        ]
        st.dataframe(pd.DataFrame(profile_data), width='stretch', hide_index=True)
