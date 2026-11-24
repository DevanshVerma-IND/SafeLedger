"""ML microservice. Run: python ml_service/app.py   (from the project folder)
POST /predict with the five features as JSON -> {"risk_score": 0..1, "high_risk": bool}"""
import os
import joblib
from flask import Flask, jsonify, request

FEATURES = ["locks_held_on_target", "wait_queue_length", "account_contention_count", "wait_time_ms", "priority"]
MODEL = os.path.join(os.path.dirname(__file__), "..", "results", "model.joblib")
app, model = Flask(__name__), joblib.load(MODEL)

@app.post("/predict")
def predict():
    d = request.get_json(silent=True) or {}
    try: x = [[float(d[k]) for k in FEATURES]]
    except (KeyError, ValueError, TypeError) as e: return jsonify(error=f"bad or missing field: {e}"), 400
    s = float(model.predict_proba(x)[0][1]); return jsonify(risk_score=round(s, 4), high_risk=s >= 0.5)

@app.get("/health")
def health(): return jsonify(status="ok")

if __name__ == "__main__": app.run(host="0.0.0.0", port=5000)
