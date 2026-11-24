"""
Page 5: Machine Learning Risk Analysis
Integrates collect_train.py artifacts and engine.py Predictor for real-time risk assessment.
"""
import os, json
import pandas as pd
import streamlit as st
from engine import FEATURES
from ui.styles import render_header, render_metric

def render_page(pred, model_path):
    render_header(
        "Machine Learning Risk Gate & Telemetry",
        "Random Forest deadlock prediction model evaluating runtime lock queue characteristics.",
        badge="AI Admission Control"
    )

    metrics_path = "results/model_metrics.json"
    has_metrics = os.path.exists(metrics_path)
    metrics = {}
    if has_metrics:
        try:
            with open(metrics_path, "r") as f:
                metrics = json.load(f)
        except Exception:
            pass

    # Model Overview
    c1, c2, c3, c4 = st.columns(4)
    model_loaded = pred is not None
    c1.metric("Model Status", "LOADED" if model_loaded else "NOT FOUND", model_path)
    c2.metric("Classifier", "RandomForest", "Estimators=40, Depth=8")
    
    if "f1" in metrics:
        c3.metric("F1 Score", f"{metrics['f1']:.4f}", f"Recall: {metrics.get('recall', 0):.3f}")
    else:
        c3.metric("F1 Score", "N/A", "Run collect_train.py")
        
    if "roc_auc" in metrics:
        c4.metric("ROC-AUC", f"{metrics['roc_auc']:.4f}", f"Precision: {metrics.get('precision', 0):.3f}")
    else:
        c4.metric("ROC-AUC", "N/A", "Run collect_train.py")

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

    # Training Telemetry and Feature Importance
    if has_metrics and metrics:
        st.markdown("#### Model Evaluation Metrics (Held-out Test Workload)")
        m_col1, m_col2 = st.columns([1, 1])
        
        with m_col1:
            perf_df = pd.DataFrame([
                {"Metric": "Training Set Records", "Value": f"{metrics.get('train_rows', 'N/A'):,}"},
                {"Metric": "Test Set Records", "Value": f"{metrics.get('test_rows', 'N/A'):,}"},
                {"Metric": "Deadlock/Timeout Positive Share", "Value": f"{metrics.get('positive_share_test', 0):.2%}"},
                {"Metric": "Precision", "Value": f"{metrics.get('precision', 0):.4f}"},
                {"Metric": "Recall", "Value": f"{metrics.get('recall', 0):.4f}"},
                {"Metric": "F1 Score", "Value": f"{metrics.get('f1', 0):.4f}"},
                {"Metric": "ROC-AUC", "Value": f"{metrics.get('roc_auc', 0):.4f}"},
                {"Metric": "False Positive Rate", "Value": f"{metrics.get('false_positive_rate', 0):.2%}"},
                {"Metric": "Per-Call Prediction Latency", "Value": f"{metrics.get('predict_ms_per_call', 0):.2f} ms"},
            ])
            st.dataframe(perf_df, width='stretch', hide_index=True)

        with m_col2:
            st.markdown("**Relative Feature Importance**")
            feat_imp = metrics.get("feature_importance", {})
            if feat_imp:
                feat_series = pd.Series(feat_imp).sort_values(ascending=True)
                st.bar_chart(feat_series)

    # Interactive Inference Gate
    st.markdown("---")
    st.markdown("#### Real-Time Risk Inference & Admission Decision")
    st.write("Input runtime lock telemetry features to evaluate the risk score and admission gating decision:")

    if not model_loaded:
        st.warning("Prediction requires a trained model. Run `python collect_train.py` from your terminal or command prompt.")
        return

    f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns(5)
    
    locks_held = f_col1.number_input("locks_held_on_target", min_value=0, max_value=20, value=2,
                                     help="Locks currently held by the target transaction")
    wait_queue = f_col2.number_input("wait_queue_length", min_value=0, max_value=50, value=3,
                                     help="Number of threads waiting for this account lock")
    contention = f_col3.number_input("account_contention_count", min_value=0, max_value=50, value=2,
                                     help="Cumulative count of contention events on this account")
    wait_time = f_col4.number_input("wait_time_ms", min_value=0.0, max_value=5000.0, value=120.0, step=10.0,
                                    help="Elapsed wait time in milliseconds")
    priority = f_col5.number_input("priority", min_value=1, max_value=5, value=2,
                                   help="Transaction priority (1=Urgent, 5=Low)")

    col_toggle1, col_toggle2 = st.columns(2)
    banker_safe = col_toggle1.checkbox("Banker's Algorithm Assessment Says Safe", value=True)
    sim_outage = col_toggle2.checkbox("Simulate ML Predictor Outage (Trigger Safe Fallback)", value=False)

    threshold = st.slider("Risk Decision Threshold (Default = 0.50)", min_value=0.1, max_value=0.9, value=0.5, step=0.05)

    if st.button("Evaluate Transaction Risk"):
        features = {
            "locks_held_on_target": float(locks_held),
            "wait_queue_length": float(wait_queue),
            "account_contention_count": float(contention),
            "wait_time_ms": float(wait_time),
            "priority": float(priority),
        }

        if sim_outage:
            risk = None
            st.warning("ML Service Unreachable: Engine falls back cleanly to Banker's check + ordered locking.")
        else:
            risk = pred(features)

        # Decision rule from engine/os_layer:
        # 1. Not safe by Banker -> DENY (rule-based always wins)
        # 2. Banker safe, risk >= threshold -> DELAY
        # 3. Banker safe, risk < threshold -> GRANT
        if not banker_safe:
            decision = "DENY"
            dec_color = "red"
            explanation = "Banker's algorithm detected potential resource depletion or cycle formation. Rule-based safety overrides ML."
        elif risk is not None and risk >= threshold:
            decision = "DELAY"
            dec_color = "orange"
            explanation = f"Risk score ({risk:.3f}) exceeds threshold ({threshold}). Transaction is delayed briefly to relieve contention before re-evaluation."
        else:
            decision = "GRANT"
            dec_color = "green"
            explanation = f"Safe state confirmed by Banker's Algorithm and ML risk ({risk if risk is not None else 'N/A'}) is below threshold."

        r1, r2 = st.columns([1, 2])
        with r1:
            if risk is not None:
                st.metric("Deadlock Risk Probability", f"{risk:.2%}", f"Threshold: {threshold:.0%}")
            else:
                st.metric("Deadlock Risk Probability", "N/A", "Service Offline")
        with r2:
            st.markdown(f"### Admission Decision: :{dec_color}[{decision}]")
            st.write(explanation)

        st.caption("Note: ML risk score is a statistical probability estimate derived from runtime telemetry, working in tandem with the deterministic Banker algorithm.")
