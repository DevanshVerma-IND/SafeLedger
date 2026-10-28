"""
ML microservice. Run with: python3 app.py
Java calls POST http://localhost:5000/predict with a JSON body.
"""
from flask import Flask, request, jsonify
import joblib
import pandas as pd

app = Flask(__name__)
model = joblib.load("model/deadlock_rf.joblib")

FEATURES = ["locks_held_on_target", "wait_queue_length",
            "account_contention_count", "wait_time_ms", "priority"]
THRESHOLD = 0.5


@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    try:
        row = pd.DataFrame([{f: data[f] for f in FEATURES}])
    except KeyError as e:
        return jsonify({"error": f"missing field {e}"}), 400

    score = float(model.predict_proba(row)[0][1])
    return jsonify({
        "risk_score": round(score, 4),
        "high_risk": score >= THRESHOLD
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
