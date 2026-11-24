"""
SafeLedger: Concurrency-Safe Banking Transaction Engine & AI Admission Gating
Clean, high-usability Streamlit Dashboard.

STRICT CONSTRAINTS ADHERED TO:
- Zero alterations to original backend modules (engine.py, dbms.py, os_layer.py, collect_train.py, benchmark.py).
- Imports only existing classes, functions, and signatures:
  - From engine: FEATURES, Predictor, HttpPredictor, make_specs, run_load, deadlock_scenario
  - From dbms: Bank, WalStore, AuthError, Forbidden, ROLES
  - From os_layer: Banker, admit
- Clean auto-detection of model and benchmark artifacts (results/ vs root).
- Role-gated authentication (User vs Developer) with PBKDF2 salting, session audit logging,
  and 4-digit PIN verification for customer transfers.
- Streamlined 4-tab Developer view.
"""

import os
import re
import sys
import json
import time
import tempfile
import pandas as pd
import numpy as np
import streamlit as st

# Configure page
st.set_page_config(
    page_title="SafeLedger",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 1. BACKEND IMPORTS (STRICT CONSTRAINTS)
# -----------------------------------------------------------------------------
from engine import (
    FEATURES,
    Predictor,
    HttpPredictor,
    make_specs,
    run_load,
    deadlock_scenario
)
from dbms import (
    Bank,
    WalStore,
    AuthError,
    Forbidden,
    ROLES
)
from os_layer import (
    Banker,
    admit
)

# -----------------------------------------------------------------------------
# 2. ARTIFACT PATH RESOLUTION (AUTO-DETECT RESULTS/ VS ROOT)
# -----------------------------------------------------------------------------
def resolve_path(filename):
    """Checks results/<filename> first, then root <filename>."""
    p_results = os.path.join("results", filename)
    if os.path.exists(p_results):
        return p_results
    if os.path.exists(filename):
        return filename
    return None

MODEL_PATH = resolve_path("model.joblib")
METRICS_PATH = resolve_path("model_metrics.json")
BENCHMARK_PATH = resolve_path("benchmark.csv")
SWEEP_PATH = resolve_path("sweep.csv")

# Load model if available
@st.cache_resource
def load_predictor(path):
    if path and os.path.exists(path):
        try:
            return Predictor(path)
        except Exception:
            return None
    return None

pred = load_predictor(MODEL_PATH)

# Load metrics if available
def load_metrics(path):
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

metrics_data = load_metrics(METRICS_PATH)

# -----------------------------------------------------------------------------
# 3. GLOBAL BANK SESSION MANAGEMENT & SEED_DATA_UPDATED.SQL AUTHENTICATION
# -----------------------------------------------------------------------------
SEED_SQL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql", "seed_data_updated.sql")

@st.cache_data
def load_seed_accounts(sql_path):
    """Parses predefined accounts, passwords, balances, and PINs from sql/seed_data_updated.sql."""
    accounts = {}
    ordered = []
    if not sql_path or not os.path.exists(sql_path):
        return accounts, ordered
    with open(sql_path, "r", encoding="utf-8") as f:
        text = f.read()
    blocks = re.findall(r"INSERT INTO public\.accounts VALUES\s*(.*?);", text, re.S)
    for block in blocks:
        for m in re.finditer(r"\((\d+),\s*'([^']*)',\s*'([^']*)',\s*(\d+),\s*'([^']*)',\s*(\d+)\)", block):
            rec = {
                "account_id": int(m.group(1)),
                "holder_name": m.group(2),
                "account_type": m.group(3),
                "balance": int(m.group(4)),
                "password": m.group(5),
                "pin": m.group(6),
            }
            accounts[rec["holder_name"].lower()] = rec
            ordered.append(rec)
    return accounts, ordered

SEED_ACCOUNTS, SEED_ORDERED = load_seed_accounts(SEED_SQL_PATH)

ADMIN_ACCOUNT = {"username": "admin", "password": "pw-x", "role": "admin"}

def ensure_seed_user_registered(b, seed_rec):
    """Registers a predefined user from seed_data_updated.sql into UserStore on first login attempt."""
    uname = seed_rec["holder_name"]
    if hasattr(b.users, "users") and isinstance(b.users.users, dict):
        if uname not in b.users.users:
            b.users.add(uname, seed_rec["password"], "customer", owns=[seed_rec["account_id"]])
    elif b.users.get(uname) is None:
        b.users.add(uname, seed_rec["password"], "customer", owns=[seed_rec["account_id"]])

def get_bank():
    """Initializes and caches Bank instance in session state with accounts from seed_data_updated.sql."""
    n_accts = max((r["account_id"] for r in SEED_ORDERED), default=29) + 1
    if "bank" not in st.session_state or getattr(st.session_state.bank, "n_accounts", 0) != n_accts:
        bank_dir = os.path.join(tempfile.gettempdir(), "safeledger_streamlit_bank")
        os.makedirs(bank_dir, exist_ok=True)
        b = Bank(bank_dir, predictor=pred, n_accounts=n_accts, sync=True)
        if SEED_ORDERED:
            bal_map = {i: 10_000 for i in range(n_accts)}
            for r in SEED_ORDERED:
                bal_map[r["account_id"]] = r["balance"]
            b.store.balances = dict(bal_map)
            b.store.initial_total = sum(bal_map.values())
            for p in (b.store.base, b.store.snap):
                with open(p, "w", encoding="utf-8") as fp:
                    json.dump({"lsn": 0, "balances": bal_map}, fp)
        # Register ONLY the single administrator account; users are authenticated strictly from seed_data_updated.sql
        b.users.add(ADMIN_ACCOUNT["username"], ADMIN_ACCOUNT["password"], ADMIN_ACCOUNT["role"], owns=[])
        st.session_state.bank = b
        st.session_state.bank_dir = bank_dir
    return st.session_state.bank

bank = get_bank()

# -----------------------------------------------------------------------------
# 4. CUSTOM MINIMALIST CSS STYLING
# -----------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
}

