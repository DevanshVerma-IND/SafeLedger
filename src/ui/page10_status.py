"""
Page 10: System & Database Status
Displays detailed diagnostics about the Python runtime environment, database connectivity
(PostgreSQL vs SQLite fallback), ML model availability, and file readiness.
"""
import sys, os, platform
import streamlit as st
import pandas as pd
import pg_store
from ui.styles import render_header, render_metric

def render_page(pred, model_path):
    render_header(
        "System Diagnostics & Database Connectivity",
        "Runtime telemetry, database connection mode, Python environment, and file system asset status.",
        badge="Infrastructure Diagnostics"
    )

    pg_enabled = pg_store.enabled()
    dsn_configured = pg_store.dsn() is not None

    # Status Overview
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Python Runtime", f"{platform.python_version()}", platform.system())
    c2.metric("Database Mode", "PostgreSQL" if pg_enabled else "SQLite WAL", "Optional PG enabled" if pg_enabled else "Default Fallback")
    c3.metric("ML Model", "Available" if pred else "Uninitialized", "Ready for admission" if pred else "Needs training")
    c4.metric("Streamlit Version", st.__version__, "Active UI Framework")

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### Database Subsystem Diagnostics")
        db_details = [
            {"Parameter": "Active Backend", "Value": "PostgreSQL (Enterprise Pool)" if pg_enabled else "SQLite (WAL Mode)"},
            {"Parameter": "SAFELEDGER_PG_DSN Configured", "Value": "Yes" if dsn_configured else "No (Using SQLite)"},
            {"Parameter": "PostgreSQL Connection Pool", "Value": f"Max {pg_store.POOL_MAX} threads" if pg_enabled else "N/A (SQLite single-writer multi-reader)"},
            {"Parameter": "Synchronous Commit", "Value": os.environ.get("SAFELEDGER_PG_SYNC_COMMIT", "off") if pg_enabled else "NORMAL (WAL)"},
            {"Parameter": "Schema Definitions", "Value": "sql/schema.sql verified" if os.path.exists("sql/schema.sql") else "Missing"},
        ]
        st.dataframe(pd.DataFrame(db_details), width='stretch', hide_index=True)

        if not pg_enabled:
            st.info("""
            **PostgreSQL Integration Notice:**
            PostgreSQL mode is optional. When `SAFELEDGER_PG_DSN` is not defined in your environment, 
            SafeLedger automatically runs using its high-speed local SQLite WAL engine.
            
            To activate PostgreSQL mode:
            ```bash
            export SAFELEDGER_PG_DSN="postgresql://safeledger:pass@localhost:5432/safeledger"
            # On Windows PowerShell:
            $env:SAFELEDGER_PG_DSN="postgresql://safeledger:pass@localhost:5432/safeledger"
            python seed_postgres.py
            ```
            """)

    with col2:
        st.markdown("#### Project File & Asset Availability")
        files_to_check = [
            ("engine.py", "Core transaction engine & lock manager"),
            ("dbms.py", "WAL, recovery, security, Bank class"),
            ("os_layer.py", "Banker, WFG, scheduler, sync"),
            ("pg_store.py", "PostgreSQL database connector"),
            ("collect_train.py", "Telemetry collector and ML training pipeline"),
            ("benchmark.py", "Performance benchmarks & sweeps"),
            ("results/model.joblib", "Trained Random Forest model binary"),
            ("results/model_metrics.json", "Model performance evaluation metrics"),
            ("results/benchmark.csv", "Empirical benchmark metrics dataset"),
            ("results/sweep.csv", "Worker thread concurrency sweep data"),
        ]

        file_status_rows = []
        for path, desc in files_to_check:
            exists = os.path.exists(path)
            file_status_rows.append({
                "File": path,
                "Status": "Available" if exists else "Missing",
                "Description": desc
            })
        st.dataframe(pd.DataFrame(file_status_rows), width='stretch', hide_index=True)

    st.markdown("---")
    st.markdown("#### Python Execution Environment")
    env_details = [
        {"Property": "Executable", "Value": sys.executable},
        {"Property": "Working Directory", "Value": os.getcwd()},
        {"Property": "Platform", "Value": platform.platform()},
        {"Property": "Byteorder", "Value": sys.byteorder},
    ]
    st.dataframe(pd.DataFrame(env_details), width='stretch', hide_index=True)
