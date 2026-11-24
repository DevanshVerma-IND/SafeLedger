"""
Authentication and Session RBAC Manager for SafeLedger.
Uses the real Bank, UserStore, and PBKDF2 hashing in dbms.py.
"""
import os, tempfile
import streamlit as st
from dbms import Bank, AuthError, Forbidden
import pg_store

def get_shared_bank():
    """Initializes and persists the shared Bank instance across the Streamlit session."""
    if "bank_instance" not in st.session_state:
        bank_dir = os.path.join(tempfile.gettempdir(), "safeledger_live_bank")
        os.makedirs(bank_dir, exist_ok=True)
        # Check if fresh or existing
        fresh = not os.path.exists(os.path.join(bank_dir, "db", "wal.log"))
        b = Bank(bank_dir, n_accounts=50, sync=True)
        
        # Seed default users if newly created
        # Customers:
        b.users.add("alice", "pass-alice", "customer", owns=[1, 2])
        b.users.add("bob", "pass-bob", "customer", owns=[3, 4])
        b.users.add("carol", "pass-carol", "customer", owns=[5, 6])
        # Staff / Developer / Admin:
        b.users.add("developer", "pass-dev", "admin")
        b.users.add("teller", "pass-teller", "teller")
        b.users.add("auditor", "pass-auditor", "auditor")
        b.users.add("admin", "pass-admin", "admin")
        
        st.session_state["bank_instance"] = b
        st.session_state["bank_dir"] = bank_dir
    return st.session_state["bank_instance"]

def login_user(username, password):
    """Authenticates against the real Bank backend, stores verified token in session state."""
    b = get_shared_bank()
    try:
        token = b.login(username, password)
        user_info = b.users.get(username)
        st.session_state["auth_token"] = token
        st.session_state["auth_username"] = username
        st.session_state["auth_role"] = user_info["role"]
        st.session_state["auth_owns"] = list(user_info["owns"])
        return True, "Login successful"
    except AuthError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Authentication error: {str(e)}"

def logout_user():
    """Clears authenticated session and returns to login."""
    b = get_shared_bank()
    user = st.session_state.get("auth_username", "anonymous")
    b.audit.add(user, "logout", "", "OK")
    for k in ["auth_token", "auth_username", "auth_role", "auth_owns"]:
        st.session_state.pop(k, None)
    st.rerun()

def get_current_user():
    """Validates the stored session token using backend PBKDF2/HMAC verification."""
    b = get_shared_bank()
    token = st.session_state.get("auth_token")
    if not token:
        return None
    try:
        username = b.users.verify(token)
        user_info = b.users.get(username)
        if not user_info:
            return None
        return {
            "username": username,
            "role": user_info["role"],
            "owns": user_info["owns"],
            "token": token
        }
    except AuthError:
        # Expired or forged token
        logout_user()
        return None

def is_developer_or_admin(user):
    """RBAC check: Only 'admin' or developer roles have access to developer monitoring & admin."""
    if not user:
        return False
    return user.get("role") in ("admin", "developer")