/* App Background: Clean White */
.stApp {
    background-color: #FFFFFF !important;
    color: #17191C !important;
}

/* Sidebar Styling: Subtle Off-White with border */
[data-testid="stSidebar"], [data-testid="stSidebarContent"] {
    background-color: #F8F9FA !important;
    border-right: 1px solid #E9ECEF !important;
}

/* Headings and Section Titles */
h1, h2, h3, h4, h5, h6 {
    color: #17191C !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

/* Custom Metric Card */
.sl-metric-card {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.sl-metric-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6B7280;
    margin-bottom: 0.25rem;
}
.sl-metric-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #111827;
    line-height: 1.2;
}
.sl-metric-sub {
    font-size: 0.75rem;
    color: #9CA3AF;
    margin-top: 0.25rem;
}

/* Architecture banner */
.arch-banner {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 0.85rem 1.25rem;
    margin-bottom: 1.25rem;
    gap: 0.5rem;
    overflow-x: auto;
}
.arch-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    min-width: 130px;
}
.arch-step-num {
    font-size: 0.7rem;
    font-weight: 700;
    color: #2563EB;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.arch-step-name {
    font-size: 0.85rem;
    font-weight: 600;
    color: #1E293B;
}
.arch-arrow {
    font-size: 1.1rem;
    color: #94A3B8;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. AUTHENTICATION & LOGIN SCREEN
# -----------------------------------------------------------------------------
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

def do_logout():
    if st.session_state.auth_user:
        uname = st.session_state.auth_user["username"]
        bank.audit.add(uname, "logout", "", "OK")
    st.session_state.auth_user = None
    st.session_state.auth_token = None
    st.rerun()

# If not authenticated, show Centered Login Page
if st.session_state.auth_user is None:
    _, col_login, _ = st.columns([1, 1.4, 1])
    with col_login:
        st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### SafeLedger Sign In")
            st.caption("Secure AI Banking Transaction Engine with Concurrency & Durability Protection")
            
            # Role selection tab / radio
            selected_portal = st.radio(
                "Select Access Portal",
                ["User Banking Portal", "Developer Administration Console"],
                horizontal=True
            )
            is_dev_portal = "Developer" in selected_portal

            if st.session_state.get("_last_portal") != is_dev_portal:
                st.session_state._last_portal = is_dev_portal
                if is_dev_portal:
                    st.session_state.login_u = ADMIN_ACCOUNT["username"]
                    st.session_state.login_p = ADMIN_ACCOUNT["password"]
                else:
                    sample_cust = next((r for r in SEED_ORDERED if r["account_type"] == "customer"), SEED_ORDERED[0] if SEED_ORDERED else None)
                    st.session_state.login_u = sample_cust["holder_name"] if sample_cust else ""
                    st.session_state.login_p = sample_cust["password"] if sample_cust else ""

            # Quick-Fill helper
            with st.expander("Quick-Fill Demo Credentials", expanded=True):
                if not is_dev_portal:
                    if not SEED_ORDERED:
                        st.error("Seed file sql/seed_data_updated.sql not found or contains no accounts.")
                    else:
                        st.caption(f"Loaded {len(SEED_ORDERED)} predefined user accounts from sql/seed_data_updated.sql. Select a sample or type any account holder name:")
                        sample_picks = [
                            next((r for r in SEED_ORDERED if r["account_id"] == 8), SEED_ORDERED[0]),
                            next((r for r in SEED_ORDERED if r["account_id"] == 100), SEED_ORDERED[min(1, len(SEED_ORDERED) - 1)]),
                            next((r for r in SEED_ORDERED if r["account_id"] == 0), SEED_ORDERED[0]),
                        ]
                        qcols = st.columns(len(sample_picks))
                        for idx, rec in enumerate(sample_picks):
                            if qcols[idx].button(f"{rec['holder_name']} (#{rec['account_id']})", key=f"q_seed_{rec['account_id']}"):
                                st.session_state.login_u = rec["holder_name"]
                                st.session_state.login_p = rec["password"]
                                st.rerun()
                else:
                    st.caption("Single administrator credential for the Developer Administration Console:")
                    if st.button("admin (Administrator)", key="q_admin"):
                        st.session_state.login_u = ADMIN_ACCOUNT["username"]
                        st.session_state.login_p = ADMIN_ACCOUNT["password"]
                        st.rerun()

            default_u = st.session_state.get("login_u", "")
            default_p = st.session_state.get("login_p", "")

            with st.form("login_form"):
                u_input = st.text_input("Username", value=default_u, key=f"u_in_{is_dev_portal}_{default_u}")
                p_input = st.text_input("Password", value=default_p, type="password", key=f"p_in_{is_dev_portal}_{default_u}")
                submitted = st.form_submit_button("Authenticate & Enter", width="stretch")

            if submitted:
                raw_u = u_input.strip()
                u_key = raw_u.lower()
                try:
                    if is_dev_portal:
                        # Single administrator login only
                        if u_key != ADMIN_ACCOUNT["username"]:
                            bank.audit.add(raw_u or "?", "login", "developer_console", "DENIED: administrator only")
                            st.error("Access Denied: Only the single administrator account ('admin') can log in to the Developer Administration Console.")
                        else:
                            token = bank.login(ADMIN_ACCOUNT["username"], p_input)
                            user_record = bank.users.get(ADMIN_ACCOUNT["username"])
                            st.session_state.auth_user = {
                                "username": ADMIN_ACCOUNT["username"],
                                "role": user_record["role"],
                                "owns": list(user_record["owns"]),
                                "token": token
                            }
                            st.session_state.auth_token = token
                            st.success("Authenticated successfully. Loading portal...")
                            st.rerun()
                    else:
                        # User portal: ONLY predefined users in sql/seed_data_updated.sql are permitted
                        seed_rec = SEED_ACCOUNTS.get(u_key)
                        if seed_rec is None:
                            # Run equal-work PBKDF2 timing & record failed attempt in audit log
                            bank.login("__unregistered__" if u_key == "admin" else (raw_u or "?"), p_input)
                        else:
                            ensure_seed_user_registered(bank, seed_rec)
                            login_name = seed_rec["holder_name"]
                            token = bank.login(login_name, p_input)
                            user_record = bank.users.get(login_name)
                            st.session_state.auth_user = {
                                "username": login_name,
                                "role": user_record["role"],
                                "account_type": seed_rec["account_type"],
                                "owns": list(user_record["owns"]),
                                "token": token
                            }
                            st.session_state.auth_token = token
                            st.success("Authenticated successfully. Loading portal...")
                            st.rerun()
                except AuthError as e:
                    st.error(f"Authentication Failed: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")

            st.markdown("---")
            st.caption("All logins are hashed via salted PBKDF2 (100,000 rounds) and verified against the tamper-evident audit log.")
    st.stop()

# -----------------------------------------------------------------------------
# 6. AUTHENTICATED STATE: SIDEBAR USER DETAILS & LOGOUT
# -----------------------------------------------------------------------------
curr_user = st.session_state.auth_user
st.sidebar.markdown(f"### SafeLedger")
st.sidebar.markdown(f"**Logged in as:** `{curr_user['username']}`  \n**Role:** `{curr_user['role'].upper()}`")
if curr_user.get("owns"):
    st.sidebar.markdown(f"**Owned Accounts:** `{curr_user['owns']}`")
if st.sidebar.button("Logout", width="stretch"):
    do_logout()
st.sidebar.markdown("---")

# -----------------------------------------------------------------------------
# 7. USER DASHBOARD (WHEN LOGGED IN AS CUSTOMER)
# -----------------------------------------------------------------------------
if curr_user["role"] == "customer":
    st.markdown(f"## Welcome back, {curr_user['username']}")
    st.caption("SafeLedger Retail Banking Portal — Real-time Concurrency & ACID Protected")

    # Top KPI Cards
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        with st.container(border=True):
            st.caption("PROFILE")
            acct_kind = curr_user.get("account_type", curr_user["role"])
            st.markdown(f"**{curr_user['username']}** ({acct_kind})")
            st.caption(f"Owned IDs: {curr_user['owns']}")
    with kpi2:
        with st.container(border=True):
            st.caption("TOTAL LIQUID BALANCE")
            tot_bal = sum(bank.store.balances.get(aid, 0) for aid in curr_user["owns"]) if bank.store.balances else 0
            st.markdown(f"### ${tot_bal:,.2f}")
            st.caption("Live from WalStore in-memory cache")
    with kpi3:
        with st.container(border=True):
            st.caption("BANK CONSERVATION")
            if bank.store.up and bank.store.balances is not None:
                vault_total = bank.store.total()
                is_conserved = vault_total == bank.store.initial_total
                status_text = "100% Conserved" if is_conserved else "Discrepancy"
                st.markdown(f"**{status_text}**")
                st.caption(f"Vault total: ${vault_total:,}")
            else:
                st.markdown("**Store Down**")
                st.caption("Database offline (recover via Developer Tab 4)")
    with kpi4:
        with st.container(border=True):
            st.caption("SESSION AUDIT COUNT")
            user_entries = [e for e in bank.audit.entries() if e.get("user") == curr_user["username"]]
            st.markdown(f"### {len(user_entries)}")
            st.caption("Recorded in append-only log")

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

    # SEND MONEY TRANSFER CARD
    col_xfer, col_telemetry = st.columns([1.2, 1])

    with col_xfer:
        with st.container(border=True):
            st.markdown("#### Send Money")
            st.caption("Executes transfer through Bank.transfer() with lock manager and write-ahead logging.")

            # From account dropdown: include owned accounts plus an unauthorized option to test RBAC
            bal_dict = bank.store.balances or {}
            owned_opts = [f"Account {aid} (Balance: ${bal_dict.get(aid, 0):,})" for aid in curr_user["owns"]]
            test_unauth_aid = 0 if 0 not in curr_user["owns"] else 1
            owned_opts.append(f"Account {test_unauth_aid} [UNAUTHORIZED - Test RBAC Denial]")
            
            src_selection = st.selectbox("From Account", owned_opts)
            if "UNAUTHORIZED" in src_selection:
                src_acct = test_unauth_aid
            else:
                src_acct = int(src_selection.split()[1])

            max_acct_id = bank.n_accounts - 1
            to_acct = st.number_input(f"To Account ID (0..{max_acct_id})", min_value=0, max_value=max_acct_id, value=8 if src_acct != 8 else 9)
            amount = st.number_input("Amount ($ USD)", min_value=-5000.0, max_value=50000.0, value=50.0, step=10.0,
                                     help="Allows negative or zero amounts to test explicit input validation triggers.")
            
            pin_input = st.text_input("4-Digit Security PIN", type="password", max_chars=4,
                                      help="Enter your 4-digit security PIN from sql/seed_data_updated.sql (e.g. 1234)")

            use_idem = st.checkbox("Include Idempotency Key (Test duplicate transfer protection)", value=False)
            idem_key = st.text_input("Idempotency Key", value="pay-ref-001") if use_idem else None

            submit_xfer = st.button("Authorize & Send Money", width="stretch", type="primary")

            if submit_xfer:
                # 1. 4-Digit PIN Validation Trigger
                seed_user = SEED_ACCOUNTS.get(curr_user["username"].lower(), {})
                correct_pin = seed_user.get("pin")
                if not pin_input or len(pin_input) != 4 or not pin_input.isdigit() or pin_input != correct_pin:
                    st.error("Transfer Blocked: Invalid 4-Digit Security PIN. Please enter your verified 4-digit PIN.")
                    bank.audit.add(curr_user["username"], "transfer", f"{src_acct}->{to_acct} {amount}", "DENIED: invalid 4-digit PIN")
                # 2. Negative / Zero Amount Trigger
                elif amount <= 0:
                    st.error("Invalid Amount: Transfer amount must be positive (> $0.00). Negative and zero amounts are blocked.")
                    bank.audit.add(curr_user["username"], "transfer", f"{src_acct}->{to_acct} {amount}", "DENIED: amount must be positive")
                # 3. Insufficient Balance Check
                elif bank.store.balances and amount > bank.store.balances.get(src_acct, 0) and src_acct in curr_user["owns"]:
                    st.error(f"Insufficient Balance: Account {src_acct} has ${bank.store.balances.get(src_acct, 0):,}, which cannot cover ${amount:,.2f}.")
                    # Let bank.transfer also log the real failure
                    res = bank.transfer(curr_user["token"], src_acct, to_acct, int(amount), idem=idem_key)
                    st.session_state.last_transfer_res = res
                else:
                    # Proceed to real backend transfer
                    with st.spinner("Processing transaction via LockManager and WalStore..."):
                        t_start = time.perf_counter()
                        res = bank.transfer(curr_user["token"], src_acct, to_acct, int(amount), idem=idem_key)
                        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
                        res["latency_ms"] = latency_ms
                        st.session_state.last_transfer_res = res

                    if res.get("ok"):
                        st.success(f"Transfer Committed! Successfully sent ${amount:,.2f} from Account {src_acct} to Account {to_acct}.")
                    else:
                        st.error(f"Transfer Failed / Denied: {res.get('status')}")

    with col_telemetry:
        with st.container(border=True):
            st.markdown("#### Real-Time ML Risk & Admission Telemetry")
            if "last_transfer_res" in st.session_state:
                res = st.session_state.last_transfer_res
                status_color = "green" if res.get("ok") else "red"
                st.markdown(f"**Transaction ID:** `TXN-{res.get('tid', 0):05d}`")
                st.markdown(f"**Status:** :{status_color}[**{res.get('status')}**]")
                st.markdown(f"**ML Deadlock Risk Score:** `{res.get('risk', 'N/A')}`")
                st.markdown(f"**Current WalStore LSN:** `{bank.store.lsn}`")
                if "latency_ms" in res:
                    st.caption(f"End-to-end execution latency: {res['latency_ms']} ms")
            else:
                st.info("Submit a transfer on the left to see live admission score and transaction telemetry.")

            st.markdown("---")
            st.markdown("#### Personal Audit Activity Trail")
            user_logs = [e for e in bank.audit.entries() if e.get("user") == curr_user["username"]][-6:]
            if user_logs:
                df_u = pd.DataFrame(user_logs)
                st.dataframe(df_u[["seq", "action", "detail", "result"]], width="stretch", hide_index=True)
            else:
                st.caption("No recent user activity recorded.")

    st.stop()

# -----------------------------------------------------------------------------
# 8. DEVELOPER DASHBOARD (FOCUSED 4 HIGH-IMPACT TABS)
# -----------------------------------------------------------------------------
st.markdown("## SafeLedger Developer Administration Console")
st.caption("System Engineering, Concurrency Benchmarking & Architectural Durability Monitoring")

tab1, tab2, tab3, tab4 = st.tabs([
    "1. Live Architecture & Admission Flow",
    "2. Concurrency & Stress Simulator",
    "3. Precomputed Benchmarks & Model Telemetry",
    "4. DBMS Security, WAL Crash & Recovery"
])

# =============================================================================
# TAB 1: LIVE ARCHITECTURE & ADMISSION FLOW
# =============================================================================
with tab1:
    # 5-Layer Banner
    st.markdown("""
    <div class="arch-banner">
        <div class="arch-step">
            <div class="arch-step-num">Layer 1</div>
            <div class="arch-step-name">Streamlit UI</div>
        </div>
        <div class="arch-arrow">→</div>
        <div class="arch-step">
            <div class="arch-step-num">Layer 2</div>
            <div class="arch-step-name">DBMS Security & RBAC</div>
        </div>
        <div class="arch-arrow">→</div>
        <div class="arch-step">
            <div class="arch-step-num">Layer 3</div>
            <div class="arch-step-name">OS Lock Mgr & Banker's</div>
        </div>
        <div class="arch-arrow">→</div>
        <div class="arch-step">
            <div class="arch-step-num">Layer 4</div>
            <div class="arch-step-name">RF Admission Gate</div>
        </div>
        <div class="arch-arrow">→</div>
        <div class="arch-step">
            <div class="arch-step-num">Layer 5</div>
            <div class="arch-step-name">WAL & Storage</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_insp, col_deadlock = st.columns([1.1, 1])

    with col_insp:
        with st.container(border=True):
            st.markdown("#### Single-Request Architecture Inspector")
            st.caption("Tune the 5 runtime lock telemetry features to evaluate the Random Forest predictor and os_layer.admit().")

            f1, f2, f3 = st.columns(3)
            locks_held = f1.number_input("locks_held_on_target", 0, 10, 2)
            wait_queue = f2.number_input("wait_queue_length", 0, 20, 3)
            contention = f3.number_input("account_contention_count", 0, 20, 2)

            f4, f5 = st.columns(2)
            wait_time = f4.number_input("wait_time_ms", 0.0, 500.0, 120.0, step=10.0)
            priority = f5.number_input("priority", 1, 5, 2)

            t_col1, t_col2 = st.columns(2)
            banker_safe_toggle = t_col1.checkbox("Banker's Check Says Safe", value=True)
            ml_online_toggle = t_col2.checkbox("ML Service Online", value=(pred is not None))

            feat_dict = {
                "locks_held_on_target": float(locks_held),
                "wait_queue_length": float(wait_queue),
                "account_contention_count": float(contention),
                "wait_time_ms": float(wait_time),
                "priority": float(priority)
            }

            # Evaluate risk
            if ml_online_toggle and pred is not None:
                risk_score = pred(feat_dict)
            else:
                risk_score = None  # Service down fallback

            decision = admit(banker_safe_toggle, risk_score, threshold=0.5)

            # Decision banner
            dec_color = {"GRANT": "green", "DELAY": "orange", "DENY": "red"}[decision]
            st.markdown(f"### Admission Decision: :{dec_color}[**{decision}**]")
            if risk_score is not None:
                st.metric("Predicted Deadlock Risk", f"{risk_score:.3f}", f"Threshold: 0.500")
            else:
                st.metric("Predicted Deadlock Risk", "Service Offline", "Fallback to Banker's / Ordered Lock")

            # Feature importance bar chart if metrics loaded
            if metrics_data and "feature_importance" in metrics_data:
                st.caption("Model Feature Importance Weights:")
                st.bar_chart(pd.Series(metrics_data["feature_importance"]))

    with col_deadlock:
        with st.container(border=True):
            st.markdown("#### Opposite-Transfer Deadlock Playground")
            st.caption("Executes engine.deadlock_scenario() comparing how each strategy resolves cyclic lock competition (0->1 vs 1->0).")

            strat = st.selectbox("Strategy to Evaluate", ["naive", "wfg", "banker", "banker+ml"])
            sim_down = st.checkbox("Simulate Predictor Down on banker+ml", value=False) if strat == "banker+ml" else False

            if st.button("Run Deadlock Scenario", width="stretch", type="primary"):
                if strat == "banker+ml" and not sim_down and pred is None:
                    st.warning("ML model not loaded (`model.joblib` missing). Toggle 'Simulate Predictor Down' or run `python collect_train.py`.")
                else:
                    with st.spinner("Executing opposite transfers in parallel threads..."):
                        predictor_arg = None
                        if strat == "banker+ml":
                            predictor_arg = HttpPredictor("http://localhost:5999/predict") if sim_down else pred
                        dl_res = deadlock_scenario(strat, predictor_arg)
                        st.session_state.last_dl_res = dl_res
                        st.session_state.last_dl_strat = strat

            if "last_dl_res" in st.session_state:
                res = st.session_state.last_dl_res
                s = st.session_state.last_dl_strat
                st.markdown(f"**Results for `{s.upper()}`:**")
                m1, m2 = st.columns(2)
                m1.metric("Execution Time", f"{res['wall_s']:.3f} s")
                m2.metric("Committed Txns", f"{res['committed']} / 2")
                
                m3, m4, m5 = st.columns(3)
                m3.metric("Deadlocks", f"{res['deadlocks']}")
                m4.metric("Timeouts", f"{res['timeouts']}")
                m5.metric("Retries", f"{res['retries']}")
                
                if res.get("money_conserved"):
                    st.success("Total vault money conserved exactly.")
                else:
                    st.error("Money conservation violation!")

# =============================================================================
# TAB 2: CONCURRENCY & STRESS SIMULATOR
# =============================================================================
with tab2:
    st.markdown("#### Concurrent Workload & Strategy Benchmark")
    st.caption("Dispatches multithreaded transaction loads using engine.make_specs() and engine.run_load().")

    with st.container(border=True):
        sc1, sc2, sc3, sc4 = st.columns(4)
        n_txns = sc1.slider("Transactions", 100, 500, 200, 50)
        n_workers = sc2.slider("Concurrent Clients", 4, 32, 16, 4)
        hot_frac = sc3.slider("Hot-Account Contention", 0.1, 1.0, 0.7, 0.1)
        sim_seed = sc4.number_input("Workload Seed", 1, 9999, 42)

        all_strats = ["naive", "wfg", "ordered", "banker", "wfg+ml", "banker+ml"]
        chosen_strats = st.multiselect("Strategies to Compare", all_strats, default=["naive", "wfg", "banker", "banker+ml"])

        if st.button("Execute Concurrency Simulator", type="primary", width="stretch"):
            if not chosen_strats:
                st.warning("Please choose at least one strategy.")
            else:
                sim_rows = []
                prog = st.progress(0.0)
                specs = make_specs(n_txns, int(sim_seed), hot_frac=hot_frac, source="synthetic")
                
                for idx, strat_name in enumerate(chosen_strats):
                    if strat_name.endswith("+ml") and pred is None:
                        st.warning(f"Skipping '{strat_name}': ML model (`model.joblib`) not loaded.")
                        prog.progress((idx + 1) / len(chosen_strats))
                        continue
                    with st.spinner(f"Running mode: {strat_name}..."):
                        r = run_load(specs, strat_name, workers=n_workers, predictor=pred, seed=int(sim_seed))
                        sim_rows.append(r)
                    prog.progress((idx + 1) / len(chosen_strats))
                prog.empty()
                st.session_state.sim_results = sim_rows

    if "sim_results" in st.session_state and st.session_state.sim_results:
        df_sim = pd.DataFrame(st.session_state.sim_results).set_index("mode")

        st.markdown("##### Comparative Performance Charts")
        c_ch1, c_ch2, c_ch3 = st.columns(3)
        with c_ch1:
            st.caption("Throughput (Transactions/sec, higher is better)")
            st.bar_chart(df_sim["tps"])
        with c_ch2:
            st.caption("P95 Tail Latency (ms, lower is better)")
            st.bar_chart(df_sim["p95_ms"])
        with c_ch3:
            st.caption("Deadlocks & Retries (lower is better)")
            st.bar_chart(df_sim[["deadlocks", "retries"]])

        st.markdown("##### Telemetry Summary Table")
        cols_to_show = ["committed", "failed", "retries", "deadlocks", "timeouts", "banker_waits", "ml_delays", "tps", "p50_ms", "p95_ms", "money_conserved"]
        avail_cols = [c for c in cols_to_show if c in df_sim.columns]
        st.dataframe(df_sim[avail_cols], width="stretch")

# =============================================================================
# TAB 3: PRECOMPUTED BENCHMARKS & MODEL TELEMETRY
# =============================================================================
with tab3:
    st.markdown("#### Precomputed Benchmarks & Model Evaluation Telemetry")
    st.caption("Reads benchmark.csv, sweep.csv, and model_metrics.json directly from disk.")

    b_col1, b_col2 = st.columns([1, 1.2])

    with b_col1:
        with st.container(border=True):
            st.markdown("##### Random Forest Model KPIs")
            if metrics_data:
                m1, m2 = st.columns(2)
                m1.metric("ROC-AUC", f"{metrics_data.get('roc_auc', 0):.3f}")
                m2.metric("F1 Score", f"{metrics_data.get('f1', 0):.3f}")

                m3, m4 = st.columns(2)
                m3.metric("Precision", f"{metrics_data.get('precision', 0):.3f}")
                m4.metric("Recall", f"{metrics_data.get('recall', 0):.3f}")

                st.caption(f"Inference Latency: {metrics_data.get('predict_ms_per_call', 0):.2f} ms/call")
                
                if "confusion_matrix" in metrics_data:
                    st.caption("Confusion Matrix [[TN, FP], [FN, TP]]:")
                    cm = np.array(metrics_data["confusion_matrix"])
                    df_cm = pd.DataFrame(cm, columns=["Pred: Normal", "Pred: Deadlock"], index=["Actual: Normal", "Actual: Deadlock"])
                    st.dataframe(df_cm, width="stretch")
            else:
                st.info("model_metrics.json not found. Run python collect_train.py to generate.")

    with b_col2:
        with st.container(border=True):
            st.markdown("##### Throughput vs. Concurrent Clients (Sweep)")
            if SWEEP_PATH and os.path.exists(SWEEP_PATH):
                df_sw = pd.read_csv(SWEEP_PATH)
                if "workers" in df_sw.columns and "tps" in df_sw.columns:
                    piv = df_sw.groupby(["workers", "mode"])["tps"].mean().unstack()
                    st.line_chart(piv)
                    st.caption("Demonstrates scalability up to 32 worker threads across configurations.")
            else:
                st.info("sweep.csv not found. Run python benchmark.py to generate.")

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("##### Full Baseline Benchmark Results")
        if BENCHMARK_PATH and os.path.exists(BENCHMARK_PATH):
            df_b = pd.read_csv(BENCHMARK_PATH)
            b_agg = df_b.groupby("mode")[["tps", "p50_ms", "p95_ms", "retries", "deadlocks", "timeouts"]].mean().round(2)
            st.dataframe(b_agg, width="stretch")
        else:
            st.info("benchmark.csv not found. Run python benchmark.py to generate.")

# =============================================================================
# TAB 4: DBMS SECURITY, WAL CRASH & RECOVERY
# =============================================================================
with tab4:
    st.markdown("#### DBMS Durability, Crash Recovery & Security Verification")
    st.caption("Directly inspects and triggers operations on st.session_state.bank.")

    d_col1, d_col2 = st.columns(2)

    with d_col1:
        with st.container(border=True):
            st.markdown("##### Crash Recovery (ARIES Protocol)")
            st.caption("Simulates a sudden power loss with uncommitted dirty pages and verifies WAL redo/undo.")

            c_btn1, c_btn2, c_btn3 = st.columns(3)
            if c_btn1.button("1. Checkpoint", width="stretch"):
                if not bank.store.up or bank.store.balances is None:
                    st.warning("Database is currently DOWN. Run '3. Recover' first.")
                else:
                    try:
                        ckpt_lsn = bank.admin(curr_user["token"], "checkpoint")
                        st.success(f"Snapshot flushed at LSN {ckpt_lsn}")
                    except (Forbidden, AuthError) as e:
                        st.error(f"Access Denied: {e}")

            if c_btn2.button("2. Crash DB", width="stretch"):
                if not bank.store.up or bank.store.balances is None:
                    st.warning("Database is already CRASHED. Click '3. Recover' to restore it.")
                else:
                    # Crash mid-transaction with steal=True
                    bank.store.simulate_crash(9999, [(1, -500), (2, 500)], steal=True)
                    st.error("System CRASHED! In-memory state cleared. Dirty half-done writes forced to disk.")

            if c_btn3.button("3. Recover", width="stretch", type="primary"):
                try:
                    rep = bank.store.recover()
                    conserved_now = bank.store.total() == bank.store.initial_total
                    st.success(f"Recovery Completed! Redone: {rep['redone']} | Undone: {rep['undone']} losers | Conserved: {conserved_now}")
                    st.json(rep)
                except Exception as e:
                    st.error(f"Recovery error: {e}")

            st.markdown("---")
            st.markdown("##### Backup & Point-in-Time Restore")
            pit_lsn = st.number_input("Point-in-Time Restore until LSN (0 = latest)", min_value=0, value=0, step=1)
            bk_col1, bk_col2 = st.columns(2)
            if bk_col1.button("Create Backup", width="stretch"):
                if not bank.store.up or bank.store.balances is None:
                    st.warning("Database is currently DOWN. Recover before creating a backup.")
                else:
                    try:
                        bk_dest = tempfile.mkdtemp(prefix="sl_backup_")
                        bank.admin(curr_user["token"], "backup", dest=bk_dest)
                        st.session_state.last_backup_dest = bk_dest
                        st.success(f"Backup manifest saved to: `{os.path.basename(bk_dest)}`")
                    except (Forbidden, AuthError) as e:
                        st.error(f"Access Denied: {e}")

            if bk_col2.button("Restore Backup", width="stretch"):
                if "last_backup_dest" in st.session_state:
                    try:
                        rst_dest = tempfile.mkdtemp(prefix="sl_restored_")
                        until_arg = int(pit_lsn) if pit_lsn > 0 else None
                        restored_store = WalStore.restore(st.session_state.last_backup_dest, rst_dest, until_lsn=until_arg, sync=False)
                        st.success(f"Restored! Total: ${restored_store.total():,} ({restored_store.committed} committed txns).")
                    except Exception as e:
                        st.error(f"Restore failed: {e}")
                else:
                    st.warning("Please click 'Create Backup' first.")

    with d_col2:
        with st.container(border=True):
            st.markdown("##### Audit Hash-Chain Tamper Detection")
            st.caption("Verifies SHA-256 hash chains across append-only audit entries.")

            t_btn1, t_btn2 = st.columns(2)
            if t_btn1.button("Verify Hash Chain", width="stretch", type="primary"):
                ok, bad_seq = bank.audit.verify()
                if ok:
                    st.success(f"Audit Log Verified: All {len(bank.audit.entries())} entries are cryptographically intact!")
                else:
                    st.error(f"TAMPERING DETECTED: Chain broken at sequence #{bad_seq}!")

            if t_btn2.button("Simulate Tamper", width="stretch"):
                entries = bank.audit.entries()
                if len(entries) >= 2:
                    bank.audit._tamper(2, result="TAMPERED_BY_ATTACKER")
                    st.warning("Tampered with Audit entry #2! Click 'Verify Hash Chain' to prove detection.")
                else:
                    st.info("Execute a few actions first to populate the audit log.")

            st.markdown("---")
            st.markdown("##### Live WAL & Audit Log Tail Viewer")
            with st.expander("View wal.log tail (CRC-32 Checksummed)", expanded=False):
                if os.path.exists(bank.store.wal):
                    with open(bank.store.wal, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()[-15:]
                        st.code("".join(lines), language="json")
                else:
                    st.caption("No WAL log found.")

            with st.expander("View audit.log entries", expanded=False):
                a_entries = bank.audit.entries()[-10:]
                if a_entries:
                    st.dataframe(pd.DataFrame(a_entries)[["seq", "user", "action", "detail", "result", "prev"]], width="stretch")
                else:
                    st.caption("No audit entries.")
